from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from uuid import uuid4

import jwt
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from src.config import settings


def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> tuple[str, str]:
    """Create a signed JWT access token for a user. Returns (token, jti)."""
    expire_delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    expire_at = datetime.now(timezone.utc) + expire_delta
    jti = str(uuid4())

    payload = {
        "sub": user_id,
        "user_id": user_id,
        "token_type": "access",
        "jti": jti,
        "exp": expire_at,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm), jti


def create_refresh_token(user_id: str, expires_delta: Optional[timedelta] = None) -> tuple[str, str]:
    """Create a signed JWT refresh token and return (token, jti)."""
    expire_delta = expires_delta or timedelta(minutes=settings.refresh_token_expire_minutes)
    expire_at = datetime.now(timezone.utc) + expire_delta
    jti = str(uuid4())

    payload = {
        "sub": user_id,
        "user_id": user_id,
        "token_type": "refresh",
        "jti": jti,
        "exp": expire_at,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm), jti


def decode_token(token: str) -> dict:
    """Decode and validate JWT token signature/expiry."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


def verify_google_credential(credential: str, audience: str) -> Dict[str, Any]:
    """Use Google's official library to verify an ID Token."""
    print(f"Verifying Google credential for audience: {audience}")
    try:
        id_info = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            audience
        )
        return id_info
    except ValueError as exc:
        print(f"Google verify error: {exc}")
        raise ValueError(f"Invalid Google credential: {str(exc)}") from exc

