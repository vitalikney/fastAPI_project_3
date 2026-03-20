from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status
from sqlalchemy.orm import Session

from app import main as main_module
from app.auth import hash_password
from app.models import Link, User


def test_health_and_root(client) -> None:
    health = client.get("/health")
    root = client.get("/")

    assert health.status_code == status.HTTP_200_OK
    assert health.json() == {"status": "ok"}
    assert root.status_code == status.HTTP_200_OK
    assert root.json()["docs"] == "/docs"


def test_register_and_login_flow(client) -> None:
    register = client.post("/auth/register", json={"email": "user@example.com", "password": "secret123"})
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret123"})

    assert register.status_code == status.HTTP_201_CREATED
    assert register.json()["email"] == "user@example.com"
    assert login.status_code == status.HTTP_200_OK
    assert "access_token" in login.json()


def test_register_duplicate_email_returns_conflict(client, db_session: Session) -> None:
    db_session.add(User(email="dup@example.com", password_hash=hash_password("secret123")))
    db_session.commit()

    response = client.post("/auth/register", json={"email": "dup@example.com", "password": "secret123"})

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"] == "Email already registered"


def test_login_with_invalid_password_returns_unauthorized(client, db_session: Session) -> None:
    db_session.add(User(email="login@example.com", password_hash=hash_password("secret123")))
    db_session.commit()

    response = client.post("/auth/login", json={"email": "login@example.com", "password": "badpass"})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_create_short_link_without_auth(client) -> None:
    response = client.post(
        "/links/shorten",
        json={"original_url": "https://example.com/page", "custom_alias": "public-link"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["short_code"] == "public-link"
    assert body["short_url"].endswith("/links/public-link")
    assert body["owner_id"] is None


def test_create_short_link_with_auth_sets_owner(client, auth_headers) -> None:
    response = client.post(
        "/links/shorten",
        headers=auth_headers,
        json={"original_url": "https://example.com/private", "custom_alias": "private-link"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["owner_id"] is not None


def test_create_short_link_rejects_duplicate_alias(client, db_session: Session) -> None:
    db_session.add(Link(original_url="https://example.com/existing", short_code="dup-link", custom_alias="dup-link"))
    db_session.commit()

    response = client.post(
        "/links/shorten",
        json={"original_url": "https://example.com/new", "custom_alias": "dup-link"},
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"] == "custom_alias already exists"


def test_create_short_link_rejects_past_expiry(client) -> None:
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    response = client.post(
        "/links/shorten",
        json={"original_url": "https://example.com/page", "custom_alias": "exp-link", "expires_at": past_time},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "expires_at must be in the future"


def test_create_short_link_rejects_invalid_url(client) -> None:
    response = client.post(
        "/links/shorten",
        json={"original_url": "not-a-url", "custom_alias": "bad-link"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_search_returns_found_and_not_found(client, db_session: Session) -> None:
    db_session.add(Link(original_url="https://example.com/search", short_code="search-link"))
    db_session.commit()

    found = client.get("/links/search", params={"original_url": "https://example.com/search"})
    missing = client.get("/links/search", params={"original_url": "https://example.com/missing"})

    assert found.status_code == status.HTTP_200_OK
    assert found.json()["found"] is True
    assert found.json()["short_code"] == "search-link"
    assert missing.status_code == status.HTTP_200_OK
    assert missing.json() == {"found": False, "short_code": None, "short_url": None, "original_url": None}


def test_redirect_updates_click_count_and_location(client, db_session: Session) -> None:
    db_session.add(Link(original_url="https://example.com/redirect", short_code="redir-link"))
    db_session.commit()

    response = client.get("/links/redir-link", follow_redirects=False)

    assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
    assert response.headers["location"] == "https://example.com/redirect"
    link = db_session.query(Link).filter_by(short_code="redir-link").first()
    assert link is not None
    db_session.refresh(link)
    assert link.click_count == 1
    assert link.last_used_at is not None


def test_redirect_returns_404_for_missing_link(client) -> None:
    response = client.get("/links/unknown-link", follow_redirects=False)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_redirect_deletes_expired_link(client, expired_link: Link, db_session: Session) -> None:
    response = client.get(f"/links/{expired_link.short_code}", follow_redirects=False)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert db_session.query(Link).filter_by(short_code=expired_link.short_code).first() is None


def test_get_stats_returns_data(client, db_session: Session) -> None:
    link = Link(original_url="https://example.com/stats", short_code="stats-link", click_count=5)
    db_session.add(link)
    db_session.commit()

    response = client.get("/links/stats-link/stats")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["click_count"] == 5
    assert response.json()["short_code"] == "stats-link"


def test_get_stats_returns_404_for_missing_link(client) -> None:
    response = client.get("/links/no-stats/stats")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_update_link_requires_auth(client, owned_link: Link) -> None:
    response = client.put(
        f"/links/{owned_link.short_code}",
        json={"original_url": "https://example.com/new", "expires_at": "2030-01-01T00:00:00Z"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_update_link_updates_owned_resource(client, auth_headers, owned_link: Link) -> None:
    response = client.put(
        f"/links/{owned_link.short_code}",
        headers=auth_headers,
        json={"original_url": "https://example.com/updated", "expires_at": "2030-01-01T00:00:00Z"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["original_url"] == "https://example.com/updated"


def test_update_link_forbidden_for_non_owner(client, db_session: Session, owned_link: Link) -> None:
    other_user = User(email="other@example.com", password_hash=hash_password("secret123"))
    db_session.add(other_user)
    db_session.commit()
    token = main_module.create_access_token(other_user.id)

    response = client.put(
        f"/links/{owned_link.short_code}",
        headers={"Authorization": f"Bearer {token}"},
        json={"original_url": "https://example.com/updated", "expires_at": "2030-01-01T00:00:00Z"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_update_link_rejects_past_expiry(client, auth_headers, owned_link: Link) -> None:
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    response = client.put(
        f"/links/{owned_link.short_code}",
        headers=auth_headers,
        json={"original_url": "https://example.com/updated", "expires_at": past_time},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_delete_link_requires_owner(client, db_session: Session, owned_link: Link) -> None:
    other_user = User(email="other@example.com", password_hash=hash_password("secret123"))
    db_session.add(other_user)
    db_session.commit()
    token = main_module.create_access_token(other_user.id)

    response = client.delete(f"/links/{owned_link.short_code}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_delete_link_removes_owned_resource(client, auth_headers, owned_link: Link, db_session: Session) -> None:
    response = client.delete(f"/links/{owned_link.short_code}", headers=auth_headers)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert db_session.query(Link).filter_by(short_code=owned_link.short_code).first() is None


def test_cleanup_inactive_links_requires_auth(client) -> None:
    response = client.post("/links/cleanup/inactive")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_cleanup_inactive_links_deletes_old_records(client, auth_headers, db_session: Session) -> None:
    old_link = Link(
        original_url="https://example.com/old",
        short_code="old-link",
        created_at=datetime.now(timezone.utc) - timedelta(days=31),
    )
    fresh_link = Link(original_url="https://example.com/fresh", short_code="fresh-link")
    db_session.add_all([old_link, fresh_link])
    db_session.commit()

    response = client.post("/links/cleanup/inactive", params={"inactive_days": 30}, headers=auth_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["deleted_count"] == 1
    assert db_session.query(Link).filter_by(short_code="old-link").first() is None
    assert db_session.query(Link).filter_by(short_code="fresh-link").first() is not None


def test_expired_history_returns_rows(client, expired_history_row) -> None:
    response = client.get("/links/expired/history")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 1
    assert response.json()[0]["short_code"] == expired_history_row.short_code


def test_cleanup_expired_links_moves_rows(client, db_session: Session) -> None:
    expired = Link(
        original_url="https://example.com/expired-cleanup",
        short_code="cleanup-expired",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=3),
    )
    db_session.add(expired)
    db_session.commit()

    response = client.post("/links/cleanup/expired")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert db_session.query(Link).filter_by(short_code="cleanup-expired").first() is None


def test_shorten_help_endpoint(client) -> None:
    response = client.get("/links/shorten")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"].startswith("Use POST /links/shorten")


@pytest.mark.asyncio
async def test_search_uses_cache_when_value_exists(mocker) -> None:
    fake_request = object()
    fake_db = object()
    cached_payload = {
        "found": True,
        "short_code": "cached",
        "short_url": "http://test/links/cached",
        "original_url": "https://example.com/cached",
    }

    cache_get = mocker.patch("app.main.cache_get", return_value=cached_payload)
    cache_set = mocker.patch("app.main.cache_set")

    response = await main_module.search_by_original_url(fake_request, "https://example.com/cached", fake_db)

    cache_get.assert_awaited_once()
    cache_set.assert_not_called()
    assert response.found is True
    assert response.short_code == "cached"


@pytest.mark.asyncio
async def test_get_stats_uses_cache_when_value_exists(mocker) -> None:
    fake_db = object()
    cached_payload = {
        "short_code": "cached-stats",
        "original_url": "https://example.com/stats",
        "created_at": "2030-01-01T00:00:00Z",
        "click_count": 7,
        "last_used_at": None,
        "expires_at": None,
    }

    cache_get = mocker.patch("app.main.cache_get", return_value=cached_payload)

    response = await main_module.get_stats("cached-stats", fake_db)

    cache_get.assert_awaited_once()
    assert response.click_count == 7


@pytest.mark.asyncio
async def test_redirect_uses_cached_url(mocker, db_session: Session) -> None:
    db_session.add(Link(original_url="https://example.com/cached-redirect", short_code="cached-redirect"))
    db_session.commit()

    cache_get = mocker.patch("app.main.cache_get", return_value={"original_url": "https://example.com/cached-redirect"})
    cache_delete = mocker.patch("app.main.cache_delete")

    response = await main_module.redirect_to_original("cached-redirect", db_session)

    cache_get.assert_awaited_once()
    cache_delete.assert_awaited_once()
    assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
