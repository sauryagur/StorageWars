from datetime import timedelta
import hashlib
from dataclasses import replace

import pytest
from starlette.websockets import WebSocketDisconnect

from conftest import auth, create_room, join_player
from openapi_server.impl.realtime import ticket_store


def _ticket(client, token):
    response = client.post("/v1/ws/ticket", headers=auth(token))
    assert response.status_code == 201, response.text
    return response.json()["ticket"]


def test_websocket_hello_frame_rejection_invalid_and_expired_ticket(client, clock):
    host = create_room(client)
    first_ticket = _ticket(client, host["sessionToken"])
    with client.websocket_connect(
        f"/v1/ws/{host['roomCode']}?ticket={first_ticket}"
    ) as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        assert hello["resync"]["required"] is True
        assert hello["seq"] >= 0
        joined = websocket.receive_json()
        assert joined["type"] == "player_presence"
        assert joined["state"] == "JOINED"
        websocket.send_text("client application frame")
        rejected = websocket.receive_json()
        assert rejected["type"] == "error"
        assert rejected["code"] == "CLIENT_FRAME_REJECTED"
        assert rejected["willClose"] is True
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_text()
        assert closed.value.code == 4400
    with pytest.raises(WebSocketDisconnect) as invalid:
        with client.websocket_connect(f"/v1/ws/{host['roomCode']}?ticket=missing"):
            pass
    assert invalid.value.code == 4401
    expired = _ticket(client, host["sessionToken"])
    key = hashlib.sha256(expired.encode()).hexdigest()
    ticket_store._tickets[key] = replace(
        ticket_store._tickets[key], expires_at=clock.now() - timedelta(seconds=1)
    )
    with pytest.raises(WebSocketDisconnect) as expired_close:
        with client.websocket_connect(f"/v1/ws/{host['roomCode']}?ticket={expired}"):
            pass
    assert expired_close.value.code == 4401


def test_websocket_ticket_wrong_room_and_duplicate_session_close(client):
    room_one = create_room(client, "Host One")
    room_two = create_room(client, "Host Two")
    wrong_room_ticket = _ticket(client, room_one["sessionToken"])
    with pytest.raises(WebSocketDisconnect) as wrong_room:
        with client.websocket_connect(
            f"/v1/ws/{room_two['roomCode']}?ticket={wrong_room_ticket}"
        ):
            pass
    assert wrong_room.value.code == 4403
    ticket_a = _ticket(client, room_one["sessionToken"])
    first = client.websocket_connect(f"/v1/ws/{room_one['roomCode']}?ticket={ticket_a}")
    first.__enter__()
    assert first.receive_json()["type"] == "hello"
    assert first.receive_json()["type"] == "player_presence"
    ticket_b = _ticket(client, room_one["sessionToken"])
    with client.websocket_connect(
        f"/v1/ws/{room_one['roomCode']}?ticket={ticket_b}"
    ) as second:
        assert second.receive_json()["type"] == "hello"
        with pytest.raises(WebSocketDisconnect) as old_closed:
            first.receive_text()
        assert old_closed.value.code == 4410
    first.__exit__(None, None, None)


def test_websocket_sequence_orders_phase_player_and_heartbeat_events(
    client, monkeypatch
):
    from openapi_server.impl import realtime
    from openapi_server.impl.config import settings
    from openapi_server.impl.engine.registry import registry

    monkeypatch.setattr(realtime, "settings", replace(settings, heartbeat_seconds=0.01))
    host = create_room(client)
    for index in range(2, 5):
        join_player(client, host["roomCode"], f"Player {index}")
    ticket = _ticket(client, host["sessionToken"])
    with client.websocket_connect(
        f"/v1/ws/{host['roomCode']}?ticket={ticket}"
    ) as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello" and hello["resync"]["required"] is True
        joined = websocket.receive_json()
        assert joined["type"] == "player_presence"
        started = client.post(
            f"/v1/rooms/{host['roomCode']}/start", headers=auth(host["sessionToken"])
        )
        assert started.status_code == 202, started.text
        room = registry.get_by_code(host["roomCode"])
        room.event_bus.publish_player(
            __import__("uuid").UUID(host["playerId"]).hex,
            "drip_revealed",
            {"stage": "BULLETS"},
        )
        frames = []
        received = set()
        for _ in range(8):
            frame = websocket.receive_json()
            frames.append(frame)
            received.add(frame["type"])
            if {"phase_changed", "drip_revealed", "heartbeat"}.issubset(received):
                break
        assert {"phase_changed", "drip_revealed", "heartbeat"}.issubset(received)
        assert [frame["seq"] for frame in frames] == sorted(
            frame["seq"] for frame in frames
        )
