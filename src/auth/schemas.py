from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, validator
from typing import Optional
import re


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email")
    password: str = Field(..., min_length=8, description="User password")


class GoogleAuthRequest(BaseModel):
    credential: str = Field(..., min_length=10, description="Google ID token credential")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10, description="Refresh token")


class UserCreate(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="User password (min 8 characters)")

    @validator('email')
    def validate_email(cls, v):
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', v):
            raise ValueError('Invalid email format')
        return v.lower()


class UserResponse(BaseModel):
    id: UUID
    email: str
    created_at: datetime

    class Config:
        from_attributes = True


class VerifyOtpRequest(BaseModel):
    email: str = Field(..., description="User email")
    code: str = Field(..., min_length=5, max_length=5, description="5-digit OTP code")


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., description="Email to send reset code to")


class ResetPasswordRequest(BaseModel):
    email: str = Field(..., description="User email")
    code: str = Field(..., min_length=5, max_length=5, description="5-digit reset code")
    password: str = Field(..., min_length=6, description="New password (min 6 characters)")
    confirm_password: str = Field(..., min_length=6, description="Confirm new password")

    @validator("confirm_password")
    def passwords_match(cls, v, values):
        if "password" in values and v != values["password"]:
            raise ValueError("Passwords do not match")
        return v


