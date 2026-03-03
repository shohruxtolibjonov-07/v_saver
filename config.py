import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# File limits
MAX_TELEGRAM_FILE_SIZE = 2000 * 1024 * 1024  # ~2 GB (Telegram document limit)
TELEGRAM_VIDEO_LIMIT = 50 * 1024 * 1024  # 50 MB — send_video/send_audio limit

# Temporary download directory
BASE_DIR = Path(__file__).parent
TEMP_DIR = BASE_DIR / "temp_downloads"
TEMP_DIR.mkdir(exist_ok=True)

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
