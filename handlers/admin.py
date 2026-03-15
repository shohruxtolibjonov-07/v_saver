"""Admin-only handlers: broadcast, stats, queue management."""

import asyncio
import logging

from aiogram import Router, Bot, types, F
from aiogram.filters import Command

from config import ADMIN_ID
from utils import messages as msg
from services.worker import WorkerPool

logger = logging.getLogger(__name__)
router = Router()

# Reference set at bot startup
_worker_pool: WorkerPool | None = None


def set_worker_pool(pool: WorkerPool):
    """Called at startup to inject dependency."""
    global _worker_pool
    _worker_pool = pool


def _is_admin(message: types.Message) -> bool:
    return message.from_user and message.from_user.id == ADMIN_ID


# ─── /stats ──────────────────────────────────────
@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if not _is_admin(message):
        await message.answer(msg.ADMIN_ONLY, parse_mode="HTML")
        return

    if not _worker_pool:
        await message.answer("⚠️ Worker pool ishlamayapti.", parse_mode="HTML")
        return

    stats = await _worker_pool.get_stats()
    status = "⏸ To'xtatilgan" if stats["paused"] else "▶️ Ishlayapti"

    await message.answer(
        msg.ADMIN_STATS.format(
            total_users=stats["total_users"],
            total_downloads=stats["total_downloads"],
            queue_size=stats["queue_size"],
            active_workers=stats["active_workers"],
            total_workers=stats["total_workers"],
            status=status,
        ),
        parse_mode="HTML",
    )


# ─── /queue ──────────────────────────────────────
@router.message(Command("queue"))
async def cmd_queue(message: types.Message):
    if not _is_admin(message):
        await message.answer(msg.ADMIN_ONLY, parse_mode="HTML")
        return

    if not _worker_pool:
        await message.answer("⚠️ Worker pool ishlamayapti.", parse_mode="HTML")
        return

    stats = await _worker_pool.get_stats()
    await message.answer(
        msg.ADMIN_QUEUE_STATUS.format(
            pending=stats["pending"],
            processing=stats["processing"],
            completed=stats["done"],
            failed=stats["failed"],
        ),
        parse_mode="HTML",
    )


# ─── /pause ──────────────────────────────────────
@router.message(Command("pause"))
async def cmd_pause(message: types.Message):
    if not _is_admin(message):
        await message.answer(msg.ADMIN_ONLY, parse_mode="HTML")
        return
    if _worker_pool:
        _worker_pool.pause()
    await message.answer(msg.ADMIN_PAUSED, parse_mode="HTML")


# ─── /resume ─────────────────────────────────────
@router.message(Command("resume"))
async def cmd_resume(message: types.Message):
    if not _is_admin(message):
        await message.answer(msg.ADMIN_ONLY, parse_mode="HTML")
        return
    if _worker_pool:
        _worker_pool.resume()
    await message.answer(msg.ADMIN_RESUMED, parse_mode="HTML")


# ─── /cancel <job_id> ────────────────────────────
@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message):
    if not _is_admin(message):
        await message.answer(msg.ADMIN_ONLY, parse_mode="HTML")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Foydalanish: /cancel &lt;job_id&gt;", parse_mode="HTML")
        return

    job_id = parts[1].strip()
    if _worker_pool and await _worker_pool.cancel_job(job_id):
        await message.answer(msg.ADMIN_JOB_CANCELLED.format(job_id=job_id), parse_mode="HTML")
    else:
        await message.answer(msg.ADMIN_JOB_NOT_FOUND.format(job_id=job_id), parse_mode="HTML")


# ─── /broadcast <message> ────────────────────────
@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, bot: Bot):
    if not _is_admin(message):
        await message.answer(msg.ADMIN_ONLY, parse_mode="HTML")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Foydalanish: /broadcast &lt;xabar&gt;", parse_mode="HTML")
        return

    text = parts[1]
    if not _worker_pool:
        await message.answer("⚠️ Worker pool ishlamayapti.", parse_mode="HTML")
        return

    users = await _worker_pool.get_all_users()
    total = len(users)

    if total == 0:
        await message.answer("👥 Hech qanday foydalanuvchi topilmadi.", parse_mode="HTML")
        return

    await message.answer(msg.ADMIN_BROADCAST_STARTED.format(total=total), parse_mode="HTML")

    success = 0
    failed = 0

    for user_id_str in users:
        try:
            user_id = int(user_id_str)
            await bot.send_message(user_id, text, parse_mode="HTML")
            success += 1
        except Exception:
            failed += 1

        # Small delay to avoid Telegram rate limits
        if (success + failed) % 25 == 0:
            await asyncio.sleep(1)

    await message.answer(
        msg.ADMIN_BROADCAST_DONE.format(success=success, failed=failed),
        parse_mode="HTML",
    )


# ─── /cleanup ────────────────────────────────────
@router.message(Command("cleanup"))
async def cmd_cleanup(message: types.Message):
    if not _is_admin(message):
        await message.answer(msg.ADMIN_ONLY, parse_mode="HTML")
        return
    if _worker_pool:
        await _worker_pool.cleanup_old_jobs()
        await message.answer("🗑 Eski joblar tozalandi.", parse_mode="HTML")
