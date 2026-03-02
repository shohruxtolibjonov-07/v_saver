import asyncio
import logging
import os
import uuid
from pathlib import Path
from functools import partial

import yt_dlp

from config import TEMP_DIR

logger = logging.getLogger(__name__)


class InstagramDownloader:
    """Downloads media from Instagram using yt-dlp Python API."""

    def __init__(self):
        self.temp_dir = TEMP_DIR / "instagram"
        self.temp_dir.mkdir(exist_ok=True)

    async def get_info(self, url: str) -> dict:
        """Fetch only metadata (title, thumbnail) without downloading — very fast."""
        url = url.strip()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._get_info_sync, url))

    def _get_info_sync(self, url: str) -> dict:
        """Synchronous metadata fetch."""
        opts = {
            "noplaylist": True,
            "no_warnings": True,
            "quiet": True,
            "socket_timeout": 30,
            "retries": 5,
            "skip_download": True,
            "no_check_certificates": True,
            "geo_bypass": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return {"title": "Instagram media", "thumbnail": None}
                return {
                    "title": info.get("title", "Instagram media"),
                    "thumbnail": info.get("thumbnail"),
                    "duration": info.get("duration") or 0,
                    "uploader": info.get("uploader", ""),
                }
        except Exception as e:
            logger.warning(f"Instagram info fetch failed: {e}")
            return {"title": "Instagram media", "thumbnail": None, "duration": 0, "uploader": ""}

    async def download(self, url: str, audio_only: bool = False) -> dict:
        """Download media from Instagram. Returns dict with files list."""
        url = url.strip()
        content_type = self._detect_content_type(url)

        # Stories require login — give clear error
        if content_type == "story":
            raise Exception("STORY_LOGIN_REQUIRED")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(self._download_with_ytdlp, url, content_type, audio_only)
        )

    def _detect_content_type(self, url: str) -> str:
        if "/stories/" in url:
            return "story"
        if "/reel/" in url or "/reels/" in url:
            return "reel"
        elif "/p/" in url:
            return "post"
        elif "/tv/" in url:
            return "tv"
        return "unknown"

    def _download_with_ytdlp(self, url: str, content_type: str, audio_only: bool = False) -> dict:
        """Download Instagram content using yt-dlp Python API."""
        download_id = str(uuid.uuid4())[:8]
        download_dir = self.temp_dir / download_id
        download_dir.mkdir(exist_ok=True)

        output_template = str(download_dir / "%(id)s.%(ext)s")

        ydl_opts = {
            "outtmpl": output_template,
            "noplaylist": True,
            "no_warnings": True,
            "quiet": True,
            "socket_timeout": 30,
            "retries": 5,
            "fragment_retries": 3,
            "noprogress": True,
            "http_chunk_size": 10485760,
            "no_check_certificates": True,
            "geo_bypass": True,
        }

        # Audio-only mode — no ffmpeg needed, download native format
        if audio_only:
            ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best"
            # No postprocessors — we send the native audio file directly

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise Exception("Instagram ma'lumotlarini olishda xatolik")
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e).lower()
            if "login" in error_msg or "private" in error_msg:
                raise Exception("PRIVATE_ACCOUNT")
            raise

        # Collect all downloaded files
        files = []
        for f in download_dir.iterdir():
            if f.is_file():
                media_type = self._detect_media_type(f.suffix)
                # If audio_only and we got mp3, mark it audio
                if audio_only and f.suffix.lower() == ".mp3":
                    media_type = "audio"
                files.append({
                    "file_path": str(f),
                    "file_size": os.path.getsize(f),
                    "file_size_str": self._format_size(os.path.getsize(f)),
                    "media_type": media_type,
                    "filename": f.name,
                })

        if not files:
            raise Exception("Hech qanday fayl yuklab olinmadi")

        title = info.get("title", "Instagram media")

        return {
            "files": files,
            "title": title,
            "content_type": content_type,
            "file_count": len(files),
            "download_dir": str(download_dir),
        }

    def _detect_media_type(self, extension: str) -> str:
        ext = extension.lower()
        if ext in (".mp4", ".mkv", ".webm", ".avi", ".mov"):
            return "video"
        elif ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            return "photo"
        elif ext in (".mp3", ".m4a", ".ogg", ".wav", ".aac"):
            return "audio"
        return "document"

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.1f} MB"

    def cleanup(self, download_dir: str):
        import shutil
        try:
            if download_dir and os.path.exists(download_dir):
                shutil.rmtree(download_dir)
        except Exception as e:
            logger.warning(f"Instagram cleanup error: {e}")
