from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LinkCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "original_url": "https://example.com/long/path",
                    "custom_alias": "my-link",
                    "expires_at": "2030-12-31T23:59:00Z",
                },
                {
                    "original_url": "https://example.com/another/path",
                    "custom_alias": None,
                    "expires_at": None,
                },
            ]
        }
    )

    original_url: HttpUrl
    custom_alias: str | None = Field(default=None, min_length=3, max_length=64)
    expires_at: datetime | None = None


class LinkUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "original_url": "https://example.com/updated/path",
                    "expires_at": "2030-12-31T23:59:00Z",
                }
            ]
        }
    )

    original_url: HttpUrl
    expires_at: datetime | None = None


class LinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    short_code: str
    short_url: str
    original_url: str
    created_at: datetime
    expires_at: datetime | None = None
    owner_id: int | None = None


class LinkStatsResponse(BaseModel):
    short_code: str
    original_url: str
    created_at: datetime
    click_count: int
    last_used_at: datetime | None
    expires_at: datetime | None


class SearchResponse(BaseModel):
    found: bool
    short_code: str | None = None
    short_url: str | None = None
    original_url: str | None = None


class CleanupResponse(BaseModel):
    deleted_count: int
    inactive_days: int


class ExpiredLinkItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    original_url: str
    short_code: str
    expired_at: datetime
    created_at: datetime
    last_used_at: datetime | None
    click_count: int
