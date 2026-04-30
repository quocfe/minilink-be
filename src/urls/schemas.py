from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, HttpUrl, validator, Field


class URLCreate(BaseModel):
    original_url: HttpUrl = Field(..., description="The original URL to shorten")
    custom_code: Optional[str] = Field(None, description="Custom short code (optional)")
    expires_in_days: Optional[int] = Field(None, gt=0, le=365, description="Expiration in days (max 365)")

    @validator('custom_code', pre=True)
    def validate_custom_code(cls, v):
        # Treat empty string / whitespace-only as "not provided"
        if v is not None and isinstance(v, str):
            v = v.strip()
            if v == '':
                return None
        if v is not None:
            if len(v) < 3 or len(v) > 10:
                raise ValueError('Mã tùy chỉnh phải từ 3 đến 10 ký tự')
            if not v.replace('_', '').replace('-', '').isalnum():
                raise ValueError('Mã tùy chỉnh chỉ được chứa chữ cái, số, dấu gạch ngang và gạch dưới')
        return v



class URLResponse(BaseModel):
    id: UUID
    short_code: str
    short_url: str
    original_url: str
    expires_at: Optional[datetime] = None
    is_active: bool
    click_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class ClickEventsSummary(BaseModel):
    total_clicks: int
    active_links: int


class UserLinksResponse(BaseModel):
    links: List[URLResponse]
    click_events: ClickEventsSummary


class URLUpdate(BaseModel):
    original_url: Optional[HttpUrl] = None
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None


class ClickEventCreate(BaseModel):
    url_id: UUID
    country: Optional[str] = Field(None, max_length=2, description="ISO country code")
    device: Optional[str] = Field(None, max_length=100, description="Device information")
    referrer: Optional[str] = None


class ClickEventResponse(BaseModel):
    id: int
    url_id: UUID
    clicked_at: datetime
    country: Optional[str]
    device: Optional[str]
    referrer: Optional[str]

    class Config:
        from_attributes = True


class BulkAssignUserRequest(BaseModel):
    url_ids: List[UUID] = Field(..., min_length=1, description="List of URL IDs to assign to current user")


class BulkAssignUserResponse(BaseModel):
    updated_count: int
    updated_ids: List[UUID]


class URLStats(BaseModel):
    id: UUID
    short_code: str
    original_url: str
    total_clicks: int
    created_at: datetime
    expires_at: Optional[datetime] = None
    recent_clicks: List[ClickEventResponse]

    class Config:
        from_attributes = True

