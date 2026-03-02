import re
import os
import logging
import hashlib
import time
import html as html_lib

from aiogram import Router, types, Bot, F
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ChatAction

from config import ADMIN_ID, MAX_TELEGRAM_FILE_SIZE, TEMP_DIR
from utils import messages as msg
from services.youtube import YouTubeDownloader
from services.instagram import InstagramDownloader
from services.media import MediaProcessor

logger = logging.getLogger(__name__)
router = Router()

# Services
yt_downloader = YouTubeDownloader()
ig_downloader = InstagramDownloader()
media_processor = MediaProcessor()

# URL-to-hash cache with TTL (prevents memory leak on long-running server)
_URL_CACHE_TTL = 3600  # 1 hour
_url_cache: dict[str, tuple[str, float]] = {}  # hash -> (url, timestamp)


def _cache_url(url_hash: str, url: str):
    """Store URL in cache with timestamp."""
    # Evict expired entries every 100 items to prevent unbounded growth
    if len(_url_cache) > 500:
        now = time.time()
        expired = [k for k, (_, ts) in _url_cache.items() if now - ts > _URL_CACHE_TTL]
        for k in expired:
            del _url_cache[k]
    _url_cache[url_hash] = (url, time.time())


def _get_cached_url(url_hash: str) -> str | None:
    """Get URL from cache, returns None if expired or missing."""
    entry = _url_cache.get(url_hash)
    if not entry:
        return None
    url, ts = entry
    if time.time() - ts > _URL_CACHE_TTL:
        del _url_cache[url_hash]
        return None
    return url


# URL patterns
YOUTUBE_RE = re.compile(
    r'(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be)/(watch\?[^\s]+|shorts/[\w\-]+[^\s]*|embed/[\w\-]+|v/[\w\-]+|live/[\w\-]+|[\w\-]{11})',
    re.IGNORECASE
)
INSTAGRAM_RE = re.compile(
    r'(https?://)?(www\.)?(instagram\.com|instagr\.am)/(p|reel|reels|stories|tv)/[\w\-/]+',
    re.IGNORECASE
)


def extract_urls(text: str) -> list[dict]:
    """Extract YouTube and Instagram URLs from text."""
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
    """Create a short hash for URL to use in callback data."""
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _make_format_keyboard(url_hash: str) -> InlineKeyboardMarkup:
    """Create inline keyboard with Video and Audio buttons."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎬 Video", callback_data=f"dl:v:{url_hash}"),
            InlineKeyboardButton(text="🎧 Audio", callback_data=f"dl:a:{url_hash}"),
        ]
    ])


# ──────────────────────────────────────────────
# Video-to-Audio extraction handler
# ──────────────────────────────────────────────
@router.message(F.video | F.document.func(lambda d: d and d.mime_type and d.mime_type.startswith("video/")))
async def handle_video_message(message: types.Message, bot: Bot):
    """When user sends a video file, extract audio from it."""
    video = message.video or message.document

    if not video:
        return

    # Check file size (Telegram API allows downloading up to 20 MB for bots)
    file_size = video.file_size or 0
    if file_size > 20 * 1024 * 1024:
        await message.answer(msg.AUDIO_EXTRACT_TOO_LARGE, parse_mode="HTML")
        return

    # Show status
    status_msg = await message.answer(msg.AUDIO_EXTRACTING, parse_mode="HTML")

    video_path = None
    audio_result = None

    try:
        # Download the video from Telegram
        await bot.send_chat_action(message.chat.id, ChatAction.RECORD_VOICE)

        file = await bot.get_file(video.file_id)
        video_dir = TEMP_DIR / "video_extract"
        video_dir.mkdir(exist_ok=True)

        # Use original filename or generate one
        if hasattr(video, "file_name") and video.file_name:
            ext = os.path.splitext(video.file_name)[1] or ".mp4"
            filename = f"{video.file_unique_id}{ext}"
        else:
            filename = f"{video.file_unique_id}.mp4"

        video_path = str(video_dir / filename)
        await bot.download_file(file.file_path, video_path)

        # Extract audio
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VOICE)

        title = "audio"
        if message.caption:
            title = message.caption[:50]
        elif hasattr(video, "file_name") and video.file_name:
            title = os.path.splitext(video.file_name)[0][:50]

        audio_result = await media_processor.extract_audio_from_video(video_path, title)

        # Send the audio file
        input_file = FSInputFile(audio_result["file_path"])
        caption = msg.AUDIO_EXTRACT_SUCCESS.format(
            title=html_lib.escape(audio_result["title"]),
            size=_format_size(audio_result["file_size"]),
        )

        await bot.send_audio(
            message.chat.id,
            audio=input_file,
            caption=caption,
            parse_mode="HTML",
            title=audio_result["title"][:64],
        )

        # Delete status message
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
        # Cleanup
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except Exception:
                pass
        if audio_result and audio_result.get("file_path"):
            media_processor._safe_remove(audio_result["file_path"])


# ──────────────────────────────────────────────
# Callback query handler — when user presses Video or Audio button
# ──────────────────────────────────────────────
@router.callback_query(F.data.startswith("dl:"))
async def handle_download_callback(callback: CallbackQuery, bot: Bot):
    """Handle inline button press — download video or audio."""
    await callback.answer()  # Remove "loading" spinner on button

    data = callback.data  # e.g. "dl:v:abc123def456"
    parts = data.split(":", 2)
    if len(parts) != 3:
        return

    _, mode, url_hash = parts
    is_audio = (mode == "a")

    # Look up the URL from cache
    url = _get_cached_url(url_hash)
    if not url:
        try:
            await callback.message.edit_text(
                msg.ERROR_LINK_EXPIRED, parse_mode="HTML"
            )
        except Exception:
            pass
        return

    # Determine platform
    platform = "youtube" if YOUTUBE_RE.search(url) else "instagram"

    # Update message to show download status
    status_text = msg.DOWNLOADING_AUDIO if is_audio else msg.DOWNLOADING_VIDEO
    try:
        await callback.message.edit_text(status_text, parse_mode="HTML")
    except Exception:
        pass

    try:
        await bot.send_chat_action(callback.message.chat.id, ChatAction.UPLOAD_VIDEO)

        if platform == "youtube":
            await _process_youtube_direct(bot, callback.message.chat.id, callback.from_user.id, url, is_audio, callback.message)
        else:
            await _process_instagram_direct(bot, callback.message.chat.id, callback.from_user.id, url, is_audio, callback.message)

    except Exception as e:
        error_text = str(e)
        logger.error(f"Download error for {url}: {error_text}")

        try:
            await callback.message.edit_text(msg.ERROR_DOWNLOAD_FAILED, parse_mode="HTML")
        except Exception:
            pass

        # Notify admin
        try:
            safe_error = html_lib.escape(error_text[:500])
            safe_url = html_lib.escape(url)
            await bot.send_message(
                ADMIN_ID,
                msg.ADMIN_ERROR_REPORT.format(
                    user_id=callback.from_user.id, url=safe_url, error=safe_error
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass


# ──────────────────────────────────────────────
# Direct download processors (no queue)
# ──────────────────────────────────────────────
async def _process_youtube_direct(bot: Bot, chat_id: int, user_id: int, url: str, is_audio: bool, status_msg: types.Message):
    """Process YouTube download directly (no queue)."""
    processed = None
    file_path = None

    try:
        result = await yt_downloader.download(url, audio_only=is_audio)
        file_path = result["file_path"]

        processed = await media_processor.process_for_telegram(file_path, result["media_type"])

        if processed["file_size"] > MAX_TELEGRAM_FILE_SIZE:
            try:
                await status_msg.edit_text(msg.ERROR_FILE_TOO_LARGE, parse_mode="HTML")
            except Exception:
                await bot.send_message(chat_id, msg.ERROR_FILE_TOO_LARGE, parse_mode="HTML")
            return

        await bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)

        dur = result.get("duration_str", "")
        caption = f"🎬 <b>{html_lib.escape(result['title'][:200])}</b>"
        if dur:
            caption += f"\n⏱ {dur}"

        input_file = FSInputFile(processed["file_path"])

        if result["media_type"] == "audio":
            await bot.send_audio(
                chat_id, audio=input_file, caption=caption,
                parse_mode="HTML", title=result["title"][:64],
                duration=result.get("duration"),
            )
        else:
            await bot.send_video(
                chat_id, video=input_file, caption=caption,
                parse_mode="HTML", duration=result.get("duration"),
                supports_streaming=True,
            )

        # Delete status message
        try:
            await status_msg.delete()
        except Exception:
            pass

    finally:
        if file_path:
            yt_downloader.cleanup(file_path)
        if processed and processed.get("file_path") != file_path:
            media_processor._safe_remove(processed["file_path"])


async def _process_instagram_direct(bot: Bot, chat_id: int, user_id: int, url: str, is_audio: bool, status_msg: types.Message):
    """Process Instagram download directly (no queue)."""
    download_dir = None

    try:
        result = await ig_downloader.download(url, audio_only=is_audio)
        download_dir = result.get("download_dir")

        if not result["files"]:
            try:
                await status_msg.edit_text(msg.ERROR_NOT_FOUND, parse_mode="HTML")
            except Exception:
                await bot.send_message(chat_id, msg.ERROR_NOT_FOUND, parse_mode="HTML")
            return

        await bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)

        for file_info in result["files"]:
            file_path = file_info["file_path"]

            processed = await media_processor.process_for_telegram(file_path, file_info["media_type"])

            if processed["file_size"] > MAX_TELEGRAM_FILE_SIZE:
                await bot.send_message(chat_id, msg.ERROR_FILE_TOO_LARGE, parse_mode="HTML")
                continue

            input_file = FSInputFile(processed["file_path"])

            caption = f"🎬 <b>{html_lib.escape(result.get('title', 'Instagram media')[:200])}</b>"

            if file_info["media_type"] == "audio":
                await bot.send_audio(chat_id, audio=input_file, caption=caption, parse_mode="HTML")
            elif file_info["media_type"] == "video":
                await bot.send_video(chat_id, video=input_file, caption=caption, parse_mode="HTML", supports_streaming=True)
            elif file_info["media_type"] == "photo":
                await bot.send_photo(chat_id, photo=input_file, caption=caption, parse_mode="HTML")
            else:
                await bot.send_document(chat_id, document=input_file, caption=caption, parse_mode="HTML")

            if processed.get("file_path") != file_path:
                media_processor._safe_remove(processed["file_path"])

        # Delete status message
        try:
            await status_msg.delete()
        except Exception:
            pass

    except Exception as e:
        error_text = str(e)
        if "STORY_LOGIN_REQUIRED" in error_text:
            try:
                await status_msg.edit_text(msg.ERROR_INSTAGRAM_STORY, parse_mode="HTML")
            except Exception:
                await bot.send_message(chat_id, msg.ERROR_INSTAGRAM_STORY, parse_mode="HTML")
        elif "PRIVATE_ACCOUNT" in error_text or "private" in error_text.lower() or "login" in error_text.lower():
            try:
                await status_msg.edit_text(msg.ERROR_INSTAGRAM_PRIVATE, parse_mode="HTML")
            except Exception:
                await bot.send_message(chat_id, msg.ERROR_INSTAGRAM_PRIVATE, parse_mode="HTML")
        else:
            raise

    finally:
        if download_dir:
            ig_downloader.cleanup(download_dir)


# ──────────────────────────────────────────────
# Text message handler (URL detection) — must be LAST
# ──────────────────────────────────────────────
@router.message(F.text)
async def handle_message(message: types.Message, bot: Bot):
    """Handle incoming text messages — detect URLs, show inline buttons instantly."""
    text = message.text.strip()
    urls = extract_urls(text)

    if not urls:
        if message.chat.type == "private":
            await message.answer(msg.ERROR_INVALID_URL, parse_mode="HTML")
        return

    for url_info in urls:
        url = url_info["url"]
        platform = url_info["platform"]

        # Store URL in cache for callback handler
        url_h = _url_hash(url)
        _cache_url(url_h, url)

        # Show buttons INSTANTLY — no metadata fetch, no waiting
        platform_icon = "▶️ YouTube" if platform == "youtube" else "📸 Instagram"
        caption = f"{platform_icon}\n\n{msg.CHOOSE_FORMAT}"
        keyboard = _make_format_keyboard(url_h)

        await message.answer(
            caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
