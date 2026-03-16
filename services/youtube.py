"""YouTube downloader — fetches all available qualities with sizes."""

import asyncio
import logging
import os
from pathlib import Path
from functools import partial
from concurrent.futures import ThreadPoolExecutor

import yt_dlp

from config import TEMP_DIR, MAX_RETRIES

logger = logging.getLogger(__name__)

# Dedicated thread pool for CPU-bound yt-dlp work (avoids GIL contention with bot)
_dl_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ytdl")

# Reusable base options — speed-tuned
_BASE_OPTS = {
    "noplaylist": True,
    "no_warnings": True,
    "quiet": True,
    "noprogress": True,
    "socket_timeout": 20,
    "retries": 5,
    "fragment_retries": 5,
    "concurrent_fragment_downloads": 12,
    "http_chunk_size": 10485760,
    "no_check_certificates": True,
    "geo_bypass": True,
    "extractor_args": {"youtube": {
        "skip": ["comments", "translated_subs"],
        "player_client": ["default", "tv_simply"],
    }},
    # Use aria2c for blazing fast parallel downloads (if available)
    "external_downloader": "aria2c",
    "external_downloader_args": {
        "aria2c": [
            "--min-split-size=1M",
            "--max-connection-per-server=16",
            "--max-concurrent-downloads=16",
            "--split=16",
        ],
    },
}

# Quality presets by height
QUALITY_PRESETS = [
    {"label": "144p",  "height": 144,  "icon": "⚡"},
    {"label": "240p",  "height": 240,  "icon": "⚡"},
    {"label": "360p",  "height": 360,  "icon": "📹"},
    {"label": "480p",  "height": 480,  "icon": "📹"},
    {"label": "720p",  "height": 720,  "icon": "🎬"},
    {"label": "1080p", "height": 1080, "icon": "🔥"},
]


class YouTubeDownloader:
    """Downloads videos and audio from YouTube using yt-dlp Python API."""

    def __init__(self):
        self.temp_dir = TEMP_DIR / "youtube"
        self.temp_dir.mkdir(exist_ok=True)
        self._aria2_available = self._check_aria2()

    @staticmethod
    def _check_aria2() -> bool:
        """Check if aria2c is available at startup."""
        import shutil
        return shutil.which("aria2c") is not None

    def _get_opts(self) -> dict:
        """Get base options, stripping aria2c if not available."""
        opts = {**_BASE_OPTS}
        if not self._aria2_available:
            opts.pop("external_downloader", None)
            opts.pop("external_downloader_args", None)
        return opts

    async def get_formats(self, url: str) -> dict:
        """Fetch all available qualities with sizes — for quality selection UI."""
        url = url.strip()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_dl_pool, partial(self._get_formats_sync, url))

    def _get_formats_sync(self, url: str) -> dict:
        """Sync: extract info and build list of available qualities."""
        opts = {**self._get_opts(), "skip_download": True}
        # Don't use aria2 for info extraction
        opts.pop("external_downloader", None)
        opts.pop("external_downloader_args", None)

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise Exception("Video ma'lumotlarini olishda xatolik")

            title = info.get("title", "Video")
            thumbnail = info.get("thumbnail")
            duration = info.get("duration") or 0
            uploader = info.get("uploader", "")
            formats = info.get("formats") or []

            # ── Collect best video format per height ──
            available = []
            best_audio_size = self._get_best_audio_size(formats)

            # Group video formats by height
            by_height: dict[int, dict] = {}
            for f in formats:
                h = f.get("height")
                vcodec = f.get("vcodec") or "none"
                if not h or vcodec == "none":
                    continue
                size = f.get("filesize") or f.get("filesize_approx") or 0
                # If video-only (no audio), add estimated audio size
                acodec = f.get("acodec") or "none"
                if acodec == "none":
                    size += best_audio_size

                # Keep largest size for this height (best bitrate)
                if h not in by_height or size > by_height[h].get("size", 0):
                    by_height[h] = {"size": size, "height": h}

            # Map to quality presets
            for preset in QUALITY_PRESETS:
                h = preset["height"]
                if h in by_height and by_height[h]["size"] > 0:
                    available.append({
                        "label": preset["label"],
                        "height": h,
                        "icon": preset["icon"],
                        "size": by_height[h]["size"],
                    })

            # If no format info, estimate from duration
            if not available and duration > 0:
                for preset in QUALITY_PRESETS:
                    bitrates = {144: 150_000, 240: 300_000, 360: 600_000,
                                480: 1_000_000, 720: 2_500_000, 1080: 5_000_000}
                    br = bitrates.get(preset["height"], 1_000_000)
                    size = int(duration * br / 8)
                    available.append({
                        "label": preset["label"],
                        "height": preset["height"],
                        "icon": preset["icon"],
                        "size": size,
                    })

            # ── Audio (MP3) size ──
            mp3_size = best_audio_size
            if mp3_size == 0 and duration > 0:
                mp3_size = int(duration * 16000)  # ~128kbps

            return {
                "title": title,
                "thumbnail": thumbnail,
                "duration": duration,
                "duration_str": self._format_duration(duration),
                "uploader": uploader,
                "qualities": available,
                "mp3_size": mp3_size,
            }

    def _get_best_audio_size(self, formats: list) -> int:
        """Find best audio-only format size."""
        audio_fmts = [
            f for f in formats
            if (f.get("acodec") or "none") != "none"
            and (f.get("vcodec") or "none") == "none"
        ]
        if audio_fmts:
            best = max(audio_fmts, key=lambda f: f.get("filesize") or f.get("filesize_approx") or 0)
            return best.get("filesize") or best.get("filesize_approx") or 0
        return 0

    async def download(self, url: str, audio_only: bool = False, height: int = 0) -> dict:
        """Download media. height=0 means best available."""
        url = url.strip()
        loop = asyncio.get_event_loop()
        if audio_only:
            return await loop.run_in_executor(_dl_pool, partial(self._download_audio, url))
        else:
            return await loop.run_in_executor(_dl_pool, partial(self._download_video, url, height))

    def _download_video(self, url: str, height: int = 0) -> dict:
        """Download video at specific height (or best)."""
        if height > 0:
            format_str = (
                f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}][ext=mp4]/"
                f"best[height<={height}]/best"
            )
        else:
            format_str = (
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                "bestvideo+bestaudio/"
                "best[ext=mp4]/best"
            )

        ydl_opts = {
            **self._get_opts(),
            "format": format_str,
            "outtmpl": str(self.temp_dir / "%(id)s.%(ext)s"),
            "merge_output_format": "mp4",
            "postprocessors": [],
        }
        return self._do_download(url, ydl_opts, "video")

    def _download_audio(self, url: str) -> dict:
        """Download audio only."""
        opts = self._get_opts()
        # Don't use aria2 for small audio files (overhead > benefit)
        opts.pop("external_downloader", None)
        opts.pop("external_downloader_args", None)

        ydl_opts = {
            **opts,
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/worst",
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

            # For merged videos, yt-dlp outputs .mp4
            if media_type == "video":
                mp4_path = Path(file_path).with_suffix(".mp4")
                if mp4_path.exists():
                    file_path = str(mp4_path)

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
