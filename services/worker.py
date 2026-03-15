"""Async worker pool with Redis-backed job queue."""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Callable, Awaitable

import redis.asyncio as aioredis

from config import REDIS_URL, WORKER_COUNT, JOB_TIMEOUT, MAX_RETRIES

logger = logging.getLogger(__name__)

# Redis keys
QUEUE_KEY = "bot:queue"
JOBS_KEY = "bot:jobs"            # hash: job_id -> job_json
STATS_KEY = "bot:stats"          # hash: total_downloads, etc.
USERS_KEY = "bot:users"          # set of user IDs


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadJob:
    """Represents a download job in the queue."""
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    chat_id: int = 0
    user_id: int = 0
    url: str = ""
    platform: str = ""            # "youtube" or "instagram"
    media_type: str = "video"     # "video" or "audio"
    quality: str = "best"         # "best", "medium", "low"
    status: str = JobStatus.PENDING
    status_message_id: int = 0    # message to edit with progress
    created_at: float = field(default_factory=time.time)
    error: str = ""
    retries: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> "DownloadJob":
        return cls(**json.loads(data))


class WorkerPool:
    """Async worker pool backed by Redis queue."""

    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self._workers: list[asyncio.Task] = []
        self._paused = False
        self._handler: Optional[Callable[[DownloadJob], Awaitable[None]]] = None
        self._running = False

    async def connect(self):
        """Connect to Redis."""
        self.redis = aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            retry_on_timeout=True,
        )
        try:
            await self.redis.ping()
            logger.info("Redis connected successfully")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            raise

    async def disconnect(self):
        """Disconnect from Redis."""
        self._running = False
        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        if self.redis:
            await self.redis.close()
            logger.info("Redis disconnected")

    def set_handler(self, handler: Callable[[DownloadJob], Awaitable[None]]):
        """Set the job processing handler."""
        self._handler = handler

    async def start_workers(self):
        """Start worker tasks."""
        if not self._handler:
            raise RuntimeError("No handler set. Call set_handler() first.")
        self._running = True
        for i in range(WORKER_COUNT):
            task = asyncio.create_task(self._worker_loop(i))
            self._workers.append(task)
        logger.info(f"Started {WORKER_COUNT} workers")

    async def _worker_loop(self, worker_id: int):
        """Main worker loop — pulls jobs from Redis queue."""
        logger.info(f"Worker-{worker_id} started")
        while self._running:
            try:
                if self._paused:
                    await asyncio.sleep(1)
                    continue

                # BRPOP with 2s timeout to allow graceful shutdown checks
                result = await self.redis.brpop(QUEUE_KEY, timeout=2)
                if not result:
                    continue

                _, job_json = result
                job = DownloadJob.from_json(job_json)

                # Check if cancelled
                stored = await self.redis.hget(JOBS_KEY, job.job_id)
                if stored:
                    stored_job = DownloadJob.from_json(stored)
                    if stored_job.status == JobStatus.CANCELLED:
                        logger.info(f"Worker-{worker_id}: Job {job.job_id} cancelled, skipping")
                        continue

                # Update status to processing
                job.status = JobStatus.PROCESSING
                await self.redis.hset(JOBS_KEY, job.job_id, job.to_json())

                logger.info(f"Worker-{worker_id}: Processing job {job.job_id} ({job.url[:50]}...)")

                try:
                    await asyncio.wait_for(
                        self._handler(job),
                        timeout=JOB_TIMEOUT,
                    )
                    job.status = JobStatus.DONE
                    await self.redis.hincrby(STATS_KEY, "total_downloads", 1)
                    logger.info(f"Worker-{worker_id}: Job {job.job_id} completed")

                except asyncio.TimeoutError:
                    job.status = JobStatus.FAILED
                    job.error = "Timeout"
                    logger.error(f"Worker-{worker_id}: Job {job.job_id} timed out")

                except Exception as e:
                    job.error = str(e)[:500]
                    job.retries += 1

                    if job.retries < MAX_RETRIES:
                        # Retry with exponential backoff
                        job.status = JobStatus.PENDING
                        delay = 2 ** job.retries
                        logger.warning(
                            f"Worker-{worker_id}: Job {job.job_id} failed, retry {job.retries}/{MAX_RETRIES} in {delay}s"
                        )
                        await asyncio.sleep(delay)
                        await self.submit_job(job)
                    else:
                        job.status = JobStatus.FAILED
                        logger.error(f"Worker-{worker_id}: Job {job.job_id} failed permanently: {job.error[:100]}")

                # Save final status
                await self.redis.hset(JOBS_KEY, job.job_id, job.to_json())

            except asyncio.CancelledError:
                logger.info(f"Worker-{worker_id} cancelled")
                break
            except Exception as e:
                logger.error(f"Worker-{worker_id} unexpected error: {e}")
                await asyncio.sleep(2)

        logger.info(f"Worker-{worker_id} stopped")

    # ─── Public API ──────────────────────────────

    async def submit_job(self, job: DownloadJob) -> str:
        """Submit a job to the queue. Returns job_id."""
        await self.redis.hset(JOBS_KEY, job.job_id, job.to_json())
        await self.redis.lpush(QUEUE_KEY, job.to_json())
        logger.info(f"Job submitted: {job.job_id}")
        return job.job_id

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending/processing job."""
        stored = await self.redis.hget(JOBS_KEY, job_id)
        if not stored:
            return False
        job = DownloadJob.from_json(stored)
        job.status = JobStatus.CANCELLED
        await self.redis.hset(JOBS_KEY, job_id, job.to_json())
        return True

    async def get_job(self, job_id: str) -> Optional[DownloadJob]:
        """Get job by ID."""
        stored = await self.redis.hget(JOBS_KEY, job_id)
        if stored:
            return DownloadJob.from_json(stored)
        return None

    def pause(self):
        """Pause all workers."""
        self._paused = True
        logger.info("Worker pool paused")

    def resume(self):
        """Resume all workers."""
        self._paused = False
        logger.info("Worker pool resumed")

    @property
    def is_paused(self) -> bool:
        return self._paused

    async def get_stats(self) -> dict:
        """Get queue stats."""
        queue_size = await self.redis.llen(QUEUE_KEY)
        total_downloads = int(await self.redis.hget(STATS_KEY, "total_downloads") or 0)
        total_users = await self.redis.scard(USERS_KEY)

        # Count jobs by status
        all_jobs = await self.redis.hgetall(JOBS_KEY)
        status_counts = {"pending": 0, "processing": 0, "done": 0, "failed": 0}
        for job_json in all_jobs.values():
            try:
                job = DownloadJob.from_json(job_json)
                if job.status in status_counts:
                    status_counts[job.status] += 1
            except Exception:
                pass

        return {
            "queue_size": queue_size,
            "total_downloads": total_downloads,
            "total_users": total_users,
            "active_workers": sum(1 for w in self._workers if not w.done()),
            "total_workers": WORKER_COUNT,
            "paused": self._paused,
            **status_counts,
        }

    async def track_user(self, user_id: int):
        """Track a user for broadcast."""
        await self.redis.sadd(USERS_KEY, str(user_id))

    async def get_all_users(self) -> set[str]:
        """Get all tracked user IDs."""
        return await self.redis.smembers(USERS_KEY)

    async def cleanup_old_jobs(self, max_age: int = 86400):
        """Remove completed/failed jobs older than max_age seconds."""
        all_jobs = await self.redis.hgetall(JOBS_KEY)
        now = time.time()
        removed = 0
        for job_id, job_json in all_jobs.items():
            try:
                job = DownloadJob.from_json(job_json)
                if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
                    if now - job.created_at > max_age:
                        await self.redis.hdel(JOBS_KEY, job_id)
                        removed += 1
            except Exception:
                await self.redis.hdel(JOBS_KEY, job_id)
                removed += 1
        if removed:
            logger.info(f"Cleaned up {removed} old jobs")
