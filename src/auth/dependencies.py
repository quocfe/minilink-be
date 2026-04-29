from typing import Optional
from uuid import UUID

import jwt
from fastapi import Cookie, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.auth.utils import decode_token
from src.auth.service import UserService, BlacklistService
from src.auth.exceptions import TokenExpiredError, InvalidTokenError


bearer_scheme = HTTPBearer(auto_error=False)


def _extract_token(
    cookie_token: Optional[str],
    credentials: Optional[HTTPAuthorizationCredentials],
) -> Optional[str]:
    """Return token from cookie, falling back to Bearer header."""
    if cookie_token:
        return cookie_token
    if credentials:
        return credentials.credentials
    return None


async def get_optional_current_user_id(
    access_token: Optional[str] = Cookie(default=None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[UUID]:
    # Log để debug
    print(f"[Auth Debug] Cookie 'access_token' received: {access_token is not None}")
    token = _extract_token(access_token, credentials)
    if not token:
        return None

    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError() from exc
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc

    token_type = payload.get("token_type")
    if token_type == "refresh":
        raise HTTPException(status_code=403, detail="Invalid token type")

    # Check blacklist
    jti = payload.get("jti")
    if jti and await BlacklistService.is_blacklisted(db, jti):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    raw_user_id = payload.get("user_id") or payload.get("sub")
    if not raw_user_id:
        raise HTTPException(status_code=404, detail="Token missing user id")

    try:
        user_id = UUID(str(raw_user_id))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid user id in token") from exc

    user = await UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user_id


async def get_current_user_id(
    user_id: Optional[UUID] = Depends(get_optional_current_user_id),
) -> UUID:
    """Like get_optional_current_user_id but raises 401 if the user is not authenticated."""
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id
