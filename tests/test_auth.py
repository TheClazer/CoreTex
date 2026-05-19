"""Tests for the auth + history layer.

We spin up an in-memory SQLite database, point the app's config at it,
and exercise signup/login/me/history end to end. Email/password +
JWT path; OAuth callbacks need real provider responses so we don't
test those here (covered by the integration smoke test in DEPLOY.md).
"""

from __future__ import annotations

import os
import tempfile

import pytest

# Configure environment BEFORE importing the app — Pydantic Settings
# reads env vars at construction time.
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP.name}"
os.environ["JWT_SECRET"] = "test-secret-for-unit-tests-only-do-not-use-in-prod"

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import create_all  # noqa: E402
from app.main import app  # noqa: E402

# Re-read settings in case the module loaded before env vars were set.
settings.DATABASE_URL = f"sqlite:///{_TMP.name}"
settings.JWT_SECRET = "test-secret-for-unit-tests-only-do-not-use-in-prod"


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_db():
    create_all()
    yield


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_providers_endpoint():
    async with _client() as client:
        r = await client.get("/auth/providers")
        assert r.status_code == 200
        body = r.json()
        assert body["email"] is True
        assert isinstance(body["google"], bool)
        assert isinstance(body["github"], bool)


@pytest.mark.asyncio
async def test_signup_login_me_flow():
    async with _client() as client:
        r = await client.post(
            "/auth/signup",
            json={"email": "alice@example.com", "password": "supersecret123", "display_name": "Alice"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == "alice@example.com"
        token = body["access_token"]

        r = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == "alice@example.com"

        r = await client.post(
            "/auth/login",
            json={"email": "alice@example.com", "password": "supersecret123"},
        )
        assert r.status_code == 200
        assert r.json()["user"]["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_signup_rejects_duplicate():
    async with _client() as client:
        await client.post(
            "/auth/signup",
            json={"email": "dup@example.com", "password": "supersecret123"},
        )
        r = await client.post(
            "/auth/signup",
            json={"email": "dup@example.com", "password": "supersecret123"},
        )
        assert r.status_code == 409


@pytest.mark.asyncio
async def test_login_rejects_bad_password():
    async with _client() as client:
        await client.post(
            "/auth/signup",
            json={"email": "bob@example.com", "password": "supersecret123"},
        )
        r = await client.post(
            "/auth/login",
            json={"email": "bob@example.com", "password": "wrong-password"},
        )
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth():
    async with _client() as client:
        r = await client.get("/auth/me")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_history_requires_auth():
    async with _client() as client:
        r = await client.get("/history")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_history_empty_for_new_user():
    async with _client() as client:
        r = await client.post(
            "/auth/signup",
            json={"email": "carol@example.com", "password": "supersecret123"},
        )
        token = r.json()["access_token"]
        r = await client.get("/history", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}
