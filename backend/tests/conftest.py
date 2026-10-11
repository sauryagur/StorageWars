from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlalchemy import create_engine

from openapi_server.impl import api as _api  # noqa: F401 - register route handlers
from openapi_server.main import app as application
from openapi_server.impl.clock import FakeClock, set_clock
from openapi_server.impl.engine.registry import registry
from openapi_server.impl.ratelimit import limiter
from openapi_server.impl.realtime import connections, ticket_store


@pytest.fixture
def clock():
    value = FakeClock()
    set_clock(value)
    registry.clock = value
    yield value
    set_clock(None)


@pytest.fixture
def client(monkeypatch, tmp_path, clock):
    from openapi_server.impl import db, ingest, media
    from openapi_server.impl.config import settings
    from openapi_server.impl.content import seed_reference_data
    import asyncio

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(db, "engine", engine)
    test_settings = replace(settings, media_root=str(tmp_path))
    monkeypatch.setattr(ingest, "settings", test_settings)
    monkeypatch.setattr(media, "settings", test_settings)
    SQLModel.metadata.create_all(engine)
    registry.reset()
    registry.clock = clock
    limiter.reset()
    ticket_store.reset()
    connections._connections.clear()
    asyncio.run(seed_reference_data())
    asyncio.run(ingest.seed_fixtures())
    with TestClient(application) as test_client:
        yield test_client
    registry.reset()
    limiter.reset()
    ticket_store.reset()
    connections._connections.clear()
    set_clock(None)


def create_room(client, name="Host"):
    response = client.post("/v1/rooms", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def join_player(client, room_code, name):
    response = client.post(f"/v1/rooms/{room_code}/join", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()


def auth(token):
    return {"X-Session-Token": token}
