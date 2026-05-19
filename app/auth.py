"""Authentication primitives — password hashing, JWT, current-user dependency.

The same JWT format is used for tokens issued by `/auth/login`,
`/auth/signup`, and the OAuth callback handlers. The token's `sub` claim
holds the user's UUID; that's all the downstream endpoints need to scope
data access.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.db import db_enabled, get_session_factory

# `bcrypt_sha256` SHA-256-prefixes the password before feeding it to
# bcrypt, sidestepping bcrypt's 72-byte input limit (which newer bcrypt
# libraries error on instead of silently truncating).
_pwd = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")


# ── Password helpers ────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


# ── JWT helpers ─────────────────────────────────────────────────────────

def create_access_token(user_id: str) -> str:
    if not settings.JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not configured")
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRES_HOURS)
    payload = {"sub": user_id, "exp": expires, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    """Return the user_id from a valid token, or None if invalid/expired."""
    if not settings.JWT_SECRET:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        sub = payload.get("sub")
        return sub if isinstance(sub, str) else None
    except JWTError:
        return None


# ── FastAPI dependencies ────────────────────────────────────────────────

def _extract_bearer(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def current_user_optional(request: Request):
    """Resolve the bearer token to a User; return None if no/invalid token.

    Opens its own short-lived DB session so endpoints that work both
    anonymously and authenticated (e.g. POST /convert) don't need to
    declare a DB dependency themselves.

    Imports User lazily to keep this module import-light when the DB
    layer isn't even configured.
    """
    if not db_enabled():
        return None
    token = _extract_bearer(request)
    if not token:
        return None
    user_id = decode_access_token(token)
    if not user_id:
        return None
    factory = get_session_factory()
    if factory is None:
        return None
    from sqlalchemy.orm import selectinload  # local imports — keep module DB-free at top
    from app.models import User
    with factory() as session:
        # Eager-load oauth_identities so downstream serialisation can access
        # it after the session closes (no DetachedInstanceError).
        user = session.get(User, user_id, options=[selectinload(User.oauth_identities)])
        if user is not None:
            session.expunge(user)
        return user


def current_user_required(user=Depends(current_user_optional)):
    """Reject the request if no authenticated user is attached."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
