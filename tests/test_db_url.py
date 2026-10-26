"""Database URL normalisation (driver pinning)."""

from app.db import _normalize_url


def test_bare_postgresql_pins_psycopg2_driver():
    assert _normalize_url("postgresql://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"


def test_heroku_style_postgres_scheme_is_normalised():
    assert _normalize_url("postgres://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"


def test_explicit_driver_and_sqlite_untouched():
    assert _normalize_url("postgresql+psycopg2://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
    assert _normalize_url("sqlite:///./local.db") == "sqlite:///./local.db"
