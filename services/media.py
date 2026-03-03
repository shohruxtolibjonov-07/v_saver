import asyncio
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

from config import MAX_TELEGRAM_FILE_SIZE, TEMP_DIR

# FFmpeg settings (used only for compression, optional if ffmpeg is installed)
FFMPEG_COMPRESS_PRESET = "ultrafast"
FFMPEG_CRF = 28
FFMPEG_MAX_RESOLUTION = "1280x720"

logger = logging.getLogger(__name__)


class MediaProcessor:
    """Handles media compression, optimization, and audio extraction."""

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
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            self._ffmpeg_available = proc.returncode == 0
        except FileNotFoundError:
            self._ffmpeg_available = False
        return self._ffmpeg_available

    async def process_for_telegram(self, file_path: str, media_type: str) -> dict:
        """Process a media file for Telegram delivery."""
        file_size = os.path.getsize(file_path)

        result = {
            "file_path": file_path,
            "file_size": file_size,
            "was_compressed": False,
            "media_type": media_type,
        }

        # Siqish olib tashlandi — tezlik uchun fayl to'g'ridan-to'g'ri yuboriladi
        return result

    async def extract_audio_from_video(self, video_path: str, title: str = "audio") -> dict:
        """
        Extract audio track from a video file and return as MP3.
        Used when user sends a video file directly to the bot.
        """
        if not await self.check_ffmpeg():
            raise Exception("FFMPEG_NOT_AVAILABLE")

        safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:50] or "audio"
        output_name = f"{safe_title}_{uuid.uuid4().hex[:6]}.mp3"
        output_path = str(self.temp_dir / output_name)

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",              # no video
            "-c:a", "libmp3lame",
            "-b:a", "192k",     # good quality audio
            "-ar", "44100",     # standard sample rate
            "-ac", "2",         # stereo
            output_path
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
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

    async def _compress_video(self, file_path: str, aggressive: bool = False) -> Optional[str]:
        """Compress video using ffmpeg."""
        if not await self.check_ffmpeg():
            return None

        output_path = str(self.temp_dir / f"compressed_{Path(file_path).name}")
        crf = str(FFMPEG_CRF + (5 if aggressive else 0))
        resolution = "854x480" if aggressive else FFMPEG_MAX_RESOLUTION

        cmd = [
            "ffmpeg", "-y",
            "-i", file_path,
            "-c:v", "libx264",
            "-preset", FFMPEG_COMPRESS_PRESET,
            "-crf", crf,
            "-vf", f"scale={resolution}:force_original_aspect_ratio=decrease",
            "-c:a", "aac",
            "-b:a", "96k" if aggressive else "128k",
            "-movflags", "+faststart",
            output_path
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)

            if proc.returncode != 0:
                logger.error(f"FFmpeg compression error: {stderr.decode()[-500:]}")
                return None
            return output_path
        except asyncio.TimeoutError:
            logger.error("FFmpeg compression timeout")
            return None
        except Exception as e:
            logger.error(f"FFmpeg error: {e}")
            return None

    async def _compress_audio(self, file_path: str) -> Optional[str]:
        """Compress audio using ffmpeg."""
        if not await self.check_ffmpeg():
            return None

        output_path = str(self.temp_dir / f"compressed_{Path(file_path).name}")

        cmd = [
            "ffmpeg", "-y",
            "-i", file_path,
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            output_path
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

            if proc.returncode != 0:
                logger.error(f"FFmpeg audio compression error: {stderr.decode()[-500:]}")
                return None
            return output_path
        except Exception as e:
            logger.error(f"FFmpeg audio error: {e}")
            return None

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
