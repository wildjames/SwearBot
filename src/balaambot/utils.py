import concurrent.futures
import json
from collections.abc import Awaitable

import redis

from balaambot.config import ADDRESS, DB, PASSWORD, PORT, REDIS_KEY, USE_REDIS, USERNAME

FUTURES_EXECUTOR = concurrent.futures.ProcessPoolExecutor()

memory_cache: dict[str, dict] = {}

redis_cache = None
if USE_REDIS:
    redis_cache = redis.Redis(
        host=ADDRESS,
        port=PORT,
        db=DB,
        username=USERNAME,
        password=PASSWORD,
    )


async def get_cache(key: str) -> dict:
    """Fetch a dict from the cache.

    Arguments:
        key: The key that the data is stored under

    """
    if redis_cache is not None:
        serialised = redis_cache.hget(REDIS_KEY, key)

        if isinstance(serialised, Awaitable):
            serialised = await serialised

        if not serialised:
            raise KeyError(key)

        return json.loads(serialised)

    return memory_cache[key]


async def set_cache(key: str, obj: dict) -> None:
    """Store the given dictionary in the cache under the specified key.

    Arguments:
        key: The cache key under which to store the object.
        obj: The dictionary object to cache.

    """
    if redis_cache is not None:
        serialised = json.dumps(obj)
        redis_cache.hset(REDIS_KEY, key, serialised)
        return

    memory_cache[key] = obj


def sec_to_string(val: float) -> str:
    """Convert a number of seconds to a human-readable string, (HH:)MM:SS."""
    sec_in_hour = 60 * 60
    d = ""
    if val >= sec_in_hour:
        d += f"{int(val // sec_in_hour):02d}:"
        val = val % sec_in_hour
    d += f"{int(val // 60):02d}:{int(val % 60):02d}"
    return d
