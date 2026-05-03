from fastapi import Depends, HTTPException, Request
from src.redis.client import redis_client
from src.config import settings


async def _rate_limit(request: Request, limit: int, window: int, prefix: str):
    """
    Generic rate limiter using Redis INCR + EXPIRE pattern.
    :param limit: max requests allowed in the window
    :param window: time window in seconds
    :param prefix: key prefix to namespace different limits
    """
    if not settings.rate_limit:
        return

    ip = request.client.host if request.client else "unknown"
    key = f"rate:{prefix}:{ip}"

    count = await redis_client.incr(key)
    if count == 1:
        # First request in window — set expiry
        await redis_client.expire(key, window)

    if count > limit:
        ttl = await redis_client.ttl(key)
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Try again in {ttl} second(s).",
            headers={"Retry-After": str(ttl)},
        )


async def shorten_rate_limit(request: Request):
    await _rate_limit(request, limit=100, window=60, prefix="shorten")


async def redirect_rate_limit(request: Request):
    await _rate_limit(request, limit=100, window=60, prefix="redirect")

