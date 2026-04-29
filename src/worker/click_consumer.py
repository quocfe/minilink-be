import asyncio
import logging
from datetime import datetime
from collections import defaultdict
from typing import Optional
from uuid import UUID

from sqlalchemy import insert, update
from sqlalchemy.orm import configure_mappers

from src.database import async_session_factory
from src.kafka.client import KafkaConsumerClient
from src.config import settings
# Both model modules MUST be imported before configure_mappers() is called so
# that SQLAlchemy can resolve all string-based relationships (e.g. "User" in
# URL.user) eagerly at startup rather than lazily on the first DB operation.
from src.auth.models import User  # noqa: F401 – registers User with the mapper
from src.urls.models import ClickEvent, URL

# Force SQLAlchemy to resolve all relationship() strings NOW, while all models
# are guaranteed to be in the registry. Without this, the worker crashes on the
# first DB flush with: 'User' failed to locate a name.
configure_mappers()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("click_consumer")

# ─── Configuration ────────────────────────────────────────────────────────────
CONSUMER_GROUP = "minilink-analytics-group"
BATCH_SIZE = 100          # flush after this many events
FLUSH_INTERVAL = 5.0      # flush every N seconds regardless of batch size


# ─── Mock GeoIP ───────────────────────────────────────────────────────────────
def resolve_country(ip: Optional[str]) -> Optional[str]:
    """
    Mock IP-to-Country resolution.
    Replace with a real GeoIP library (e.g. geoip2) in production.
    """
    if not ip:
        return None
    # Stub: first octet → fake country mapping for demo purposes
    first_octet = ip.split(".")[0] if "." in ip else ""
    mock_map = {"1": "US", "2": "GB", "3": "DE", "4": "FR", "5": "JP"}
    return mock_map.get(first_octet, "XX")


# ─── Consumer ─────────────────────────────────────────────────────────────────
class ClickConsumer:
    def __init__(self):
        self._client = KafkaConsumerClient(
            group_id=CONSUMER_GROUP,
            topics=[settings.kafka_click_topic],
        )
        self._buffer: list[dict] = []
        self._last_flush: float = asyncio.get_event_loop().time()

    # ------------------------------------------------------------------
    async def _flush(self):
        """Bulk-insert buffered events into PostgreSQL and clear the buffer."""
        if not self._buffer:
            return

        batch = self._buffer[:]
        self._buffer.clear()
        self._last_flush = asyncio.get_event_loop().time()

        rows = []
        click_count_by_url: dict[UUID, int] = defaultdict(int)
        for event in batch:
            try:
                logger.info(f"Received event: {event}")
                url_id = UUID(event["url_id"])
                rows.append({
                    "url_id": url_id,
                    "clicked_at": datetime.fromisoformat(event["clicked_at"]),
                    "country": resolve_country(event.get("ip")),
                    "device": _extract_device(event.get("user_agent")),
                    "referrer": event.get("referrer"),
                })
                click_count_by_url[url_id] += 1
            except Exception as e:
                logger.error(f"Skipping malformed event: {e} | {event}")

        if not rows:
            return

        try:
            async with async_session_factory() as db:
                await db.execute(insert(ClickEvent), rows)
                for url_id, increment_by in click_count_by_url.items():
                    await db.execute(
                        update(URL)
                        .where(URL.id == url_id)
                        .values(click_count=URL.click_count + increment_by)
                    )
                await db.commit()
            logger.info(
                f"Flushed {len(rows)} click events to DB and "
                f"updated {len(click_count_by_url)} URL counters"
            )
        except Exception as e:
            logger.error(f"DB flush error: {e}")

    # ------------------------------------------------------------------
    async def _handle_message(self, data: dict):
        """Buffer an incoming Kafka message and flush if thresholds are met."""
        self._buffer.append(data)

        elapsed = asyncio.get_event_loop().time() - self._last_flush
        if len(self._buffer) >= BATCH_SIZE or elapsed >= FLUSH_INTERVAL:
            await self._flush()

    # ------------------------------------------------------------------
    async def _periodic_flush(self):
        """Background task: flush the buffer every FLUSH_INTERVAL seconds."""
        while True:
            await asyncio.sleep(FLUSH_INTERVAL)
            await self._flush()

    # ------------------------------------------------------------------
    async def start_consuming(self):
        """Start the consumer and the periodic flush task."""
        logger.info(
            f"[ClickConsumer] Starting — group={CONSUMER_GROUP}, "
            f"topic={settings.kafka_click_topic}, "
            f"batch_size={BATCH_SIZE}, flush_interval={FLUSH_INTERVAL}s"
        )

        await self._client.start()

        # Run periodic flush alongside the consumer loop
        flush_task = asyncio.create_task(self._periodic_flush())
        try:
            await self._client.consume_messages(self._handle_message)
        finally:
            flush_task.cancel()
            await self._flush()          # drain remaining events on shutdown
            await self._client.stop()


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _extract_device(user_agent: Optional[str]) -> Optional[str]:
    if not user_agent:
        return None
    ua = user_agent.lower()
    if any(x in ua for x in ("iphone", "android", "mobile")):
        return "mobile"
    if any(x in ua for x in ("ipad", "tablet")):
        return "tablet"
    return "desktop"


# ─── Entry point ──────────────────────────────────────────────────────────────
async def main():
    consumer = ClickConsumer()
    await consumer.start_consuming()


if __name__ == "__main__":
    asyncio.run(main())

