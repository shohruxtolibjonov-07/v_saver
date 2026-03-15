"""Video Saver Bot — Entry point with Redis, workers, and middlewares."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, ADMIN_ID, TEMP_DIR, LOG_LEVEL, WORKER_COUNT
from handlers.start import router as start_router
from handlers.download import router as download_router
from handlers.admin import router as admin_router
from services.worker import WorkerPool
from utils.messages import ADMIN_BOT_STARTED

# Logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)
logging.getLogger("yt_dlp").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Global worker pool
worker_pool = WorkerPool()


async def on_startup(bot: Bot):
    """Called when the bot starts."""
    logger.info("Bot started successfully")

    try:
        await bot.send_message(
            ADMIN_ID,
            ADMIN_BOT_STARTED.format(workers=WORKER_COUNT),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Could not notify admin: {e}")


async def on_shutdown(bot: Bot):
    """Called when the bot shuts down."""
    logger.info("Bot shutting down...")

    # Stop worker pool
    await worker_pool.disconnect()

    # Cleanup temp directory
    import shutil
    try:
        if TEMP_DIR.exists():
            shutil.rmtree(TEMP_DIR)
            logger.info("Temp directory cleaned up")
    except Exception as e:
        logger.warning(f"Cleanup error: {e}")


async def main():
    """Main entry point."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set! Create a .env file or set environment variable.")
        sys.exit(1)

    # Ensure temp directory exists
    TEMP_DIR.mkdir(exist_ok=True)

    # Connect Redis & start workers
    try:
        await worker_pool.connect()
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        logger.warning("Bot will run without Redis queue — downloads will be direct.")

    # Create bot
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Create dispatcher
    dp = Dispatcher()

    # Register middlewares (only if Redis is connected)
    if worker_pool.redis:
        try:
            from middlewares.rate_limit import RateLimitMiddleware
            from middlewares.user_tracking import UserTrackingMiddleware

            dp.message.middleware(RateLimitMiddleware(worker_pool.redis))
            dp.message.middleware(UserTrackingMiddleware(worker_pool.redis))
            dp.callback_query.middleware(RateLimitMiddleware(worker_pool.redis))
            logger.info("Middlewares registered (rate limit + user tracking)")
        except Exception as e:
            logger.warning(f"Middleware registration error: {e}")

    # Inject worker pool into handlers
    from handlers.admin import set_worker_pool as admin_set_pool
    admin_set_pool(worker_pool)

    # Register routers (order matters — start first, then admin, then download)
    dp.include_router(start_router)
    dp.include_router(admin_router)
    dp.include_router(download_router)

    # Register hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting bot polling...")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
