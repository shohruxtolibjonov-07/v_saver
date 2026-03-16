import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Bot ────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
BOT_USERNAME = os.getenv("BOT_USERNAME", "videosaq1a_bot")

# ─── Redis ──────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ─── File limits ────────────────────────────────
# Telegram Cloud Bot API limit: 50 MB for ALL upload methods
# (send_video, send_audio, send_document — hammasi 50 MB)
TELEGRAM_VIDEO_LIMIT = 50 * 1024 * 1024       # 50 MB – inline video playback
TELEGRAM_DOCUMENT_LIMIT = 50 * 1024 * 1024    # 50 MB – cloud Bot API hard limit

# ─── Worker pool ────────────────────────────────
WORKER_COUNT = int(os.getenv("WORKER_COUNT", "4"))
JOB_TIMEOUT = int(os.getenv("JOB_TIMEOUT", "600"))  # 10 minutes
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

# ─── Rate limiting ──────────────────────────────
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))

# ─── Paths ──────────────────────────────────────
BASE_DIR = Path(__file__).parent
TEMP_DIR = BASE_DIR / "temp_downloads"
TEMP_DIR.mkdir(exist_ok=True)

# ─── Logging ────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
