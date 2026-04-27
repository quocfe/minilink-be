from fastapi import Depends, HTTPException, Request
from src.redis.client import redis_client


async def _rate_limit(request: Request, limit: int, window: int, prefix: str):
    """
    Generic rate limiter using Redis INCR + EXPIRE pattern.
    :param limit: max requests allowed in the window
    :param window: time window in seconds
    :param prefix: key prefix to namespace different limits
    """
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
    """10 requests/minute per IP for POST /shorten."""
    await _rate_limit(request, limit=10, window=60, prefix="shorten")


async def redirect_rate_limit(request: Request):
    """100 requests/minute per IP for GET /{short_code}."""
    await _rate_limit(request, limit=100, window=60, prefix="redirect")

