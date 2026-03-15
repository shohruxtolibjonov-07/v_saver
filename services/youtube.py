"""YouTube downloader with format selection and retry support."""

import asyncio
import logging
import os
from pathlib import Path
from functools import partial
from typing import Optional

import yt_dlp

from config import TEMP_DIR, MAX_RETRIES

logger = logging.getLogger(__name__)

# Reusable base options for maximum speed
_BASE_OPTS = {
    "noplaylist": True,
    "no_warnings": True,
    "quiet": True,
    "noprogress": True,
    "socket_timeout": 30,
    "retries": 3,
    "fragment_retries": 3,
    "concurrent_fragment_downloads": 8,
    "http_chunk_size": 10485760,  # 10 MB chunks
    "no_check_certificates": True,
    "geo_bypass": True,
    "extractor_args": {"youtube": {
        "skip": ["comments", "translated_subs"],
        "player_client": ["android"],
    }},
}


class YouTubeDownloader:
    """Downloads videos and audio from YouTube using yt-dlp Python API."""

    def __init__(self):
        self.temp_dir = TEMP_DIR / "youtube"
        self.temp_dir.mkdir(exist_ok=True)

    async def get_info(self, url: str) -> dict:
        """Fetch metadata (title, size, formats) without downloading."""
        url = url.strip()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._get_info_sync, url))

    def _get_info_sync(self, url: str) -> dict:
        """Synchronous metadata + estimated size fetch."""
        opts = {
            **_BASE_OPTS,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise Exception("Video ma'lumotlarini olishda xatolik")

            # Estimate best video size
            best_video_size = self._estimate_size(info, audio_only=False)
            best_audio_size = self._estimate_size(info, audio_only=True)

            return {
                "title": info.get("title", "Video"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration") or 0,
                "duration_str": self._format_duration(info.get("duration") or 0),
                "uploader": info.get("uploader", ""),
                "video_size": best_video_size,
                "audio_size": best_audio_size,
            }

    def _estimate_size(self, info: dict, audio_only: bool = False) -> int:
        """Estimate file size from format info."""
        formats = info.get("formats", [])
        if not formats:
            # Fallback: estimate from duration and bitrate
            duration = info.get("duration") or 0
            if audio_only:
                return int(duration * 16000)  # ~128kbps
            return int(duration * 500000)  # ~4Mbps

        if audio_only:
            # Find best audio format size
            audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") in (None, "none")]
            if audio_formats:
                best = max(audio_formats, key=lambda f: f.get("filesize") or f.get("filesize_approx") or 0)
                return best.get("filesize") or best.get("filesize_approx") or 0
        else:
            # Find best combined format size
            # Try filesize first
            if info.get("filesize"):
                return info["filesize"]
            if info.get("filesize_approx"):
                return info["filesize_approx"]

            # Check best format
            best_formats = [f for f in formats if f.get("ext") == "mp4" and f.get("vcodec") != "none"]
            if best_formats:
                best = max(best_formats, key=lambda f: (f.get("height") or 0))
                size = best.get("filesize") or best.get("filesize_approx") or 0
                # If combined format (has audio), return as-is
                if best.get("acodec") != "none":
                    return size
                # If video-only, add estimated audio size
                audio_size = self._estimate_size(info, audio_only=True)
                return size + audio_size

        return 0

    async def download(self, url: str, audio_only: bool = False, quality: str = "best") -> dict:
        """Download media from YouTube."""
        url = url.strip()
        loop = asyncio.get_event_loop()
        if audio_only:
            return await loop.run_in_executor(None, partial(self._download_audio, url))
        else:
            return await loop.run_in_executor(None, partial(self._download_video, url, quality))

    def _download_video(self, url: str, quality: str = "best") -> dict:
        """Download video — format depends on quality choice."""
        format_str = self._get_video_format(quality)

        ydl_opts = {
            **_BASE_OPTS,
            "format": format_str,
            "outtmpl": str(self.temp_dir / "%(id)s.%(ext)s"),
            "merge_output_format": "mp4",
            "postprocessors": [],
        }
        return self._do_download(url, ydl_opts, "video")

    def _get_video_format(self, quality: str) -> str:
        """Get yt-dlp format string for quality level."""
        if quality == "low":
            return "best[ext=mp4][height<=360]/best[height<=360]/worst[ext=mp4]/worst"
        elif quality == "medium":
            return "best[ext=mp4][height<=480]/best[ext=mp4][height<=720]/best[height<=480]/best"
        else:  # "best"
            return "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"

    def _download_audio(self, url: str) -> dict:
        """Download audio only — native format, no ffmpeg."""
        ydl_opts = {
            **_BASE_OPTS,
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
            "outtmpl": str(self.temp_dir / "%(id)s.%(ext)s"),
            "postprocessors": [],
        }
        return self._do_download(url, ydl_opts, "audio")

    def _do_download(self, url: str, ydl_opts: dict, media_type: str) -> dict:
        """Execute download."""
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise Exception("Video ma'lumotlarini olishda xatolik")

            title = info.get("title", "video")
            duration = info.get("duration") or 0
            video_id = info.get("id", "unknown")

            file_path = ydl.prepare_filename(info)

            # For audio, check native audio extensions
            if media_type == "audio":
                for ext in [".m4a", ".webm", ".ogg", ".mp3"]:
                    alt_path = Path(file_path).with_suffix(ext)
                    if alt_path.exists():
                        file_path = str(alt_path)
                        break

            # Fallback: search by video ID
            if not os.path.exists(file_path):
                for f in self.temp_dir.iterdir():
                    if video_id in f.name and f.is_file():
                        file_path = str(f)
                        break

            if not os.path.exists(file_path):
                raise Exception("Yuklab olingan fayl topilmadi")

            return {
                "file_path": file_path,
                "title": title,
                "duration": duration,
                "duration_str": self._format_duration(duration),
                "file_size": os.path.getsize(file_path),
                "media_type": media_type,
            }

    @staticmethod
    def _format_duration(seconds: int) -> str:
        if not seconds:
            return ""
        h, r = divmod(seconds, 3600)
        m, s = divmod(r, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    def cleanup(self, file_path: str):
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
