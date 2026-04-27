from datetime import datetime
from fastapi import APIRouter
from src.health.schemas import HealthCheck
from src.config import settings
from src.redis.client import redis_client
from src.database import engine

router = APIRouter()


@router.get("/health", response_model=HealthCheck)
async def health_check():
    """Health check endpoint to verify service status."""
    services = {}

    # Check database connection
    try:
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        services["database"] = "healthy"
    except Exception as e:
        services["database"] = f"unhealthy: {str(e)}"

    # Check Redis connection
    try:
        await redis_client.set("health_check", "ok", expire=10)
        result = await redis_client.get("health_check")
        if result == "ok":
            services["redis"] = "healthy"
        else:
            services["redis"] = "unhealthy: unexpected response"
    except Exception as e:
        services["redis"] = f"unhealthy: {str(e)}"

    # Check if any service is unhealthy
    overall_status = "healthy" if all("healthy" in status for status in services.values()) else "unhealthy"

    return HealthCheck(
        status=overall_status,
        timestamp=datetime.utcnow(),
        version=settings.app_version,
        services=services
    )

