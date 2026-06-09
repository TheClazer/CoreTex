"""Tests for the figure storage abstraction (Redis default backend)."""

from __future__ import annotations

from app.config import settings
from app.storage import RedisFigureStore, get_figure_store


class FakeRedis:
    """Minimal in-memory stand-in for the Redis calls the store makes."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def setex(self, key, ttl, value):
        self.store[key] = value if isinstance(value, bytes) else value.encode()

    def get(self, key):
        return self.store.get(key)


def test_redis_store_round_trips_figures():
    r = FakeRedis()
    store = RedisFigureStore(r)
    figures = {"figure_001.png": b"\x89PNG-A", "figure_002.jpg": b"JPEGB"}

    store.put_many("job1", figures, ttl=300)
    # Manifest + one key per figure were written.
    assert r.store["figures:job1:manifest"] == b"figure_001.png\nfigure_002.jpg"
    assert r.store["figures:job1:f:figure_001.png"] == b"\x89PNG-A"

    got = store.get_many("job1")
    assert got == figures


def test_redis_store_missing_manifest_returns_empty():
    store = RedisFigureStore(FakeRedis())
    assert store.get_many("nope") == {}


def test_put_empty_is_noop():
    r = FakeRedis()
    RedisFigureStore(r).put_many("job", {}, ttl=300)
    assert r.store == {}


def test_get_figure_store_defaults_to_redis():
    store = get_figure_store(FakeRedis())
    assert isinstance(store, RedisFigureStore)


def test_get_figure_store_s3_misconfigured_falls_back_to_redis(monkeypatch):
    # FIGURE_STORAGE=s3 but no bucket configured -> graceful Redis fallback.
    monkeypatch.setattr(settings, "FIGURE_STORAGE", "s3")
    monkeypatch.setattr(settings, "S3_BUCKET", "")
    store = get_figure_store(FakeRedis())
    assert isinstance(store, RedisFigureStore)
