from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from openapi_server.impl.config import settings

T = TypeVar("T")

# Hosts that are not reached over the public internet; no TLS is implied.
_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1", "db", "host.docker.internal"}


def normalize_database_url(url: str) -> str:
    """Accept the connection string a host hands out, verbatim.

    Supabase prints `postgresql://` (and older dashboards `postgres://`); both
    need the psycopg driver name. A remote host without an explicit sslmode
    gets `sslmode=require`, because Supabase refuses plaintext connections and
    a silent fallback is worse than a clear failure.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix) :]
            break
    if not url.startswith("postgresql+psycopg://"):
        return url
    parts = urlsplit(url)
    if (parts.hostname or "").lower() in _LOCAL_HOSTS:
        return url
    query = dict(parse_qsl(parts.query))
    if "sslmode" not in query:
        query["sslmode"] = "require"
    return urlunsplit(parts._replace(query=urlencode(query)))


def _engine_options(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"pool_pre_ping": True}
    options: dict = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": settings.db_pool_size,
        # A serverless instance must not hold more than one connection: the
        # number of warm instances is not under our control.
        "max_overflow": 0 if settings.serverless else settings.db_pool_size,
    }
    if not settings.db_prepare_statements:
        # Supabase's transaction pooler (port 6543) cannot keep server-side
        # prepared statements across transactions.
        options["connect_args"] = {"prepare_threshold": None}
    return options


DATABASE_URL = normalize_database_url(settings.database_url)
engine = create_engine(DATABASE_URL, **_engine_options(DATABASE_URL))


@contextmanager
def session_scope():
    with Session(engine, expire_on_commit=False) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def _run(fn: Callable[[Session], T]) -> T:
    with session_scope() as session:
        return fn(session)


async def write(fn: Callable[[Session], T]) -> T:
    return await run_in_threadpool(_run, fn)


async def read(fn: Callable[[Session], T]) -> T:
    return await run_in_threadpool(_run, fn)


async def init_db() -> None:
    import openapi_server.impl.tables  # noqa: F401

    await run_in_threadpool(SQLModel.metadata.create_all, engine)
