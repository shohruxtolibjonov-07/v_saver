"""URL detection, format/quality selection, and download pipeline handler."""

import re
import os
import logging
import hashlib
import time
import html as html_lib

from aiogram import Router, types, Bot, F
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ChatAction

from config import ADMIN_ID, TELEGRAM_VIDEO_LIMIT, TELEGRAM_DOCUMENT_LIMIT, TEMP_DIR, BOT_USERNAME
from utils import messages as msg
from services.youtube import YouTubeDownloader
from services.instagram import InstagramDownloader
from services.media import MediaProcessor
from services.worker import WorkerPool, DownloadJob

logger = logging.getLogger(__name__)
router = Router()

# Services
yt_downloader = YouTubeDownloader()
ig_downloader = InstagramDownloader()
media_processor = MediaProcessor()

# Worker pool reference — set at startup
_worker_pool: WorkerPool | None = None


def set_worker_pool(pool: WorkerPool):
    global _worker_pool
    _worker_pool = pool


# ─── URL cache (hash → url, TTL=1h) ─────────────
_URL_CACHE_TTL = 3600
_url_cache: dict[str, tuple[str, float]] = {}


def _cache_url(url_hash: str, url: str):
    if len(_url_cache) > 500:
        now = time.time()
        expired = [k for k, (_, ts) in _url_cache.items() if now - ts > _URL_CACHE_TTL]
        for k in expired:
            del _url_cache[k]
    _url_cache[url_hash] = (url, time.time())


def _get_cached_url(url_hash: str) -> str | None:
    entry = _url_cache.get(url_hash)
    if not entry:
        return None
    url, ts = entry
    if time.time() - ts > _URL_CACHE_TTL:
        del _url_cache[url_hash]
        return None
    return url


# ─── URL patterns ────────────────────────────────
YOUTUBE_RE = re.compile(
    r'(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be)/(watch\?[^\s]+|shorts/[\w\-]+[^\s]*|embed/[\w\-]+|v/[\w\-]+|live/[\w\-]+|[\w\-]{11})',
    re.IGNORECASE,
)
INSTAGRAM_RE = re.compile(
    r'(https?://)?(www\.)?(instagram\.com|instagr\.am)/(p|reel|reels|stories|tv)/[\w\-/]+',
    re.IGNORECASE,
)


def extract_urls(text: str) -> list[dict]:
    urls = []
    seen = set()
    for match in YOUTUBE_RE.finditer(text):
        url = match.group(0)
        if not url.startswith("http"):
            url = "https://" + url
        if url not in seen:
            seen.add(url)
            urls.append({"url": url, "platform": "youtube"})
    for match in INSTAGRAM_RE.finditer(text):
        url = match.group(0)
        if not url.startswith("http"):
            url = "https://" + url
        if url not in seen:
            seen.add(url)
            urls.append({"url": url, "platform": "instagram"})
    return urls


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _make_format_keyboard(url_hash: str) -> InlineKeyboardMarkup:
    """Format selection: Video / Audio."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎬 Video", callback_data=f"dl:v:{url_hash}"),
            InlineKeyboardButton(text="🎧 Audio", callback_data=f"dl:a:{url_hash}"),
        ]
    ])


def _make_quality_keyboard(url_hash: str, estimated_size: int) -> InlineKeyboardMarkup:
    """Quality selection for >50MB files."""
    size_str = _format_size(estimated_size)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📥 Original ({size_str})", callback_data=f"ql:best:{url_hash}")],
        [InlineKeyboardButton(text="📦 O'rtacha (~720p)", callback_data=f"ql:medium:{url_hash}")],
        [InlineKeyboardButton(text="📄 Kichik (~480p)", callback_data=f"ql:low:{url_hash}")],
    ])


def _make_caption(title: str, duration_str: str, size: int, media_type: str) -> str:
    """Build caption with bot username."""
    title_safe = html_lib.escape(title[:200])
    size_str = _format_size(size)

    if media_type == "audio":
        template = msg.CAPTION_AUDIO
    elif media_type == "video":
        template = msg.CAPTION_VIDEO
    else:
        template = msg.CAPTION_DOCUMENT

    return template.format(
        title=title_safe,
        duration=duration_str or "—",
        size=size_str,
        bot_username=BOT_USERNAME,
    )


# ═══════════════════════════════════════════════════
# Video-to-Audio extraction (user sends a video file)
# ═══════════════════════════════════════════════════
@router.message(F.video | F.document.func(lambda d: d and d.mime_type and d.mime_type.startswith("video/")))
async def handle_video_message(message: types.Message, bot: Bot):
    video = message.video or message.document
    if not video:
        return

    file_size = video.file_size or 0
    if file_size > 20 * 1024 * 1024:
        await message.answer(msg.AUDIO_EXTRACT_TOO_LARGE, parse_mode="HTML")
        return

    status_msg = await message.answer(msg.AUDIO_EXTRACTING, parse_mode="HTML")
    video_path = None
    audio_result = None

    try:
        await bot.send_chat_action(message.chat.id, ChatAction.RECORD_VOICE)

        file = await bot.get_file(video.file_id)
        video_dir = TEMP_DIR / "video_extract"
        video_dir.mkdir(exist_ok=True)

        if hasattr(video, "file_name") and video.file_name:
            ext = os.path.splitext(video.file_name)[1] or ".mp4"
            filename = f"{video.file_unique_id}{ext}"
        else:
            filename = f"{video.file_unique_id}.mp4"

        video_path = str(video_dir / filename)
        await bot.download_file(file.file_path, video_path)

        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VOICE)

        title = "audio"
        if message.caption:
            title = message.caption[:50]
        elif hasattr(video, "file_name") and video.file_name:
            title = os.path.splitext(video.file_name)[0][:50]

        audio_result = await media_processor.extract_audio_from_video(video_path, title)

        input_file = FSInputFile(audio_result["file_path"])
        caption = msg.AUDIO_EXTRACT_SUCCESS.format(
            title=html_lib.escape(audio_result["title"]),
            size=_format_size(audio_result["file_size"]),
        )

        await bot.send_audio(
            message.chat.id,
            audio=input_file,
            caption=caption + f"\n\n@{BOT_USERNAME}",
            parse_mode="HTML",
            title=audio_result["title"][:64],
        )

        try:
            await status_msg.delete()
        except Exception:
            pass

    except Exception as e:
        error_text = str(e)
        logger.error(f"Audio extraction error: {error_text}")

        if "FFMPEG_NOT_AVAILABLE" in error_text:
            error_msg = msg.ERROR_FFMPEG_MISSING
        else:
            error_msg = msg.ERROR_GENERIC

        try:
            await status_msg.edit_text(error_msg, parse_mode="HTML")
        except Exception:
            await message.answer(error_msg, parse_mode="HTML")

    finally:
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except Exception:
                pass
        if audio_result and audio_result.get("file_path"):
            media_processor._safe_remove(audio_result["file_path"])


# ═══════════════════════════════════════════════════
# Callback: Format selection (dl:v:hash / dl:a:hash)
# ═══════════════════════════════════════════════════
@router.callback_query(F.data.startswith("dl:"))
async def handle_format_callback(callback: CallbackQuery, bot: Bot):
    await callback.answer()

    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        return

    _, mode, url_hash = parts
    is_audio = (mode == "a")

    url = _get_cached_url(url_hash)
    if not url:
        try:
            await callback.message.edit_text(msg.ERROR_LINK_EXPIRED, parse_mode="HTML")
        except Exception:
            pass
        return

    platform = "youtube" if YOUTUBE_RE.search(url) else "instagram"

    # Show immediate feedback
    status_text = msg.CHECKING_INFO
    try:
        await callback.message.edit_text(status_text, parse_mode="HTML")
    except Exception:
        pass

    try:
        if is_audio:
            # Audio — always download directly (audio is always small)
            status_text = msg.DOWNLOADING_AUDIO
            try:
                await callback.message.edit_text(status_text, parse_mode="HTML")
            except Exception:
                pass

            await _process_download(
                bot, callback.message.chat.id, callback.from_user.id,
                url, platform, is_audio=True, quality="best",
                status_msg=callback.message,
            )
        else:
            # Video — check size first
            if platform == "youtube":
                info = await yt_downloader.get_info(url)
                estimated_size = info.get("video_size", 0)
            else:
                info = await ig_downloader.get_info(url)
                estimated_size = info.get("estimated_size", 0)

            if estimated_size > TELEGRAM_VIDEO_LIMIT and estimated_size > 0:
                # >50 MB — show quality choice
                keyboard = _make_quality_keyboard(url_hash, estimated_size)
                size_str = _format_size(estimated_size)
                try:
                    await callback.message.edit_text(
                        msg.QUALITY_CHOICE.format(size=size_str),
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
                except Exception:
                    pass
            else:
                # ≤50 MB — download best quality directly
                status_text = msg.DOWNLOADING_VIDEO
                try:
                    await callback.message.edit_text(status_text, parse_mode="HTML")
                except Exception:
                    pass

                await _process_download(
                    bot, callback.message.chat.id, callback.from_user.id,
                    url, platform, is_audio=False, quality="best",
                    status_msg=callback.message,
                )

    except Exception as e:
        error_text = str(e)
        logger.error(f"Format callback error for {url}: {error_text}")

        try:
            await callback.message.edit_text(msg.ERROR_DOWNLOAD_FAILED, parse_mode="HTML")
        except Exception:
            pass

        # Notify admin
        _notify_admin_error(bot, callback.from_user.id, url, error_text)


# ═══════════════════════════════════════════════════
# Callback: Quality selection (ql:best:hash / ql:medium:hash / ql:low:hash)
# ═══════════════════════════════════════════════════
@router.callback_query(F.data.startswith("ql:"))
async def handle_quality_callback(callback: CallbackQuery, bot: Bot):
    await callback.answer()

    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        return

    _, quality, url_hash = parts
    url = _get_cached_url(url_hash)
    if not url:
        try:
            await callback.message.edit_text(msg.ERROR_LINK_EXPIRED, parse_mode="HTML")
        except Exception:
            pass
        return

    platform = "youtube" if YOUTUBE_RE.search(url) else "instagram"

    # Show processing message
    quality_name = {"best": "Original", "medium": "O'rtacha", "low": "Kichik"}.get(quality, quality)
    try:
        await callback.message.edit_text(
            msg.QUALITY_PROCESSING.format(quality=quality_name),
            parse_mode="HTML",
        )
    except Exception:
        pass

    try:
        await _process_download(
            bot, callback.message.chat.id, callback.from_user.id,
            url, platform, is_audio=False, quality=quality,
            status_msg=callback.message,
        )
    except Exception as e:
        error_text = str(e)
        logger.error(f"Quality download error for {url}: {error_text}")
        try:
            await callback.message.edit_text(msg.ERROR_DOWNLOAD_FAILED, parse_mode="HTML")
        except Exception:
            pass
        _notify_admin_error(bot, callback.from_user.id, url, error_text)


# ═══════════════════════════════════════════════════
# Core download + send pipeline
# ═══════════════════════════════════════════════════
async def _process_download(
    bot: Bot, chat_id: int, user_id: int,
    url: str, platform: str,
    is_audio: bool, quality: str,
    status_msg: types.Message,
):
    """Download and send media to user."""
    file_path = None
    processed = None
    recompressed = None

    try:
        await bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)

        if platform == "youtube":
            result = await yt_downloader.download(url, audio_only=is_audio, quality=quality)
            file_path = result["file_path"]
            title = result["title"]
            duration_str = result.get("duration_str", "")
            duration = result.get("duration")
            media_type = result["media_type"]

        else:  # instagram
            result = await ig_downloader.download(url, audio_only=is_audio)
            # Instagram may return multiple files, process first one
            if result["files"]:
                first = result["files"][0]
                file_path = first["file_path"]
                media_type = first["media_type"]
                if is_audio:
                    media_type = "audio"
            else:
                try:
                    await status_msg.edit_text(msg.ERROR_NOT_FOUND, parse_mode="HTML")
                except Exception:
                    pass
                return
            title = result.get("title", "Instagram media")
            duration_str = ""
            duration = None

        file_size = os.path.getsize(file_path)

        # Recompress if needed (medium/low quality for >50MB files)
        if quality in ("medium", "low") and media_type == "video":
            recomp = await media_processor.recompress_video(file_path, quality)
            recompressed = recomp["file_path"] if recomp["was_compressed"] else None
            if recompressed:
                file_size = recomp["file_size"]
                actual_path = recompressed
            else:
                actual_path = file_path
        else:
            actual_path = file_path

        # Check if file exceeds Telegram document limit (~2 GB)
        if file_size > TELEGRAM_DOCUMENT_LIMIT:
            try:
                await status_msg.edit_text(msg.ERROR_FILE_TOO_LARGE, parse_mode="HTML")
            except Exception:
                await bot.send_message(chat_id, msg.ERROR_FILE_TOO_LARGE, parse_mode="HTML")
            return

        # Build caption
        caption = _make_caption(title, duration_str, file_size, media_type)

        input_file = FSInputFile(actual_path)

        await bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)

        # Send based on size and type
        if media_type == "audio":
            if file_size <= TELEGRAM_VIDEO_LIMIT:
                await bot.send_audio(
                    chat_id, audio=input_file, caption=caption,
                    parse_mode="HTML", title=title[:64],
                    duration=duration,
                )
            else:
                await bot.send_document(
                    chat_id, document=input_file, caption=caption,
                    parse_mode="HTML",
                )

        elif media_type == "video":
            if file_size <= TELEGRAM_VIDEO_LIMIT:
                await bot.send_video(
                    chat_id, video=input_file, caption=caption,
                    parse_mode="HTML", duration=duration,
                    supports_streaming=True,
                )
            else:
                await bot.send_document(
                    chat_id, document=input_file, caption=caption,
                    parse_mode="HTML",
                )

        elif media_type == "photo":
            await bot.send_photo(
                chat_id, photo=input_file, caption=caption,
                parse_mode="HTML",
            )
        else:
            await bot.send_document(
                chat_id, document=input_file, caption=caption,
                parse_mode="HTML",
            )

        # Delete status message
        try:
            await status_msg.delete()
        except Exception:
            pass

        logger.info(f"Delivered {media_type} ({_format_size(file_size)}) to user {user_id}")

    finally:
        # Cleanup
        if platform == "youtube" and file_path:
            yt_downloader.cleanup(file_path)
        elif platform == "instagram" and result and result.get("download_dir"):
            ig_downloader.cleanup(result["download_dir"])

        if recompressed:
            media_processor._safe_remove(recompressed)


def _notify_admin_error(bot: Bot, user_id: int, url: str, error: str):
    """Send error report to admin (fire-and-forget)."""
    import asyncio

    async def _send():
        try:
            safe_error = html_lib.escape(error[:500])
            safe_url = html_lib.escape(url)
            await bot.send_message(
                ADMIN_ID,
                msg.ADMIN_ERROR_REPORT.format(user_id=user_id, url=safe_url, error=safe_error),
                parse_mode="HTML",
            )
        except Exception:
            pass

    asyncio.create_task(_send())


# ═══════════════════════════════════════════════════
# Text message handler (URL detection) — must be LAST
# ═══════════════════════════════════════════════════
@router.message(F.text)
async def handle_message(message: types.Message, bot: Bot):
    """Handle incoming text messages — detect URLs, show format buttons instantly."""
    text = message.text.strip()
    urls = extract_urls(text)

    if not urls:
        if message.chat.type == "private":
            await message.answer(msg.ERROR_INVALID_URL, parse_mode="HTML")
        return

    for url_info in urls:
        url = url_info["url"]
        platform = url_info["platform"]

        # Cache URL
        url_h = _url_hash(url)
        _cache_url(url_h, url)

        # Show format buttons INSTANTLY
        platform_icon = "▶️ YouTube" if platform == "youtube" else "📸 Instagram"
        caption = f"{platform_icon}\n\n{msg.CHOOSE_FORMAT}"
        keyboard = _make_format_keyboard(url_h)

        await message.answer(caption, parse_mode="HTML", reply_markup=keyboard)
