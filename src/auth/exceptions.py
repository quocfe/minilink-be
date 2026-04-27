"""Auth-specific exceptions with machine-readable error codes."""
from fastapi import HTTPException


class AuthException(HTTPException):
    """Base auth exception that carries a machine-readable `code` for the frontend."""

    def __init__(self, status_code: int, detail: str, code: str):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code


class InvalidCredentialsError(AuthException):
    """Wrong email / password at login."""
    def __init__(self, detail: str = "Invalid credentials"):
        super().__init__(status_code=401, detail=detail, code="INVALID_CREDENTIALS")


class TokenExpiredError(AuthException):
    """Access token exists but has expired → frontend should refresh."""
    def __init__(self, detail: str = "Token has expired"):
        super().__init__(status_code=401, detail=detail, code="TOKEN_EXPIRED")


class InvalidTokenError(AuthException):
    """Token is present but malformed / tampered / wrong type → must re-login."""
    def __init__(self, detail: str = "Invalid token"):
        super().__init__(status_code=403, detail=detail, code="INVALID_TOKEN")


class UserNotFoundError(AuthException):
    """Authenticated but the user no longer exists in the database."""
    def __init__(self, detail: str = "User not found"):
        super().__init__(status_code=404, detail=detail, code="USER_NOT_FOUND")


class EmailAlreadyRegisteredError(AuthException):
    """Registration conflict — email is already taken."""
    def __init__(self, detail: str = "Email already registered"):
        super().__init__(status_code=409, detail=detail, code="EMAIL_ALREADY_REGISTERED")
