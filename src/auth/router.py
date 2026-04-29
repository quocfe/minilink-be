from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response, Cookie
from fastapi.concurrency import run_in_threadpool
import jwt
from datetime import datetime, timezone, timedelta
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_id
from src.config import settings
from src.database import get_db
from src.auth.utils import verify_google_credential, create_access_token, create_refresh_token, decode_token
from src.redis.client import redis_client
from src.auth.schemas import GoogleAuthRequest, LoginRequest, MessageResponse, UserResponse, UserCreate, TokenResponse, RefreshTokenRequest, ForgotPasswordRequest, ResetPasswordRequest, VerifyOtpRequest
from src.auth.service import UserService, BlacklistService, VerificationCodeService
from src.email.service import EmailService
from src.logger import get_logger

logger = get_logger("auth_router")


router = APIRouter(prefix="/auth")


def _refresh_session_key(user_id: str, jti: str) -> str:
    return f"auth:refresh:{user_id}:{jti}"


async def _issue_tokens(user_id: str, response: Response) -> TokenResponse:
    """Create a new access/refresh token pair, set HttpOnly cookies, and return them."""
    access_token, access_jti = create_access_token(user_id=user_id)
    refresh_token, refresh_jti = create_refresh_token(user_id=user_id)

    # Persist refresh token session in Redis
    await redis_client.set(
        _refresh_session_key(user_id, refresh_jti),
        "1",
        expire=settings.refresh_token_expire_minutes * 60,
    )

    # Debug log (xem trong log của backend)
    logger.info(f"[Cookie Debug] Setting cookies: domain={settings.cookie_domain}, secure={settings.cookie_secure}, samesite={settings.cookie_samesite}")

    # Set access token cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.access_token_expire_minutes * 60,
        domain=settings.cookie_domain,
    )

    # Set refresh token cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_expire_minutes * 60,
        domain=settings.cookie_domain,
    )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and return JWT tokens in response body + HttpOnly cookies."""
    user = await UserService.authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return await _issue_tokens(user_id=str(user.id), response=response)


@router.post("/google", response_model=TokenResponse)
async def google_login(
    payload: GoogleAuthRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user with Google credential and return JWT tokens in response body + HttpOnly cookies."""
    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID is not configured")

    try:
        google_payload = await run_in_threadpool(
            verify_google_credential,
            payload.credential,
            settings.google_client_id,
        )
    except ValueError as exc:
        logger.error(f"Credential verification failed: {exc}")
        raise HTTPException(status_code=401, detail="Invalid Google credential") from exc

    email = google_payload.get("email")
    email_verified = google_payload.get("email_verified")
    if not email or not email_verified:
        raise HTTPException(status_code=401, detail="Google account email is not verified")

    user = await UserService.get_or_create_user_by_email(db, str(email).lower())
    return await _issue_tokens(user_id=str(user.id), response=response)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Rotate refresh token: blacklist the old one and issue a new token pair in body + cookies."""
    try:
        token_payload = decode_token(payload.refresh_token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Refresh token has expired") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc

    if token_payload.get("token_type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    raw_user_id = token_payload.get("user_id") or token_payload.get("sub")
    refresh_jti = token_payload.get("jti")
    if not raw_user_id or not refresh_jti:
        raise HTTPException(status_code=401, detail="Invalid refresh token payload")

    user_id = str(raw_user_id)
    try:
        user_uuid = UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid user id in refresh token") from exc

    session_key = _refresh_session_key(user_id, str(refresh_jti))
    session_exists = await redis_client.get(session_key)
    if not session_exists:
        raise HTTPException(status_code=401, detail="Refresh token is invalid or already used")

    user = await UserService.get_user_by_id(db, user_uuid)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    # One-time use: revoke old refresh token session and blacklist its JTI.
    await redis_client.delete(session_key)
    exp_ts = token_payload.get("exp")
    expires_at = (
        datetime.fromtimestamp(exp_ts, tz=timezone.utc)
        if exp_ts
        else datetime.now(timezone.utc) + timedelta(minutes=settings.refresh_token_expire_minutes)
    )
    await BlacklistService.add_jti(
        db,
        jti=str(refresh_jti),
        token_type="refresh",
        expires_at=expires_at,
        user_id=user_uuid,
        reason="refresh_rotation",
    )

    return await _issue_tokens(user_id=user_id, response=response)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    payload: Optional[RefreshTokenRequest] = None,
    refresh_token_cookie: Optional[str] = Cookie(default=None, alias="refresh_token"),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Logout: blacklist tokens and clear cookies."""
    token_to_blacklist = payload.refresh_token if payload else refresh_token_cookie

    if token_to_blacklist:
        try:
            rt_payload = decode_token(token_to_blacklist)
            refresh_jti = rt_payload.get("jti")
            if refresh_jti:
                exp_ts = rt_payload.get("exp")
                expires_at = (
                    datetime.fromtimestamp(exp_ts, tz=timezone.utc)
                    if exp_ts
                    else datetime.now(timezone.utc) + timedelta(minutes=settings.refresh_token_expire_minutes)
                )
                # Remove from Redis
                session_key = _refresh_session_key(str(current_user_id), str(refresh_jti))
                await redis_client.delete(session_key)
                # Blacklist in DB
                await BlacklistService.add_jti(
                    db,
                    jti=str(refresh_jti),
                    token_type="refresh",
                    expires_at=expires_at,
                    user_id=current_user_id,
                    reason="logout",
                )
        except jwt.PyJWTError:
            pass

    # Clear cookies
    response.delete_cookie(key="access_token", domain=settings.cookie_domain)
    response.delete_cookie(key="refresh_token", domain=settings.cookie_domain)

    return MessageResponse(message="Logged out successfully")


@router.post("/logout/all", response_model=MessageResponse)
async def logout_all_sessions(
    response: Response,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Revoke ALL refresh token sessions for the current user and clear cookies."""
    pattern = _refresh_session_key(str(current_user_id), "*")
    keys = await redis_client.keys(pattern)
    if keys:
        await redis_client.delete_many(*keys)

    # Clear cookies
    response.delete_cookie(key="access_token", domain=settings.cookie_domain)
    response.delete_cookie(key="refresh_token", domain=settings.cookie_domain)

    return MessageResponse(message=f"Logged out from all sessions ({len(keys)} session(s) revoked)")


@router.post("/register", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new user account."""
    try:
        user = await UserService.create_user(db, user_data)
        # Send welcome email (fire-and-forget; don't fail the request if mail errors)
        try:
            await EmailService.send_welcome_email(user.email)
        except Exception as mail_exc:
            logger.error(f"Failed to send welcome email: {mail_exc}")
        return UserResponse(
            id=user.id,
            email=user.email,
            created_at=user.created_at
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get the currently authenticated user's information."""
    user = await UserService.get_user_by_id(db, current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=user.id,
        email=user.email,
        created_at=user.created_at
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Request a 5-digit reset code sent to the given email."""
    # Always return the same message to avoid user enumeration
    user = await UserService.get_user_by_email(db, payload.email.lower())
    if user:
        try:
            await VerificationCodeService.request_code(
                db=db,
                redis_client=redis_client,
                email=user.email,
            )
        except ValueError as exc:
            raise HTTPException(status_code=429, detail=str(exc))
    return MessageResponse(message="If the email is registered, a reset code has been sent.")


@router.post("/verify-otp", response_model=MessageResponse)
async def verify_otp(
    payload: VerifyOtpRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify the 5-digit OTP code for the given email without consuming it."""
    try:
        await VerificationCodeService.verify_code(
            db=db,
            email=payload.email.lower(),
            code=payload.code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return MessageResponse(message="OTP is valid.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify the 5-digit code and set a new password."""
    try:
        await VerificationCodeService.reset_password(
            db=db,
            email=payload.email.lower(),
            code=payload.code,
            new_password=payload.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return MessageResponse(message="Password has been reset successfully.")

