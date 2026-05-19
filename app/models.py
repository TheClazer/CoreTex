"""ORM models for user accounts and conversion history.

Schema:
    users           — account record. password_hash is NULL for OAuth-only users.
    oauth_identities — links one user to one (provider, provider_user_id) pair.
                       Lets a user attach multiple sign-in methods (e.g. email
                       account + Google + GitHub) without duplicate rows.
    conversions     — one row per successful conversion. Body and figures are
                       stored alongside so the user can re-download from history
                       without re-running the pipeline.
    figures         — child table; one row per /figures/<name> entry.

The (user_id, docx_sha256, template) tuple has a unique index so the dedup
logic in /convert can short-circuit identical uploads.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Index,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # NULL when the user signed up purely via OAuth (no password set).
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    oauth_identities: Mapped[list["OAuthIdentity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    conversions: Mapped[list["Conversion"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_subject"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # 'google' | 'github'
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="oauth_identities")


class Conversion(Base):
    __tablename__ = "conversions"
    __table_args__ = (
        # Hash-based dedup: at most one stored conversion per
        # (user, docx hash, template) tuple.
        UniqueConstraint("user_id", "docx_sha256", "template", name="uq_conversion_dedup"),
        Index("ix_conversions_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    docx_sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    template: Mapped[str] = mapped_column(String(32), nullable=False)
    latex_source: Mapped[str] = mapped_column(Text, nullable=False)
    has_images: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    warnings: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    citation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compile_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    compile_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    compile_error_line: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )

    user: Mapped["User"] = relationship(back_populates="conversions")
    figures: Mapped[list["Figure"]] = relationship(
        back_populates="conversion", cascade="all, delete-orphan"
    )


class Figure(Base):
    __tablename__ = "figures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversion_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    conversion: Mapped["Conversion"] = relationship(back_populates="figures")
