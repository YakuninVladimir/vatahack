import logging

from redis.asyncio import Redis

from config import REDIS_URL
from db_functions.db import get_summary_checkpoint_db, set_summary_checkpoint_db

logger = logging.getLogger(__name__)

_redis: Redis | None = None


def _checkpoint_key(chat_id: int, thread_id: int | None) -> str:
    thread_key = int(thread_id or 0)
    return f"summary_checkpoint:{chat_id}:{thread_key}"


async def checkpoints_init():
    global _redis
    if not REDIS_URL:
        logger.info("REDIS_URL is not set; using DB only for checkpoints")
        return
    try:
        _redis = Redis.from_url(REDIS_URL, decode_responses=True)
        await _redis.ping()
        logger.info("Connected to Redis for checkpoints")
    except Exception as exc:
        logger.warning("Redis unavailable, falling back to DB: %s", exc)
        _redis = None


async def checkpoints_close():
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


async def get_last_checkpoint(chat_id: int, thread_id: int | None) -> int | None:
    key = _checkpoint_key(chat_id, thread_id)

    if _redis is not None:
        try:
            cached = await _redis.get(key)
            if cached is not None:
                return int(cached)
        except Exception as exc:
            logger.warning("Redis get failed, fallback to DB: %s", exc)

    last = await get_summary_checkpoint_db(chat_id, thread_id)

    if last is not None and _redis is not None:
        try:
            await _redis.set(key, str(last))
        except Exception as exc:
            logger.warning("Redis set failed: %s", exc)

    return last


async def set_last_checkpoint(chat_id: int, thread_id: int | None, message_id: int):
    key = _checkpoint_key(chat_id, thread_id)

    await set_summary_checkpoint_db(chat_id, thread_id, message_id)

    if _redis is not None:
        try:
            await _redis.set(key, str(message_id))
        except Exception as exc:
            logger.warning("Redis set failed: %s", exc)
