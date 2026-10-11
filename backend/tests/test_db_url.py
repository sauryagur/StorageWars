from __future__ import annotations

import pytest

from openapi_server.impl.db import normalize_database_url


@pytest.mark.parametrize(
    "given, expected",
    [
        # Supabase hands out `postgresql://` (older dashboards `postgres://`).
        (
            "postgres://postgres.abc:pw@aws-0-eu-west-1.pooler.supabase.com:5432/postgres",
            "postgresql+psycopg://postgres.abc:pw@aws-0-eu-west-1.pooler.supabase.com:5432/postgres?sslmode=require",
        ),
        (
            "postgresql://postgres.abc:pw@aws-0-eu-west-1.pooler.supabase.com:6543/postgres",
            "postgresql+psycopg://postgres.abc:pw@aws-0-eu-west-1.pooler.supabase.com:6543/postgres?sslmode=require",
        ),
        # An explicit sslmode is never overwritten.
        (
            "postgresql://user:pw@db.example.com:5432/impulsebuy?sslmode=disable",
            "postgresql+psycopg://user:pw@db.example.com:5432/impulsebuy?sslmode=disable",
        ),
        # Local hosts keep working without TLS, query strings included.
        (
            "postgresql://impulsebuy:impulsebuy@db:5432/impulsebuy?application_name=api",
            "postgresql+psycopg://impulsebuy:impulsebuy@db:5432/impulsebuy?application_name=api",
        ),
        (
            "postgresql+psycopg://impulsebuy:impulsebuy@localhost:5432/impulsebuy",
            "postgresql+psycopg://impulsebuy:impulsebuy@localhost:5432/impulsebuy",
        ),
        # Already-driver-qualified URLs and other dialects pass through.
        (
            "sqlite:///./local.db",
            "sqlite:///./local.db",
        ),
    ],
)
def test_normalize_database_url(given: str, expected: str) -> None:
    assert normalize_database_url(given) == expected
