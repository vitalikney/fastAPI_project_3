import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, get_optional_user, hash_password, verify_password
from app.cache import cache_delete, cache_get, cache_set, close_redis, init_redis
from app.config import get_settings
from app.database import Base, engine, get_db
from app.models import ExpiredLink, Link, User
from app.schemas import (
    CleanupResponse,
    ExpiredLinkItem,
    LinkCreate,
    LinkResponse,
    LinkStatsResponse,
    LinkUpdate,
    SearchResponse,
    TokenResponse,
    UserLogin,
    UserRegister,
)


settings = get_settings()
app = FastAPI(title=settings.app_name)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_datetime(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(second=0, microsecond=0)


def build_short_url(short_code: str, request: Request | None = None) -> str:
    if settings.base_url:
        base = settings.base_url.rstrip("/")
    elif request is not None:
        base = str(request.base_url).rstrip("/")
    else:
        base = "http://localhost:8000"
    return f"{base}/links/{short_code}"


def link_to_response(link: Link, request: Request | None = None) -> LinkResponse:
    return LinkResponse(
        short_code=link.short_code,
        short_url=build_short_url(link.short_code, request),
        original_url=link.original_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
        owner_id=link.owner_id,
    )


def generate_short_code() -> str:
    return secrets.token_urlsafe(5).replace("-", "").replace("_", "")[:8]


def save_expired_link(db: Session, link: Link) -> None:
    db.add(
        ExpiredLink(
            original_url=link.original_url,
            short_code=link.short_code,
            created_at=link.created_at,
            last_used_at=link.last_used_at,
            click_count=link.click_count,
        )
    )


def delete_if_expired(db: Session, link: Link) -> bool:
    if link.expires_at and link.expires_at <= now_utc():
        save_expired_link(db, link)
        db.delete(link)
        db.commit()
        return True
    return False


@app.on_event("startup")
async def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    await init_redis()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await close_redis()


@app.get("/health")
def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/")
def root() -> dict:
    return {
        "message": "FastAPI URL Shortener is running",
        "docs": "/docs",
        "health": "/health",
    }


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)) -> dict:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email}


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return TokenResponse(access_token=create_access_token(user.id))


@app.post("/links/shorten", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)
async def create_short_link(
    request: Request,
    payload: LinkCreate,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> LinkResponse:
    expires_at = normalize_datetime(payload.expires_at)
    if expires_at and expires_at <= now_utc():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="expires_at must be in the future")

    short_code = payload.custom_alias or generate_short_code()
    if payload.custom_alias:
        exists_alias = db.scalar(select(Link).where(Link.short_code == payload.custom_alias))
        if exists_alias:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="custom_alias already exists")
    else:
        while db.scalar(select(Link).where(Link.short_code == short_code)) is not None:
            short_code = generate_short_code()

    link = Link(
        original_url=str(payload.original_url),
        short_code=short_code,
        custom_alias=payload.custom_alias,
        expires_at=expires_at,
        owner_id=user.id if user else None,
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    await cache_delete(f"search:{link.original_url}")
    return link_to_response(link, request)


@app.get("/links/shorten")
def shorten_help() -> dict:
    return {
        "message": "Use POST /links/shorten to create a short link",
        "docs": "/docs",
        "example_body": {
            "original_url": "https://example.com/long/path",
            "custom_alias": "my-link",
            "expires_at": "2030-12-31T23:59:00Z",
        },
    }


@app.get("/links/search", response_model=SearchResponse)
async def search_by_original_url(
    request: Request,
    original_url: str = Query(...),
    db: Session = Depends(get_db),
) -> SearchResponse:
    cache_key = f"search:{original_url}"
    cached = await cache_get(cache_key)
    if cached:
        return SearchResponse(**cached)

    link = db.scalar(select(Link).where(Link.original_url == original_url))
    if link is None:
        return SearchResponse(found=False)
    if delete_if_expired(db, link):
        await cache_delete(f"redirect:{link.short_code}", f"stats:{link.short_code}")
        return SearchResponse(found=False)

    result = SearchResponse(
        found=True,
        short_code=link.short_code,
        short_url=build_short_url(link.short_code, request),
        original_url=link.original_url,
    )
    await cache_set(cache_key, result.model_dump(mode="json"))
    return result


@app.post("/links/cleanup/inactive", response_model=CleanupResponse)
async def cleanup_inactive_links(
    inactive_days: int | None = Query(default=None, ge=1, le=3650),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CleanupResponse:
    del user
    n_days = inactive_days or settings.default_inactive_days
    threshold = now_utc() - timedelta(days=n_days)

    candidates = db.scalars(
        select(Link).where(
            or_(
                and_(Link.last_used_at.is_(None), Link.created_at < threshold),
                and_(Link.last_used_at.is_not(None), Link.last_used_at < threshold),
            )
        )
    ).all()

    deleted_count = 0
    for link in candidates:
        await cache_delete(f"redirect:{link.short_code}", f"stats:{link.short_code}", f"search:{link.original_url}")
        db.delete(link)
        deleted_count += 1
    db.commit()

    return CleanupResponse(deleted_count=deleted_count, inactive_days=n_days)


@app.get("/links/expired/history", response_model=list[ExpiredLinkItem])
def expired_history(limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)) -> list[ExpiredLinkItem]:
    rows = db.scalars(select(ExpiredLink).order_by(ExpiredLink.expired_at.desc()).limit(limit)).all()
    return [ExpiredLinkItem.model_validate(row) for row in rows]


@app.post("/links/cleanup/expired", status_code=status.HTTP_204_NO_CONTENT)
async def cleanup_expired_links(db: Session = Depends(get_db)) -> Response:
    expired = db.scalars(select(Link).where(Link.expires_at.is_not(None), Link.expires_at <= now_utc())).all()
    for link in expired:
        save_expired_link(db, link)
        await cache_delete(f"redirect:{link.short_code}", f"stats:{link.short_code}", f"search:{link.original_url}")
        db.delete(link)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/links/{short_code}")
async def redirect_to_original(short_code: str, db: Session = Depends(get_db)) -> Response:
    cache_key = f"redirect:{short_code}"
    cached = await cache_get(cache_key)
    if cached:
        link = db.scalar(select(Link).where(Link.short_code == short_code))
        if link:
            if delete_if_expired(db, link):
                await cache_delete(cache_key, f"stats:{short_code}", f"search:{link.original_url}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short link expired")
            link.click_count += 1
            link.last_used_at = now_utc()
            db.commit()
            await cache_delete(f"stats:{short_code}")
            return RedirectResponse(url=cached["original_url"], status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    link = db.scalar(select(Link).where(Link.short_code == short_code))
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short link not found")

    if delete_if_expired(db, link):
        await cache_delete(cache_key, f"stats:{short_code}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short link expired")

    link.click_count += 1
    link.last_used_at = now_utc()
    db.commit()

    await cache_set(cache_key, {"original_url": link.original_url})
    await cache_delete(f"stats:{short_code}")
    return RedirectResponse(url=link.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.put("/links/{short_code}", response_model=LinkResponse)
async def update_link(
    short_code: str,
    request: Request,
    payload: LinkUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LinkResponse:
    link = db.scalar(select(Link).where(Link.short_code == short_code))
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short link not found")
    if link.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can update link")
    if delete_if_expired(db, link):
        await cache_delete(f"redirect:{short_code}", f"stats:{short_code}", f"search:{link.original_url}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short link expired")

    old_original_url = link.original_url
    link.original_url = str(payload.original_url)
    expires_at = normalize_datetime(payload.expires_at)
    if expires_at and expires_at <= now_utc():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="expires_at must be in the future")
    link.expires_at = expires_at

    db.commit()
    db.refresh(link)
    await cache_delete(f"redirect:{short_code}", f"stats:{short_code}", f"search:{old_original_url}", f"search:{link.original_url}")
    return link_to_response(link, request)


@app.delete("/links/{short_code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    short_code: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    link = db.scalar(select(Link).where(Link.short_code == short_code))
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short link not found")
    if link.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can delete link")

    original_url = link.original_url
    db.delete(link)
    db.commit()
    await cache_delete(f"redirect:{short_code}", f"stats:{short_code}", f"search:{original_url}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/links/{short_code}/stats", response_model=LinkStatsResponse)
async def get_stats(short_code: str, db: Session = Depends(get_db)) -> LinkStatsResponse:
    cache_key = f"stats:{short_code}"
    cached = await cache_get(cache_key)
    if cached:
        return LinkStatsResponse(**cached)

    link = db.scalar(select(Link).where(Link.short_code == short_code))
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short link not found")
    if delete_if_expired(db, link):
        await cache_delete(cache_key, f"redirect:{short_code}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short link expired")

    data = LinkStatsResponse(
        short_code=link.short_code,
        original_url=link.original_url,
        created_at=link.created_at,
        click_count=link.click_count,
        last_used_at=link.last_used_at,
        expires_at=link.expires_at,
    )
    await cache_set(cache_key, data.model_dump(mode="json"))
    return data
