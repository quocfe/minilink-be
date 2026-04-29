import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.urls.service import URLService
from src.urls.schemas import (
    URLCreate,
    URLResponse,
    URLUpdate,
    URLStats,
    UserLinksResponse,
    BulkAssignUserRequest,
    BulkAssignUserResponse,
)
from src.config import settings
from src.redis.client import redis_client
from src.kafka.client import kafka_producer
from src.urls.dependencies import shorten_rate_limit, redirect_rate_limit
from src.auth.dependencies import get_optional_current_user_id, get_current_user_id

router = APIRouter()


async def _produce_click_event(url_id, short_code: str, request: Request):
    """Build and send a click event message to Kafka (non-blocking)."""
    try:
        await kafka_producer.send_message(
            topic=settings.kafka_click_topic,
            message={
                "url_id": str(url_id),
                "short_code": short_code,
                "clicked_at": datetime.now(timezone.utc).isoformat(),
                "ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
                "referrer": request.headers.get("referer"),
            },
            key=str(url_id),
        )
        print(f"[KafkaProducer] Click event sent for URL ID: {url_id}")
    except Exception as e:
        print(f"[KafkaProducer] Failed to send click event: {e}")


@router.post("/shorten", response_model=URLResponse)
async def create_short_url(
    url_data: URLCreate,
    db: AsyncSession = Depends(get_db),
    current_user_id: Optional[UUID] = Depends(get_optional_current_user_id),
    _: None = Depends(shorten_rate_limit)
):
    """Create a new shortened URL."""
    try:
        print(f"[URLCreate] current_user_id: {current_user_id}")
        url = await URLService.create_url(db, url_data, current_user_id)
        return URLResponse(
            id=url.id,
            short_code=url.short_code,
            short_url=f"{settings.base_url}/{url.short_code}",
            original_url=url.original_url,
            expires_at=url.expires_at,
            is_active=url.is_active,
            click_count=url.click_count,
            created_at=url.created_at
        )
    except ValueError as e:
        print(f"[URLCreate] Failed to create shortened URL: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[URLCreate] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create short URL")


@router.put("/bulk-assign", response_model=BulkAssignUserResponse)
async def bulk_assign_user_to_urls(
    data: BulkAssignUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Assign the current user as owner of a list of URLs by their IDs."""
    updated_ids = await URLService.bulk_assign_user(db, data.url_ids, current_user_id)
    return BulkAssignUserResponse(
        updated_count=len(updated_ids),
        updated_ids=updated_ids
    )


@router.get("/links", response_model=UserLinksResponse)
async def get_my_urls(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user_id: Optional[UUID] = Depends(get_optional_current_user_id)
):
    """Get all URLs for the current user."""
    print(f"skip: {skip}, limit: {limit}, current_user_id: {current_user_id}")
    urls = await URLService.get_user_urls(db, current_user_id, skip, limit)
    click_events = await URLService.get_user_click_events_summary(db, current_user_id)

    return {
        "links": [
            URLResponse(
                id=url.id,
                short_code=url.short_code,
                short_url=f"{settings.base_url}/{url.short_code}",
                original_url=url.original_url,
                expires_at=url.expires_at,
                is_active=url.is_active,
                click_count=url.click_count,
                created_at=url.created_at
            ) for url in urls
        ],
        "click_events": click_events,
    }


@router.get("/{short_code}", response_class=RedirectResponse)
async def redirect_to_original(
    short_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(redirect_rate_limit)
):
    """Redirect to the original URL and record click analytics."""
    print(f"[Redirect] Attempting to resolve short code '{short_code}' from cache")

    cached_data = await URLService.get_original_url_from_cache(short_code)

    if cached_data:
        url_id, original_url = cached_data
    else:
        # Redis MISS — query PostgreSQL
        url = await URLService.get_url_by_short_code(db, short_code)
        if not url or not url.is_active:
            raise HTTPException(status_code=404, detail="URL not found")

        # Check if expired
        if url.expires_at and url.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="URL has expired")

        url_id = url.id
        original_url = url.original_url

        # Populate Redis cache on miss
        await redis_client.set(
            f"url:{short_code}",
            f"{url.id}:{url.original_url}",
            expire=3600
        )

    # Fire-and-forget: produce click event to Kafka without blocking the redirect
    print(f"[Redirect] URL ID: {url_id}, Short Code: {short_code} | Producing click event to Kafka")
    asyncio.create_task(_produce_click_event(
        url_id=url_id,
        short_code=short_code,
        request=request,
    ))

    return RedirectResponse(url=original_url, status_code=302)


@router.get("/{short_code}/info", response_model=URLResponse)
async def get_url_info(
    short_code: str,
    db: AsyncSession = Depends(get_db)
):
    """Get information about a shortened URL."""
    url = await URLService.get_url_by_short_code(db, short_code)
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")

    return URLResponse(
        id=url.id,
        short_code=url.short_code,
        short_url=f"{settings.base_url}/{url.short_code}",
        original_url=url.original_url,
        expires_at=url.expires_at,
        is_active=url.is_active,
        click_count=url.click_count,
        created_at=url.created_at
    )


@router.put("/{short_code}", response_model=URLResponse)
async def update_url(
    short_code: str,
    url_data: URLUpdate,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Update an existing shortened URL."""
    updated_url = await URLService.update_url(db, short_code, url_data, current_user_id)
    if not updated_url:
        raise HTTPException(status_code=404, detail="URL not found or not owned by user")

    return URLResponse(
        id=updated_url.id,
        short_code=updated_url.short_code,
        short_url=f"{settings.base_url}/{updated_url.short_code}",
        original_url=updated_url.original_url,
        expires_at=updated_url.expires_at,
        is_active=updated_url.is_active,
        click_count=updated_url.click_count,
        created_at=updated_url.created_at
    )


@router.delete("/{short_code}")
async def delete_url(
    short_code: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Delete (deactivate) a shortened URL."""
    success = await URLService.delete_url(db, short_code, current_user_id)
    if not success:
        raise HTTPException(status_code=404, detail="URL not found or not owned by user")

    return {"message": "URL deleted successfully"}


@router.get("/{short_code}/stats", response_model=URLStats)
async def get_url_statistics(
    short_code: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Get detailed statistics for a shortened URL."""
    stats = await URLService.get_url_stats(db, short_code, current_user_id)
    if not stats:
        raise HTTPException(status_code=404, detail="URL not found or not owned by user")

    return stats

