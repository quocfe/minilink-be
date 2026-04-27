import enum
import uuid
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.database import Base


class VerificationCodeStatus(str, enum.Enum):
    PENDING = "PENDING"      # code sent, waiting for user to enter it
    VERIFIED = "VERIFIED"    # user entered correct code, can now reset password
    USED = "USED"            # flow completed (password reset) or superseded


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationship with URLs
    urls = relationship("URL", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}')>"


class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    jti = Column(String(255), unique=True, index=True, nullable=False)
    token_type = Column(String(50), nullable=False)  # "access" or "refresh"
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    blacklisted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reason = Column(String(50), nullable=True)  # "logout", "refresh_rotation", "expired"

    def __repr__(self):
        return f"<TokenBlacklist(jti={self.jti}, type={self.token_type}, reason={self.reason})>"


class VerificationCode(Base):
    __tablename__ = "codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(10), nullable=False)
    type = Column(String(50), nullable=False)  # e.g. "forgot_password"
    email = Column(String(255), nullable=False, index=True)
    status = Column(
        Enum(VerificationCodeStatus, name="verificationcodestatus"),
        default=VerificationCodeStatus.PENDING,
        nullable=False,
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<VerificationCode(email={self.email}, type={self.type}, status={self.status})>"
