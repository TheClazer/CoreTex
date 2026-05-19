"""Authentication endpoints — email/password + Google + GitHub OAuth.

All endpoints live under the /auth prefix. The OAuth flow is the standard
authorization-code grant:

    /auth/<provider>/start    →  302 redirect to provider with state cookie
    /auth/<provider>/callback ←  provider returns ?code=... &state=...
                              →  302 redirect to frontend with #token=<JWT>

The provider returns the user to the backend (so we can keep client
secrets server-side). The backend exchanges the code for an access token,
fetches the user profile, links/creates the local User row, mints a JWT,
and bounces the browser back to FRONTEND_URL with the token in the URL
fragment so the SPA can stash it in localStorage.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Annotated, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    current_user_required,
    hash_password,
    verify_password,
)
from app.config import settings
from app.db import db_enabled, get_db
from app.models import OAuthIdentity, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ─────────────────────────────────────────────────────────────


class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: Optional[str] = Field(default=None, max_length=100)


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "MeResponse"


class MeResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str]
    providers: list[str]
    created_at: datetime


class ProvidersResponse(BaseModel):
    email: bool = True
    google: bool
    github: bool


# ── Helpers ─────────────────────────────────────────────────────────────


def _serialise(user: User) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        providers=[oi.provider for oi in user.oauth_identities],
        created_at=user.created_at,
    )


def _check_db_enabled() -> None:
    if not db_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth is disabled — DATABASE_URL is not configured on the server.",
        )


def _check_jwt_configured() -> None:
    if not settings.JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth is misconfigured — JWT_SECRET is not set.",
        )


# ── Discovery — frontend asks which buttons to show ────────────────────


@router.get("/providers", response_model=ProvidersResponse)
def list_providers() -> ProvidersResponse:
    return ProvidersResponse(
        email=db_enabled() and bool(settings.JWT_SECRET),
        google=bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET),
        github=bool(settings.GITHUB_OAUTH_CLIENT_ID and settings.GITHUB_OAUTH_CLIENT_SECRET),
    )


# ── Email + password ────────────────────────────────────────────────────


@router.post("/signup", response_model=TokenResponse)
def signup(body: SignupBody, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    _check_db_enabled()
    _check_jwt_configured()

    email = body.email.lower().strip()
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists.",
        )

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=_serialise(user))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginBody, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    _check_db_enabled()
    _check_jwt_configured()

    email = body.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
        # Single message — don't leak whether the email exists.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=_serialise(user))


@router.get("/me", response_model=MeResponse)
def me(user: Annotated[User, Depends(current_user_required)]) -> MeResponse:
    return _serialise(user)


# ── OAuth ───────────────────────────────────────────────────────────────


_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

_GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USERINFO_URL = "https://api.github.com/user"
_GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


def _redirect_uri(provider: str) -> str:
    return f"{settings.OAUTH_REDIRECT_BASE.rstrip('/')}/auth/{provider}/callback"


def _frontend_redirect(token: Optional[str] = None, error: Optional[str] = None) -> RedirectResponse:
    """Bounce the browser back to the SPA with the auth result in the URL fragment.

    A URL fragment (``#token=...``) is never sent to the server, so it
    won't leak into logs or referer headers the way a query parameter
    might.
    """
    base = settings.FRONTEND_URL.rstrip("/") + "/auth/callback"
    if token:
        return RedirectResponse(f"{base}#token={token}", status_code=302)
    return RedirectResponse(f"{base}#error={error or 'oauth_failed'}", status_code=302)


@router.get("/google/start")
def google_start(request: Request) -> RedirectResponse:
    if not (settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET):
        raise HTTPException(status_code=503, detail="Google OAuth is not configured.")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": _redirect_uri("google"),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    resp = RedirectResponse(f"{_GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=302)
    # CSRF defence: persist the state in a short-lived signed cookie and
    # verify on callback.
    resp.set_cookie(
        "oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
    )
    return resp


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    db: Annotated[Session, Depends(get_db)] = ...,
) -> RedirectResponse:
    if not code or not state or state != request.cookies.get("oauth_state"):
        return _frontend_redirect(error="state_mismatch")

    try:
        with httpx.Client(timeout=10) as client:
            token_resp = client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                    "redirect_uri": _redirect_uri("google"),
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            userinfo = client.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo.raise_for_status()
            info = userinfo.json()

        provider_user_id = info["sub"]
        email = (info.get("email") or "").lower()
        display_name = info.get("name")
    except Exception as e:  # pragma: no cover - network errors
        logger.warning("Google OAuth callback failed: %s", e)
        return _frontend_redirect(error="provider_error")

    user = _link_or_create_user(db, "google", provider_user_id, email, display_name)
    token = create_access_token(user.id)
    return _frontend_redirect(token=token)


@router.get("/github/start")
def github_start() -> RedirectResponse:
    if not (settings.GITHUB_OAUTH_CLIENT_ID and settings.GITHUB_OAUTH_CLIENT_SECRET):
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured.")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
        "redirect_uri": _redirect_uri("github"),
        "scope": "read:user user:email",
        "state": state,
    }
    resp = RedirectResponse(f"{_GITHUB_AUTH_URL}?{urlencode(params)}", status_code=302)
    resp.set_cookie(
        "oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
    )
    return resp


@router.get("/github/callback")
def github_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    db: Annotated[Session, Depends(get_db)] = ...,
) -> RedirectResponse:
    if not code or not state or state != request.cookies.get("oauth_state"):
        return _frontend_redirect(error="state_mismatch")

    try:
        with httpx.Client(timeout=10) as client:
            token_resp = client.post(
                _GITHUB_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
                    "client_secret": settings.GITHUB_OAUTH_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": _redirect_uri("github"),
                },
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            userinfo = client.get(
                _GITHUB_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            userinfo.raise_for_status()
            info = userinfo.json()

            email = (info.get("email") or "").lower()
            if not email:
                # GitHub hides email by default; fetch the verified primary.
                emails_resp = client.get(
                    _GITHUB_EMAILS_URL,
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                )
                if emails_resp.status_code == 200:
                    for e in emails_resp.json():
                        if e.get("primary") and e.get("verified"):
                            email = (e.get("email") or "").lower()
                            break

        provider_user_id = str(info["id"])
        display_name = info.get("name") or info.get("login")
    except Exception as e:  # pragma: no cover - network errors
        logger.warning("GitHub OAuth callback failed: %s", e)
        return _frontend_redirect(error="provider_error")

    if not email:
        return _frontend_redirect(error="github_email_required")

    user = _link_or_create_user(db, "github", provider_user_id, email, display_name)
    token = create_access_token(user.id)
    return _frontend_redirect(token=token)


def _link_or_create_user(
    db: Session,
    provider: str,
    provider_user_id: str,
    email: str,
    display_name: Optional[str],
) -> User:
    """Find or create the local User for an OAuth identity.

    Three cases:
    1. Identity already linked → return that User.
    2. Identity new, but a User with this email exists → attach identity to that user.
    3. Otherwise → create a new User with no password set, attach identity.
    """
    identity = db.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == provider,
            OAuthIdentity.provider_user_id == provider_user_id,
        )
    )
    if identity is not None:
        identity.user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        return identity.user

    user = db.scalar(select(User).where(User.email == email)) if email else None
    if user is None:
        user = User(email=email, display_name=display_name, last_login_at=datetime.now(timezone.utc))
        db.add(user)
        db.flush()
    else:
        user.last_login_at = datetime.now(timezone.utc)

    db.add(
        OAuthIdentity(
            user_id=user.id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_email=email or None,
        )
    )
    db.commit()
    db.refresh(user)
    return user


TokenResponse.model_rebuild()
