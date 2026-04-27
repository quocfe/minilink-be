import uuid
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey, BigInteger, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.database import Base


class URL(Base):
    __tablename__ = "urls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    short_code = Column(String(10), unique=True, index=True, nullable=False)
    original_url = Column(Text, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    click_count = Column(Integer, default=0, nullable=False)

    # Relationships
    user = relationship("User", back_populates="urls")
    click_events = relationship("ClickEvent", back_populates="url", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<URL(id={self.id}, short_code='{self.short_code}', original_url='{self.original_url}')>"


class ClickEvent(Base):
    __tablename__ = "click_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    url_id = Column(UUID(as_uuid=True), ForeignKey("urls.id"), nullable=False, index=True)
    clicked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    country = Column(String(2), nullable=True)  # ISO country code
    device = Column(String(100), nullable=True)
    referrer = Column(Text, nullable=True)

    # Relationship
    url = relationship("URL", back_populates="click_events")

    # Composite indexes for better query performance
    __table_args__ = (
        Index('idx_click_events_url_id_clicked_at', 'url_id', 'clicked_at'),
        Index('idx_click_events_clicked_at', 'clicked_at'),
    )

    def __repr__(self):
        return f"<ClickEvent(id={self.id}, url_id='{self.url_id}', clicked_at='{self.clicked_at}')>"

