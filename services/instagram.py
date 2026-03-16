"""Instagram downloader — simplified, no quality selection needed."""

import asyncio
import logging
import os
import uuid
from pathlib import Path
from functools import partial
from concurrent.futures import ThreadPoolExecutor

import yt_dlp

from config import TEMP_DIR

logger = logging.getLogger(__name__)

# Dedicated thread pool for Instagram downloads
_ig_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="igdl")


class InstagramDownloader:
    """Downloads media from Instagram using yt-dlp."""

    def __init__(self):
        self.temp_dir = TEMP_DIR / "instagram"
        self.temp_dir.mkdir(exist_ok=True)

    async def download(self, url: str, audio_only: bool = False) -> dict:
        """Download media from Instagram."""
        url = url.strip()
        content_type = self._detect_content_type(url)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _ig_pool, partial(self._download_sync, url, content_type, audio_only)
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

    def _download_sync(self, url: str, content_type: str, audio_only: bool = False) -> dict:
        """Download Instagram content."""
        download_id = str(uuid.uuid4())[:8]
        download_dir = self.temp_dir / download_id
        download_dir.mkdir(exist_ok=True)

        output_template = str(download_dir / "%(id)s.%(ext)s")

        ydl_opts = {
            "outtmpl": output_template,
            "noplaylist": True,
            "no_warnings": True,
            "quiet": True,
            "socket_timeout": 20,
            "retries": 5,
            "fragment_retries": 5,
            "concurrent_fragment_downloads": 8,
            "noprogress": True,
            "http_chunk_size": 10485760,
            "no_check_certificates": True,
            "geo_bypass": True,
        }

        if audio_only:
            ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best"

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise Exception("Instagram ma'lumotlarini olishda xatolik")
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e).lower()
            # Only flag as private if clearly stated
            if "login required" in error_msg and "private" in error_msg:
                raise Exception("PRIVATE_ACCOUNT")
            if "story" in error_msg and "login" in error_msg:
                raise Exception("STORY_LOGIN_REQUIRED")
            # Re-raise all other download errors as-is
            raise Exception(f"Instagram yuklab olishda xatolik: {str(e)[:200]}")

        # Collect downloaded files
        files = []
        for f in download_dir.iterdir():
            if f.is_file():
                media_type = self._detect_media_type(f.suffix)
                if audio_only:
                    media_type = "audio"
                files.append({
                    "file_path": str(f),
                    "file_size": os.path.getsize(f),
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

    def cleanup(self, download_dir: str):
        import shutil
        try:
            if download_dir and os.path.exists(download_dir):
                shutil.rmtree(download_dir)
        except Exception as e:
            logger.warning(f"Instagram cleanup error: {e}")
