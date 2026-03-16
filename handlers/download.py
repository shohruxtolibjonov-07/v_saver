"""URL → platform-specific flow → download → send.

YouTube:  Link → quality buttons (144p-1080p + MP3) with sizes
Instagram: Link → [🎬 Video] [🎧 Audio] → instant download
"""

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

logger = logging.getLogger(__name__)
router = Router()

# Services
yt_downloader = YouTubeDownloader()
ig_downloader = InstagramDownloader()
media_processor = MediaProcessor()


# ─── URL cache ───────────────────────────────────
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
    if size_bytes <= 0:
        return ""
    elif size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# ─── Keyboards ───────────────────────────────────

def _make_ig_keyboard(url_hash: str) -> InlineKeyboardMarkup:
    """Instagram: simple Video / Audio buttons."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎬 Video", callback_data=f"ig:v:{url_hash}"),
            InlineKeyboardButton(text="🎧 Audio", callback_data=f"ig:a:{url_hash}"),
        ]
    ])


def _make_yt_quality_keyboard(url_hash: str, qualities: list, mp3_size: int) -> InlineKeyboardMarkup:
    """YouTube: quality buttons with sizes (3 per row). Warns if >50MB."""
    limit = TELEGRAM_DOCUMENT_LIMIT
    rows = []
    row = []
    for q in qualities:
        size_str = _format_size(q["size"])
        # Show warning icon if estimated size > Telegram limit
        over_limit = q["size"] > limit and q["size"] > 0
        icon = "⚠️" if over_limit else q["icon"]
        label = f"{icon} {q['label']}"
        if size_str:
            label += f":  {size_str}"
        callback = f"yt:{q['height']}:{url_hash}"
        row.append(InlineKeyboardButton(text=label, callback_data=callback))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    # MP3 button
    mp3_size_str = _format_size(mp3_size)
    mp3_label = f"🎧 MP3"
    if mp3_size_str:
        mp3_label += f":  {mp3_size_str}"
    rows.append([InlineKeyboardButton(text=mp3_label, callback_data=f"yt:mp3:{url_hash}")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


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
            message.chat.id, audio=input_file,
            caption=caption + f"\n\n@{BOT_USERNAME}",
            parse_mode="HTML", title=audio_result["title"][:64],
        )
        try:
            await status_msg.delete()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Audio extraction error: {e}")
        err = msg.ERROR_FFMPEG_MISSING if "FFMPEG" in str(e) else msg.ERROR_GENERIC
        try:
            await status_msg.edit_text(err, parse_mode="HTML")
        except Exception:
            await message.answer(err, parse_mode="HTML")

    finally:
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except Exception:
                pass
        if audio_result and audio_result.get("file_path"):
            media_processor._safe_remove(audio_result["file_path"])


# ═══════════════════════════════════════════════════
# Instagram callback: ig:v:hash / ig:a:hash
# ═══════════════════════════════════════════════════
@router.callback_query(F.data.startswith("ig:"))
async def handle_ig_callback(callback: CallbackQuery, bot: Bot):
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

    # Show download progress
    dl_text = msg.DOWNLOADING_AUDIO if is_audio else msg.DOWNLOADING_VIDEO
    try:
        await callback.message.edit_text(dl_text, parse_mode="HTML")
    except Exception:
        pass

    # Download and send directly
    download_dir = None
    try:
        await bot.send_chat_action(callback.message.chat.id, ChatAction.UPLOAD_VIDEO)

        result = await ig_downloader.download(url, audio_only=is_audio)
        download_dir = result.get("download_dir")

        if not result["files"]:
            try:
                await callback.message.edit_text(msg.ERROR_NOT_FOUND, parse_mode="HTML")
            except Exception:
                pass
            return

        title = result.get("title", "Instagram media")

        for file_info in result["files"]:
            file_path = file_info["file_path"]
            file_size = file_info["file_size"]
            media_type = file_info["media_type"]
            if is_audio:
                media_type = "audio"

            if file_size > TELEGRAM_DOCUMENT_LIMIT:
                await bot.send_message(
                    callback.message.chat.id,
                    msg.ERROR_FILE_TOO_LARGE, parse_mode="HTML",
                )
                continue

            caption = _make_caption(title, "", file_size, media_type)
            input_file = FSInputFile(file_path)

            await bot.send_chat_action(callback.message.chat.id, ChatAction.UPLOAD_VIDEO)

            if media_type == "audio":
                if file_size <= TELEGRAM_VIDEO_LIMIT:
                    await bot.send_audio(
                        callback.message.chat.id, audio=input_file,
                        caption=caption, parse_mode="HTML",
                    )
                else:
                    await bot.send_document(
                        callback.message.chat.id, document=input_file,
                        caption=caption, parse_mode="HTML",
                    )
            elif media_type == "video":
                if file_size <= TELEGRAM_VIDEO_LIMIT:
                    await bot.send_video(
                        callback.message.chat.id, video=input_file,
                        caption=caption, parse_mode="HTML",
                        supports_streaming=True,
                    )
                else:
                    await bot.send_document(
                        callback.message.chat.id, document=input_file,
                        caption=caption, parse_mode="HTML",
                    )
            elif media_type == "photo":
                await bot.send_photo(
                    callback.message.chat.id, photo=input_file,
                    caption=caption, parse_mode="HTML",
                )
            else:
                await bot.send_document(
                    callback.message.chat.id, document=input_file,
                    caption=caption, parse_mode="HTML",
                )

        try:
            await callback.message.delete()
        except Exception:
            pass

        logger.info(f"Instagram media delivered to user {callback.from_user.id}")

    except Exception as e:
        error_text = str(e)
        logger.error(f"Instagram download error: {error_text}")

        if "PRIVATE_ACCOUNT" in error_text:
            err = msg.ERROR_INSTAGRAM_PRIVATE
        elif "STORY_LOGIN" in error_text:
            err = msg.ERROR_INSTAGRAM_STORY
        elif "LOGIN_REQUIRED" in error_text:
            err = "🔒 Bu kontentni yuklab olish uchun Instagram login talab qiladi.\nOmmaviy postlar va reels'larni yuboring."
        elif "RATE_LIMITED" in error_text:
            err = "⏱ Instagram vaqtinchalik cheklov qo'ydi. Iltimos, bir necha daqiqadan keyin qayta urinib ko'ring."
        elif "CONTENT_NOT_AVAILABLE" in error_text:
            err = "🔍 Bu kontent mavjud emas yoki o'chirilgan."
        else:
            err = msg.ERROR_DOWNLOAD_FAILED

        try:
            await callback.message.edit_text(err, parse_mode="HTML")
        except Exception:
            pass
        _notify_admin_error(bot, callback.from_user.id, url, error_text)

    finally:
        if download_dir:
            ig_downloader.cleanup(download_dir)


# ═══════════════════════════════════════════════════
# YouTube callback: yt:<height>:hash / yt:mp3:hash
# ═══════════════════════════════════════════════════
@router.callback_query(F.data.startswith("yt:"))
async def handle_yt_callback(callback: CallbackQuery, bot: Bot):
    await callback.answer()

    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        return

    _, height_or_mp3, url_hash = parts

    url = _get_cached_url(url_hash)
    if not url:
        try:
            await callback.message.edit_text(msg.ERROR_LINK_EXPIRED, parse_mode="HTML")
        except Exception:
            pass
        return

    is_audio = (height_or_mp3 == "mp3")
    height = 0 if is_audio else int(height_or_mp3)
    quality_label = "MP3" if is_audio else f"{height}p"

    try:
        await callback.message.edit_text(f"⏳ {quality_label} yuklanmoqda...", parse_mode="HTML")
    except Exception:
        pass

    file_path = None
    try:
        await bot.send_chat_action(callback.message.chat.id, ChatAction.UPLOAD_VIDEO)

        result = await yt_downloader.download(url, audio_only=is_audio, height=height)
        file_path = result["file_path"]
        title = result["title"]
        duration_str = result.get("duration_str", "")
        duration = result.get("duration")
        media_type = result["media_type"]
        file_size = result["file_size"]

        if file_size > TELEGRAM_DOCUMENT_LIMIT:
            size_str = _format_size(file_size)
            try:
                await callback.message.edit_text(
                    f"⚠️ Fayl juda katta: <b>{size_str}</b>\n"
                    f"Telegram limiti: 50 MB\n\n"
                    f"💡 Kichikroq sifatni tanlang yoki 🎧 MP3 ni bosing.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return

        caption = _make_caption(title, duration_str, file_size, media_type)
        input_file = FSInputFile(file_path)

        await bot.send_chat_action(callback.message.chat.id,
                                   ChatAction.UPLOAD_VOICE if is_audio else ChatAction.UPLOAD_VIDEO)

        if media_type == "audio":
            if file_size <= TELEGRAM_VIDEO_LIMIT:
                await bot.send_audio(
                    callback.message.chat.id, audio=input_file,
                    caption=caption, parse_mode="HTML",
                    title=title[:64], duration=duration,
                )
            else:
                await bot.send_document(
                    callback.message.chat.id, document=input_file,
                    caption=caption, parse_mode="HTML",
                )
        elif media_type == "video":
            if file_size <= TELEGRAM_VIDEO_LIMIT:
                await bot.send_video(
                    callback.message.chat.id, video=input_file,
                    caption=caption, parse_mode="HTML",
                    duration=duration, supports_streaming=True,
                )
            else:
                await bot.send_document(
                    callback.message.chat.id, document=input_file,
                    caption=caption, parse_mode="HTML",
                )
        else:
            await bot.send_document(
                callback.message.chat.id, document=input_file,
                caption=caption, parse_mode="HTML",
            )

        try:
            await callback.message.delete()
        except Exception:
            pass

        logger.info(f"YouTube {quality_label} ({_format_size(file_size)}) delivered to user {callback.from_user.id}")

    except Exception as e:
        error_text = str(e)
        logger.error(f"YouTube download error: {error_text}")
        try:
            await callback.message.edit_text(msg.ERROR_DOWNLOAD_FAILED, parse_mode="HTML")
        except Exception:
            pass
        _notify_admin_error(bot, callback.from_user.id, url, error_text)

    finally:
        if file_path:
            yt_downloader.cleanup(file_path)


# ═══════════════════════════════════════════════════
# Admin error notification
# ═══════════════════════════════════════════════════
def _notify_admin_error(bot: Bot, user_id: int, url: str, error: str):
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
# Text message handler (URL detection) — LAST
# ═══════════════════════════════════════════════════
@router.message(F.text)
async def handle_message(message: types.Message, bot: Bot):
    """Detect URLs → show YouTube quality buttons OR Instagram Video/Audio buttons."""
    text = message.text.strip()
    urls = extract_urls(text)

    if not urls:
        if message.chat.type == "private":
            await message.answer(msg.ERROR_INVALID_URL, parse_mode="HTML")
        return

    for url_info in urls:
        url = url_info["url"]
        platform = url_info["platform"]

        url_h = _url_hash(url)
        _cache_url(url_h, url)

        if platform == "instagram":
            # ── Instagram: instant Video/Audio buttons ──
            keyboard = _make_ig_keyboard(url_h)
            await message.answer(
                "📸 Instagram\n\nYuklab olish formatini tanlang ↓",
                parse_mode="HTML", reply_markup=keyboard,
            )

        else:
            # ── YouTube: fetch formats, show quality buttons ──
            status_msg = await message.answer(msg.FETCHING_FORMATS, parse_mode="HTML")

            try:
                formats = await yt_downloader.get_formats(url)
                qualities = formats.get("qualities", [])
                mp3_size = formats.get("mp3_size", 0)
                title = formats.get("title", "Video")

                if not qualities:
                    qualities = [{"label": "Video", "height": 0, "icon": "🎬", "size": 0}]

                keyboard = _make_yt_quality_keyboard(url_h, qualities, mp3_size)
                header = msg.QUALITY_HEADER.format(title=html_lib.escape(title[:100]))

                try:
                    await status_msg.edit_text(header, parse_mode="HTML", reply_markup=keyboard)
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"YouTube format fetch error: {e}")
                try:
                    await status_msg.edit_text(msg.ERROR_DOWNLOAD_FAILED, parse_mode="HTML")
                except Exception:
                    pass
                _notify_admin_error(bot, message.from_user.id, url, str(e))
