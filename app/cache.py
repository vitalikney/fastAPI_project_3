import json
import logging
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import get_settings


logger = logging.getLogger(__name__)
redis_client: Redis | None = None


async def init_redis() -> None:
    global redis_client
    settings = get_settings()
    try:
        redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connected")
    except RedisError:
        redis_client = None
        logger.warning("Redis unavailable, cache disabled")


async def close_redis() -> None:
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None


async def cache_get(key: str) -> Any:
    if redis_client is None:
        return None
    try:
        value = await redis_client.get(key)
        return None if value is None else json.loads(value)
    except (RedisError, json.JSONDecodeError):
        return None


async def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    if redis_client is None:
        return
    settings = get_settings()
    try:
        await redis_client.set(key, json.dumps(value, default=str), ex=ttl or settings.cache_ttl_seconds)
    except RedisError:
        return


async def cache_delete(*keys: str) -> None:
    if redis_client is None or not keys:
        return
    try:
        await redis_client.delete(*keys)
    except RedisError:
        return
