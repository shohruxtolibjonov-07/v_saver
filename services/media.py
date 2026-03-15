"""Media processing — recompression and audio extraction."""

import asyncio
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

from config import TEMP_DIR

logger = logging.getLogger(__name__)


class MediaProcessor:
    """Handles media recompression and audio extraction."""

    def __init__(self):
        self.temp_dir = TEMP_DIR / "processed"
        self.temp_dir.mkdir(exist_ok=True)
        self._ffmpeg_available: Optional[bool] = None

    async def check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available (cached)."""
        if self._ffmpeg_available is not None:
            return self._ffmpeg_available
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            self._ffmpeg_available = proc.returncode == 0
        except FileNotFoundError:
            self._ffmpeg_available = False
        return self._ffmpeg_available

    async def process_for_telegram(self, file_path: str, media_type: str) -> dict:
        """Return file info without any compression — zero delay."""
        file_size = os.path.getsize(file_path)
        return {
            "file_path": file_path,
            "file_size": file_size,
            "was_compressed": False,
            "media_type": media_type,
        }
    async def recompress_video(self, file_path: str, quality: str) -> dict:
        """Recompress video to target quality. Used for >50MB quality choices."""
        if not await self.check_ffmpeg():
            raise Exception("FFMPEG_NOT_AVAILABLE")

        if quality == "medium":
            crf = "28"
            resolution = "1280x720"
            audio_bitrate = "128k"
        elif quality == "low":
            crf = "33"
            resolution = "854x480"
            audio_bitrate = "96k"
        else:
            # "best" — no recompression needed
            return await self.process_for_telegram(file_path, "video")

        output_name = f"recomp_{uuid.uuid4().hex[:8]}.mp4"
        output_path = str(self.temp_dir / output_name)

        cmd = [
            "ffmpeg", "-y",
            "-i", file_path,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", crf,
            "-vf", f"scale={resolution}:force_original_aspect_ratio=decrease",
            "-c:a", "aac",
            "-b:a", audio_bitrate,
            "-movflags", "+faststart",
            output_path,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)

            if proc.returncode != 0:
                logger.error(f"Recompression failed: {stderr.decode()[-300:]}")
                raise Exception("Qayta siqishda xatolik")

            if not os.path.exists(output_path):
                raise Exception("Siqilgan fayl yaratilmadi")

            return {
                "file_path": output_path,
                "file_size": os.path.getsize(output_path),
                "was_compressed": True,
                "media_type": "video",
            }

        except asyncio.TimeoutError:
            self._safe_remove(output_path)
            raise Exception("Qayta siqish juda uzoq davom etdi")
        except Exception:
            self._safe_remove(output_path)
            raise
        # Siqish olib tashlandi — tezlik uchun fayl to'g'ridan-to'g'ri yuboriladi
        return result
    async def extract_audio_from_video(self, video_path: str, title: str = "audio") -> dict:
        """Extract audio track from a video file as MP3."""
        if not await self.check_ffmpeg():
            raise Exception("FFMPEG_NOT_AVAILABLE")

        safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:50] or "audio"
        output_name = f"{safe_title}_{uuid.uuid4().hex[:6]}.mp3"
        output_path = str(self.temp_dir / output_name)

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            output_path,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

            if proc.returncode != 0:
                logger.error(f"Audio extraction failed: {stderr.decode()[-300:]}")
                raise Exception("Audio ajratib olishda xatolik yuz berdi")

            if not os.path.exists(output_path):
                raise Exception("Audio fayl yaratilmadi")

            return {
                "file_path": output_path,
                "file_size": os.path.getsize(output_path),
                "title": safe_title,
            }

        except asyncio.TimeoutError:
            self._safe_remove(output_path)
            raise Exception("Audio ajratish juda uzoq davom etdi")
        except Exception:
            self._safe_remove(output_path)
            raise

    def _safe_remove(self, path: str):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    def cleanup_all(self):
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
                self.temp_dir.mkdir(exist_ok=True)
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
