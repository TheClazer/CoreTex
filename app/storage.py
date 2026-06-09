"""Figure storage backends (v2 roadmap: S3 / R2 figure storage).

Conversions produce figure files that must survive between the worker (which
writes them) and the /download + /temp routes (which bundle them into the
Overleaf zip). v1 stored them in Redis with a short TTL — simple and free, but
large/numerous figures pressure Redis memory.

This module abstracts that behind a ``FigureStore`` with two implementations:

* ``RedisFigureStore`` (default) — byte-for-byte the v1 behaviour: a manifest
  key plus one raw-byte key per figure, all under the same TTL.
* ``S3FigureStore`` (opt-in, ``FIGURE_STORAGE=s3``) — offloads to S3 or any
  S3-compatible store (Cloudflare R2, MinIO) via boto3. Expiry is handled by a
  bucket lifecycle rule, so the heavy bytes never touch Redis.

``get_figure_store(redis_conn)`` picks the backend from settings and falls back
to Redis if S3 is requested but unavailable, so a misconfiguration degrades
gracefully instead of failing conversions.
"""

from __future__ import annotations

import logging
from typing import Dict, Protocol

from app.config import settings

logger = logging.getLogger(__name__)


class FigureStore(Protocol):
    def put_many(self, job_id: str, figures: Dict[str, bytes], ttl: int) -> None: ...

    def get_many(self, job_id: str) -> Dict[str, bytes]: ...


class RedisFigureStore:
    """Figures as individual raw-byte keys + a manifest (the v1 scheme)."""

    def __init__(self, redis_conn) -> None:
        self._redis = redis_conn

    def put_many(self, job_id: str, figures: Dict[str, bytes], ttl: int) -> None:
        if not figures:
            return
        manifest = "\n".join(figures.keys()).encode("utf-8")
        self._redis.setex(f"figures:{job_id}:manifest", ttl, manifest)
        for name, data in figures.items():
            self._redis.setex(f"figures:{job_id}:f:{name}", ttl, data)

    def get_many(self, job_id: str) -> Dict[str, bytes]:
        manifest_raw = self._redis.get(f"figures:{job_id}:manifest")
        if not manifest_raw:
            return {}
        figures: Dict[str, bytes] = {}
        for name in manifest_raw.decode("utf-8").splitlines():
            blob = self._redis.get(f"figures:{job_id}:f:{name}")
            if blob:
                figures[name] = blob
        return figures


class S3FigureStore:
    """Offload figures to S3 / R2 / MinIO under ``<prefix>/<job_id>/<name>``.

    Object expiry is delegated to a bucket lifecycle rule (configure the
    prefix to expire after a day); we do not set per-object TTLs here.
    """

    def __init__(self) -> None:
        if not settings.S3_BUCKET:
            raise RuntimeError("FIGURE_STORAGE=s3 requires S3_BUCKET to be set.")
        try:
            import boto3  # noqa: F401  (import-time availability check)
        except ImportError as exc:
            raise RuntimeError(
                "FIGURE_STORAGE=s3 requires boto3. Run: pip install boto3."
            ) from exc
        self._bucket = settings.S3_BUCKET
        self._prefix = settings.S3_PREFIX.strip("/")
        self._client = self._make_client()

    def _make_client(self):
        import boto3

        kwargs: dict = {"region_name": settings.S3_REGION or None}
        if settings.S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
            kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
        return boto3.client("s3", **kwargs)

    def _key(self, job_id: str, name: str) -> str:
        return f"{self._prefix}/{job_id}/{name}"

    def put_many(self, job_id: str, figures: Dict[str, bytes], ttl: int) -> None:
        # ttl is intentionally unused: lifecycle rules own expiry for S3/R2.
        for name, data in figures.items():
            self._client.put_object(
                Bucket=self._bucket, Key=self._key(job_id, name), Body=data
            )

    def get_many(self, job_id: str) -> Dict[str, bytes]:
        prefix = f"{self._prefix}/{job_id}/"
        figures: Dict[str, bytes] = {}
        resp = self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
        for obj in resp.get("Contents", []) or []:
            key = obj["Key"]
            name = key[len(prefix):]
            if not name:
                continue
            body = self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
            figures[name] = body
        return figures


def get_figure_store(redis_conn) -> FigureStore:
    """Return the configured figure store, falling back to Redis on error."""
    backend = (settings.FIGURE_STORAGE or "redis").strip().lower()
    if backend == "s3":
        try:
            return S3FigureStore()
        except Exception as e:  # misconfig or boto3 missing → don't break jobs
            logger.warning("S3 figure store unavailable (%s); using Redis.", e)
    return RedisFigureStore(redis_conn)
