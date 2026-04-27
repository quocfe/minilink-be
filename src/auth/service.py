from datetime import datetime, timezone, timedelta
from typing import Optional
import random
import uuid
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from sqlalchemy.exc import IntegrityError
from passlib.context import CryptContext
from src.auth.models import User, TokenBlacklist, VerificationCode, VerificationCodeStatus
from src.auth.schemas import UserCreate

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Generate password hash."""
        return pwd_context.hash(password)

    @staticmethod
    async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
        """Create a new user."""
        try:
            hashed_password = UserService.get_password_hash(user_data.password)
            user = User(
                email=user_data.email,
                password_hash=hashed_password
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            return user
        except IntegrityError:
            await db.rollback()
            raise ValueError("Email already registered")

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """Get user by email."""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password."""
        user = await UserService.get_user_by_email(db, email)
        if not user:
            return None
        if not UserService.verify_password(password, user.password_hash):
            return None
        return user

    @staticmethod
    async def get_or_create_user_by_email(db: AsyncSession, email: str) -> User:
        """Get existing user by email, or create one for social login flows."""
        user = await UserService.get_user_by_email(db, email)
        if user:
            return user

        temp_password = f"google-{uuid.uuid4()}"
        user = User(email=email, password_hash=UserService.get_password_hash(temp_password))
        db.add(user)
        try:
            await db.commit()
            await db.refresh(user)
            return user
        except IntegrityError:
            # Handle race condition when two requests create the same email concurrently.
            await db.rollback()
            existing = await UserService.get_user_by_email(db, email)
            if existing:
                return existing
            raise

    @staticmethod
    async def update_user_tokens(
        db: AsyncSession, user_id: UUID, access_token: str, refresh_token: str
    ) -> None:
        """Store the latest issued access and refresh tokens on the user record."""
        user = await UserService.get_user_by_id(db, user_id)
        if user:
            user.access_token = access_token
            user.refresh_token = refresh_token
            await db.commit()


class BlacklistService:
    @staticmethod
    async def add_jti(
        db: AsyncSession,
        jti: str,
        token_type: str,
        expires_at: datetime,
        user_id: Optional[UUID] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Add a JWT ID to the blacklist."""
        entry = TokenBlacklist(
            jti=jti,
            token_type=token_type,
            user_id=user_id,
            expires_at=expires_at,
            reason=reason,
        )
        db.add(entry)
        try:
            await db.commit()
        except IntegrityError:
            # Already blacklisted — ignore duplicate.
            await db.rollback()

    @staticmethod
    async def is_blacklisted(db: AsyncSession, jti: str) -> bool:
        """Return True if the given JTI is on the blacklist."""
        result = await db.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == jti)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def cleanup_expired(db: AsyncSession) -> int:
        """Delete blacklist entries whose natural expiry has already passed."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            delete(TokenBlacklist).where(TokenBlacklist.expires_at < now)
        )
        await db.commit()
        return result.rowcount


# ── Verification Code ────────────────────────────────────────────────────────

CODE_TYPE_FORGOT_PASSWORD = "forgot_password"
_RATE_LIMIT_TTL = 5 * 60          # 5 minutes in seconds
_CODE_EXPIRE_MINUTES = 10


def _rate_limit_key(email: str, code_type: str) -> str:
    return f"pwd_reset:rl:{code_type}:{email}"


class VerificationCodeService:
    @staticmethod
    def _generate_code() -> str:
        """Generate a random 5-digit numeric code."""
        return str(random.randint(10000, 99999))

    @staticmethod
    async def request_code(
        db: AsyncSession,
        redis_client,
        email: str,
        code_type: str = CODE_TYPE_FORGOT_PASSWORD,
    ) -> None:
        """
        Rate-limited code request flow:
        1. Check Redis rate limit (once per 5 min per email+type).
        2. Invalidate all previous unused codes for same email+type.
        3. Insert new code valid for _CODE_EXPIRE_MINUTES.
        4. Set Redis rate-limit key.
        5. Send email (imported lazily to avoid circular deps).
        """
        rl_key = _rate_limit_key(email, code_type)
        if await redis_client.get(rl_key):
            ttl = await redis_client.ttl(rl_key)
            raise ValueError(f"Please wait {ttl} seconds before requesting a new code.")

        # Invalidate old codes (mark as USED / superseded)
        await db.execute(
            update(VerificationCode)
            .where(
                VerificationCode.email == email,
                VerificationCode.type == code_type,
                VerificationCode.status == VerificationCodeStatus.PENDING,
            )
            .values(status=VerificationCodeStatus.USED)
        )

        # Create new code
        code = VerificationCodeService._generate_code()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=_CODE_EXPIRE_MINUTES)
        entry = VerificationCode(
            id=uuid.uuid4(),
            code=code,
            type=code_type,
            email=email,
            status=VerificationCodeStatus.PENDING,
            expires_at=expires_at,
        )
        db.add(entry)
        await db.commit()

        # Rate-limit key
        await redis_client.set(rl_key, "1", expire=_RATE_LIMIT_TTL)

        # Send email
        from src.email.service import EmailService
        await EmailService.send_forgot_password_code(
            email=email,
            code=code,
            expire_minutes=_CODE_EXPIRE_MINUTES,
        )

    @staticmethod
    async def verify_code(
        db: AsyncSession,
        email: str,
        code: str,
        code_type: str = CODE_TYPE_FORGOT_PASSWORD,
    ) -> VerificationCode:
        """Return the valid code entry (status → VERIFIED) or raise ValueError."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(VerificationCode).where(
                VerificationCode.email == email,
                VerificationCode.type == code_type,
                VerificationCode.code == code,
                VerificationCode.status == VerificationCodeStatus.PENDING,
                VerificationCode.expires_at > now,
            )
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise ValueError("Invalid or expired code.")

        # Advance status: PENDING → VERIFIED
        entry.status = VerificationCodeStatus.VERIFIED
        await db.commit()
        await db.refresh(entry)
        return entry

    @staticmethod
    async def reset_password(
        db: AsyncSession,
        email: str,
        code: str,
        new_password: str,
    ) -> None:
        """
        Reset password using a previously verified code (status must be VERIFIED).
        Caller must first call verify_code() to advance the code to VERIFIED.
        Status transitions: VERIFIED → USED.
        """
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(VerificationCode).where(
                VerificationCode.email == email,
                VerificationCode.code == code,
                VerificationCode.status == VerificationCodeStatus.VERIFIED,
                VerificationCode.expires_at > now,
            )
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise ValueError("Code not verified or has expired. Please verify your code first.")

        user = await UserService.get_user_by_email(db, email)
        if not user:
            raise ValueError("User not found.")

        user.password_hash = UserService.get_password_hash(new_password)
        # Advance status: VERIFIED → USED
        entry.status = VerificationCodeStatus.USED
        await db.commit()

