import asyncio
import json
from typing import Any, Dict, Optional, Callable
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError
from src.config import settings
from src.logger import get_logger

logger = get_logger("kafka_client")

# Retry configuration
_RETRY_ATTEMPTS = 10
_RETRY_BASE_DELAY = 2.0   # seconds
_RETRY_MAX_DELAY = 30.0   # seconds


class KafkaProducer:
    def __init__(self):
        self._producer: Optional[AIOKafkaProducer] = None

    async def start(self):
        """Start the Kafka producer with retry/backoff on connection failure."""
        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            self._producer = AIOKafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                client_id="minilink-producer",
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
            )
            try:
                await self._producer.start()
                logger.info(f"Connected to Kafka (attempt {attempt})")
                return
            except Exception as e:
                await self._producer.stop()
                self._producer = None
                delay = min(_RETRY_BASE_DELAY * (2 ** (attempt - 1)), _RETRY_MAX_DELAY)
                logger.warning(
                    f"Unable to connect to Kafka "
                    f"(attempt {attempt}/{_RETRY_ATTEMPTS}): {e}. "
                    f"Retrying in {delay:.1f}s…"
                )
                if attempt == _RETRY_ATTEMPTS:
                    raise
                await asyncio.sleep(delay)

    async def stop(self):
        """Stop the Kafka producer."""
        if self._producer:
            await self._producer.stop()

    async def send_message(self, topic: str, message: Dict[str, Any], key: str = None):
        """Send message to Kafka topic (fire-and-forget)."""
        if not self._producer:
            await self.start()
        try:
            await self._producer.send(topic=topic, value=message, key=key)
        except Exception as e:
            logger.error(f"Error sending message to {topic}: {e}")


class KafkaConsumerClient:
    def __init__(self, group_id: str, topics: list):
        self._group_id = group_id
        self._topics = topics
        self._consumer: Optional[AIOKafkaConsumer] = None

    async def start(self):
        """Start the Kafka consumer with retry/backoff on connection failure."""
        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            self._consumer = AIOKafkaConsumer(
                *self._topics,
                bootstrap_servers=settings.kafka_bootstrap_servers,
                group_id=self._group_id,
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            )
            try:
                await self._consumer.start()
                logger.info(f"Connected to Kafka (attempt {attempt})")
                return
            except Exception as e:
                await self._consumer.stop()
                self._consumer = None
                delay = min(_RETRY_BASE_DELAY * (2 ** (attempt - 1)), _RETRY_MAX_DELAY)
                logger.warning(
                    f"Unable to connect to Kafka "
                    f"(attempt {attempt}/{_RETRY_ATTEMPTS}): {e}. "
                    f"Retrying in {delay:.1f}s…"
                )
                if attempt == _RETRY_ATTEMPTS:
                    raise
                await asyncio.sleep(delay)

    async def stop(self):
        """Stop the Kafka consumer."""
        if self._consumer:
            await self._consumer.stop()

    async def consume_messages(self, message_handler: Callable):
        """Consume messages from subscribed topics, passing each to the handler."""
        if not self._consumer:
            await self.start()
        try:
            async for msg in self._consumer:
                try:
                    await message_handler(msg.value)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        finally:
            await self.stop()


async def create_topics():
    """Create Kafka topics if they don't exist."""
    admin = AIOKafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap_servers)
    try:
        await admin.start()
        topics = [
            NewTopic(
                name=settings.kafka_click_topic,
                num_partitions=3,
                replication_factor=1,
            )
        ]
        try:
            await admin.create_topics(topics)
            logger.info(f"Topic '{settings.kafka_click_topic}' created")
        except TopicAlreadyExistsError:
            logger.info(f"Topic '{settings.kafka_click_topic}' already exists")
        except Exception as e:
            logger.error(f"Failed to create topics: {e}")
    finally:
        await admin.close()


# Global Kafka producer instance
kafka_producer = KafkaProducer()

