from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app import cache as cache_module
from app.auth import create_access_token, get_current_user, get_optional_user, hash_password, verify_password
from app.database import get_db
from app.main import build_short_url, delete_if_expired, generate_short_code, link_to_response, normalize_datetime
from app.models import ExpiredLink, Link


def test_generate_short_code_returns_short_non_empty_values() -> None:
    codes = {generate_short_code() for _ in range(20)}
    assert len(codes) == 20
    assert all(1 <= len(code) <= 8 for code in codes)


def test_normalize_datetime_rounds_to_minute_and_forces_utc() -> None:
    dt = datetime(2030, 1, 1, 12, 34, 56)
    normalized = normalize_datetime(dt)

    assert normalized == datetime(2030, 1, 1, 12, 34, tzinfo=timezone.utc)


def test_build_short_url_uses_request_base_when_base_url_not_set() -> None:
    scope = {
        "type": "http",
        "scheme": "https",
        "server": ("testserver.local", 443),
        "path": "/",
        "headers": [],
    }
    request = Request(scope)

    result = build_short_url("abc123", request)

    assert result == "https://testserver.local/links/abc123"


def test_build_short_url_falls_back_to_localhost() -> None:
    assert build_short_url("abc123") == "http://localhost:8000/links/abc123"


def test_link_to_response_contains_short_url() -> None:
    link = Link(
        original_url="https://example.com/item",
        short_code="item-code",
        created_at=datetime.now(timezone.utc),
    )
    response = link_to_response(link)

    assert response.short_code == "item-code"
    assert response.short_url.endswith("/links/item-code")


def test_hash_password_and_verify_password() -> None:
    password = "secret123"
    password_hash = hash_password(password)

    assert password_hash != password
    assert verify_password(password, password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_create_access_token_returns_string() -> None:
    token = create_access_token(123)
    assert isinstance(token, str)
    assert token


def test_get_optional_user_returns_none_for_missing_credentials(db_session: Session) -> None:
    user = get_optional_user(credentials=None, db=db_session)
    assert user is None


def test_get_optional_user_returns_none_for_invalid_token(db_session: Session) -> None:
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token")
    user = get_optional_user(credentials=credentials, db=db_session)
    assert user is None


def test_get_current_user_requires_authorization(db_session: Session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials=None, db=db_session)

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_invalid_token(db_session: Session) -> None:
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token")

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials=credentials, db=db_session)

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_missing_user(db_session: Session) -> None:
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_access_token(999))

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials=credentials, db=db_session)

    assert exc_info.value.status_code == 401


def test_delete_if_expired_moves_link_to_history(db_session: Session) -> None:
    link = Link(
        original_url="https://example.com/expired-now",
        short_code="expired-now",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)

    result = delete_if_expired(db_session, link)

    assert result is True
    assert db_session.query(Link).filter_by(short_code="expired-now").first() is None
    archived = db_session.query(ExpiredLink).filter_by(short_code="expired-now").first()
    assert archived is not None


def test_delete_if_expired_keeps_active_link(db_session: Session) -> None:
    link = Link(
        original_url="https://example.com/future",
        short_code="future-link",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)

    result = delete_if_expired(db_session, link)

    assert result is False
    assert db_session.query(Link).filter_by(short_code="future-link").first() is not None


def test_get_db_yields_and_closes_session(mocker) -> None:
    fake_session = mocker.Mock()
    mocker.patch("app.database.SessionLocal", return_value=fake_session)

    generator = get_db()
    yielded = next(generator)

    assert yielded is fake_session
    with pytest.raises(StopIteration):
        next(generator)
    fake_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_cache_helpers_return_none_without_redis() -> None:
    cache_module.redis_client = None

    assert await cache_module.cache_get("missing") is None
    assert await cache_module.cache_set("k", {"v": 1}) is None
    assert await cache_module.cache_delete("k") is None


@pytest.mark.asyncio
async def test_cache_helpers_work_with_fake_redis(mocker) -> None:
    fake_redis = mocker.AsyncMock()
    fake_redis.get.return_value = '{"answer": 42}'
    cache_module.redis_client = fake_redis

    value = await cache_module.cache_get("key")
    await cache_module.cache_set("key", {"answer": 42}, ttl=10)
    await cache_module.cache_delete("key")

    assert value == {"answer": 42}
    fake_redis.set.assert_awaited_once()
    fake_redis.delete.assert_awaited_once_with("key")


@pytest.mark.asyncio
async def test_cache_get_handles_bad_json(mocker) -> None:
    fake_redis = mocker.AsyncMock()
    fake_redis.get.return_value = "{bad-json"
    cache_module.redis_client = fake_redis

    value = await cache_module.cache_get("key")

    assert value is None
