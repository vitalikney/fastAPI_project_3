from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import cache as cache_module
from app.auth import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app
from app.models import ExpiredLink, Link, User


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def isolate_app(db_session: Session) -> Generator[None, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    cache_module.redis_client = None
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def created_user(db_session: Session) -> User:
    user = User(email="owner@example.com", password_hash=hash_password("secret123"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(created_user: User) -> dict[str, str]:
    token = create_access_token(created_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def owned_link(db_session: Session, created_user: User) -> Link:
    link = Link(
        original_url="https://example.com/original",
        short_code="owned-link",
        custom_alias="owned-link",
        owner_id=created_user.id,
    )
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)
    return link


@pytest.fixture
def expired_link(db_session: Session) -> Link:
    from datetime import datetime, timedelta, timezone

    link = Link(
        original_url="https://example.com/expired",
        short_code="expired-link",
        custom_alias="expired-link",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)
    return link


@pytest.fixture
def expired_history_row(db_session: Session) -> ExpiredLink:
    from datetime import datetime, timezone

    row = ExpiredLink(
        original_url="https://example.com/archived",
        short_code="archived-link",
        created_at=datetime.now(timezone.utc),
        click_count=3,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row
