"""Per-user rate limiting middleware using Redis."""

import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
import redis.asyncio as aioredis

from config import RATE_LIMIT_PER_MINUTE, REDIS_URL
from utils import messages as msg

logger = logging.getLogger(__name__)

RATE_KEY_PREFIX = "bot:rate:"


class RateLimitMiddleware(BaseMiddleware):
    """Limits requests per user per minute using Redis."""

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.limit = RATE_LIMIT_PER_MINUTE
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Extract user_id from event
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if not user_id:
            return await handler(event, data)

        # Check rate limit
        key = f"{RATE_KEY_PREFIX}{user_id}"
        try:
            current = await self.redis.incr(key)
            if current == 1:
                await self.redis.expire(key, 60)  # 1 minute TTL

            if current > self.limit:
                ttl = await self.redis.ttl(key)
                ttl = max(ttl, 1)
                logger.warning(f"Rate limit exceeded for user {user_id}: {current}/{self.limit}")

                if isinstance(event, Message):
                    await event.answer(
                        msg.ERROR_RATE_LIMIT.format(seconds=ttl),
                        parse_mode="HTML",
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer(
                        f"Juda ko'p so'rov. {ttl} soniya kuting.",
                        show_alert=True,
                    )
                return  # Block the request

        except Exception as e:
            # If Redis fails, allow the request through
            logger.error(f"Rate limit check error: {e}")

        return await handler(event, data)
