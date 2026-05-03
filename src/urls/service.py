import string
import random
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from src.urls.models import URL, ClickEvent
from src.urls.schemas import URLCreate, URLUpdate, ClickEventCreate
from src.config import settings
from src.redis.client import redis_client
from src.kafka.client import kafka_producer


class URLService:
    @staticmethod
    def generate_short_code() -> str:
        """Generate a random short code."""
        characters = string.ascii_letters + string.digits
        return ''.join(random.choices(characters, k=settings.short_url_length))

    @staticmethod
    async def create_url(db: AsyncSession, url_data: URLCreate, user_id: Optional[UUID]) -> URL:
        """Create a new shortened URL."""
        # Use custom code or generate one
        short_code = url_data.custom_code or URLService.generate_short_code()

        # Calculate expiration date if expires_in_days is provided
        expires_at = None
        if url_data.expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=url_data.expires_in_days)

        # Ensure unique short code
        max_attempts = 10
        for _ in range(max_attempts):
            try:
                url = URL(
                    original_url=str(url_data.original_url),
                    short_code=short_code,
                    user_id=user_id,
                    expires_at=expires_at
                )
                db.add(url)
                await db.commit()
                await db.refresh(url)

                # Cache in Redis with URL ID as key
                if settings.redis_cache:
                    await redis_client.set(
                        f"url:{short_code}",
                        f"{url.id}:{str(url_data.original_url)}",
                        expire=3600
                    )

                return url
            except IntegrityError as e:
                print(f"[IntegrityError] {e}")
                await db.rollback()
                if url_data.custom_code:
                    raise ValueError("Mã tùy chỉnh đã tồn tại, vui lòng chọn mã khác")
                short_code = URLService.generate_short_code()

        raise Exception("Failed to generate unique short code")

    @staticmethod
    async def get_url_by_short_code(db: AsyncSession, short_code: str) -> Optional[URL]:
        """Get URL by short code with user relationship."""
        result = await db.execute(
            select(URL)
            .options(selectinload(URL.user))
            .where(URL.short_code == short_code)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_url_by_id(db: AsyncSession, url_id: UUID) -> Optional[URL]:
        """Get URL by ID."""
        result = await db.execute(select(URL).where(URL.id == url_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_original_url_from_cache(short_code: str) -> Optional[tuple[UUID, str]]:
        """Get URL ID and original URL from Redis cache."""
        if not settings.redis_cache:
            return None
            
        cached_data = await redis_client.get(f"url:{short_code}")
        if cached_data:
            try:
                url_id_str, original_url = cached_data.split(':', 1)
                return UUID(url_id_str), original_url
            except (ValueError, AttributeError):
                # Invalid cache data, remove it
                await redis_client.delete(f"url:{short_code}")
        return None

    @staticmethod
    async def update_url(db: AsyncSession, short_code: str, url_data: URLUpdate, user_id: UUID) -> Optional[URL]:
        """Update an existing URL (only if owned by user)."""
        result = await db.execute(
            update(URL)
            .where(URL.short_code == short_code, URL.user_id == user_id)
            .values(**url_data.dict(exclude_unset=True))
            .returning(URL)
        )
        updated_url = result.scalar_one_or_none()
        if updated_url:
            await db.commit()
            # Update cache if original_url changed
            if url_data.original_url and settings.redis_cache:
                await redis_client.set(
                    f"url:{short_code}",
                    f"{updated_url.id}:{str(url_data.original_url)}",
                    expire=3600
                )
        return updated_url

    @staticmethod
    async def delete_url(db: AsyncSession, short_code: str, user_id: UUID) -> bool:
        """Soft delete a URL (only if owned by user)."""
        result = await db.execute(
            update(URL)
            .where(URL.short_code == short_code, URL.user_id == user_id)
            .values(is_active=False)
            .returning(URL)
        )
        deleted_url = result.scalar_one_or_none()
        if deleted_url:
            await db.commit()
            # Remove from cache
            if settings.redis_cache:
                await redis_client.delete(f"url:{short_code}")
            return True
        return False

    @staticmethod
    async def increment_click_count(db: AsyncSession, url_id: UUID) -> int:
        """Increment click count in database and cache."""
        result = await db.execute(
            update(URL)
            .where(URL.id == url_id)
            .values(click_count=URL.click_count + 1)
            .returning(URL.click_count)
        )
        new_count = result.scalar()
        if new_count is not None:
            await db.commit()
            if settings.redis_cache:
                await redis_client.incr(f"clicks:{url_id}")
        return new_count or 0

    @staticmethod
    async def record_click(click_data: ClickEventCreate):
        """Send click event to Kafka for async processing."""
        message = {
            "url_id": str(click_data.url_id),
            "country": click_data.country,
            "device": click_data.device,
            "referrer": click_data.referrer,
            "clicked_at": datetime.utcnow().isoformat()
        }
        await kafka_producer.send_message(
            topic=settings.kafka_click_topic,
            message=message,
            key=str(click_data.url_id)
        )

    @staticmethod
    async def get_url_stats(db: AsyncSession, short_code: str, user_id: UUID) -> Optional[dict]:
        """Get URL statistics (only if owned by user)."""
        url = await db.execute(
            select(URL)
            .where(URL.short_code == short_code, URL.user_id == user_id)
        )
        url = url.scalar_one_or_none()
        if not url:
            return None

        # Get recent clicks
        result = await db.execute(
            select(ClickEvent)
            .where(ClickEvent.url_id == url.id)
            .order_by(ClickEvent.clicked_at.desc())
            .limit(10)
        )
        recent_clicks = result.scalars().all()

        return {
            "id": url.id,
            "short_code": short_code,
            "original_url": url.original_url,
            "total_clicks": url.click_count,
            "created_at": url.created_at,
            "expires_at": url.expires_at,
            "recent_clicks": recent_clicks
        }

    @staticmethod
    async def get_user_urls(db: AsyncSession, user_id: UUID, skip: int = 0, limit: int = 100) -> List[URL]:
        """Get all URLs for a specific user."""
        result = await db.execute(
            select(URL)
            .where(URL.user_id == user_id, URL.is_active == True)
            .order_by(URL.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def bulk_assign_user(db: AsyncSession, url_ids: List[UUID], user_id: UUID) -> List[UUID]:
        """Assign user_id to a list of URLs (only updates URLs not already owned by another user)."""
        result = await db.execute(
            update(URL)
            .where(URL.id.in_(url_ids), URL.is_active == True)
            .values(user_id=user_id)
            .returning(URL.id)
        )
        updated_ids = result.scalars().all()
        if updated_ids:
            await db.commit()
        return list(updated_ids)

    @staticmethod
    async def get_user_click_events_summary(db: AsyncSession, user_id: UUID) -> dict:
        """Get aggregate click metrics across active links for a user."""
        result = await db.execute(
            select(
                func.coalesce(func.sum(URL.click_count), 0).label("total_clicks"),
                func.count(URL.id).label("active_links"),
            )
            .where(URL.user_id == user_id, URL.is_active.is_(True))
        )
        total_clicks, active_links = result.one()
        return {
            "total_clicks": int(total_clicks or 0),
            "active_links": int(active_links or 0),
        }

