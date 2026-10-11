from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, TypeVar

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from openapi_server.impl.config import settings

T = TypeVar("T")
engine = create_engine(settings.database_url, pool_pre_ping=True)


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
