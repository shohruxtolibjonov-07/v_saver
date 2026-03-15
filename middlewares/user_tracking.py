"""User tracking middleware — saves user IDs to Redis for broadcast."""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

USERS_KEY = "bot:users"


class UserTrackingMiddleware(BaseMiddleware):
    """Tracks all user IDs in Redis SET for broadcast feature."""

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.from_user:
            try:
                await self.redis.sadd(USERS_KEY, str(event.from_user.id))
            except Exception as e:
                logger.debug(f"User tracking error: {e}")

        return await handler(event, data)
