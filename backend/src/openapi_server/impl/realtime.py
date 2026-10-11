from __future__ import annotations

import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from openapi_server.impl.config import settings
from openapi_server.impl.engine.registry import registry

TICKET_TTL_SECONDS = 60


@dataclass(frozen=True)
class Ticket:
    player_id: str
    room_id: str
    expires_at: datetime


class TicketStore:
    def __init__(self) -> None:
        self._tickets: dict[str, Ticket] = {}

    def mint(self, player_id: str, room_id: str) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(24)
        expires = datetime.now(timezone.utc) + timedelta(seconds=TICKET_TTL_SECONDS)
        self._tickets[hashlib.sha256(token.encode()).hexdigest()] = Ticket(
            player_id, room_id, expires
        )
        return token, expires

    def consume(self, token: str) -> Ticket | None:
        if not token:
            return None
        ticket = self._tickets.pop(hashlib.sha256(token.encode()).hexdigest(), None)
        if ticket is None or datetime.now(timezone.utc) >= ticket.expires_at:
            return None
        return ticket

    def reset(self) -> None:
        self._tickets.clear()


ticket_store = TicketStore()


@dataclass
class Connection:
    websocket: WebSocket
    room: Any
    player_id: str
    queue: asyncio.Queue[dict[str, Any]]
    send_lock: asyncio.Lock
    closed: bool = False


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[tuple[str, str], Connection] = {}

    async def connect(
        self, websocket: WebSocket, room: Any, player_id: str
    ) -> Connection:
        key = (room.id, player_id)
        previous = self._connections.get(key)
        if previous is not None:
            await self.close(previous, 4410)
        await websocket.accept()
        connection = Connection(
            websocket,
            room,
            player_id,
            room.event_bus.subscribe(player_id),
            asyncio.Lock(),
        )
        self._connections[key] = connection
        return connection

    async def send(self, connection: Connection, event: dict[str, Any]) -> None:
        payload = dict(event)
        for field in ("playerId", "cardId", "newRoomId", "roomId"):
            value = payload.get(field)
            if isinstance(value, str):
                try:
                    payload[field] = str(UUID(value))
                except ValueError:
                    pass
        try:
            await asyncio.wait_for(connection.send_lock.acquire(), timeout=5)
            try:
                await asyncio.wait_for(
                    connection.websocket.send_json(payload), timeout=5
                )
            finally:
                connection.send_lock.release()
        except Exception:
            await self._stalled(connection)
            raise

    async def _stalled(self, connection: Connection) -> None:
        if not connection.closed:
            try:
                event = {
                    "type": "error",
                    "seq": connection.room.event_bus.next_seq(),
                    "at": connection.room.clock.now().isoformat(),
                    "code": "STALLED",
                    "willClose": True,
                }
                await asyncio.wait_for(
                    connection.websocket.send_json(event), timeout=0.2
                )
            except Exception:
                pass
            connection.room.disconnect(connection.player_id)
            await self.close(connection, 4504)

    async def close(self, connection: Connection, code: int = 1000) -> None:
        if connection.closed:
            return
        connection.closed = True
        connection.room.event_bus.unsubscribe(connection.queue)
        key = (connection.room.id, connection.player_id)
        if self._connections.get(key) is connection:
            del self._connections[key]
        try:
            await connection.websocket.close(code=code)
        except Exception:
            pass

    def get(self, room_id: str, player_id: str) -> Connection | None:
        return self._connections.get((room_id, player_id))

    async def close_room(self, room_id: str, code: int) -> None:
        for connection in tuple(self._connections.values()):
            if connection.room.id == room_id:
                await self.close(connection, code)


connections = ConnectionManager()


async def ws_endpoint(websocket: WebSocket, roomCode: str) -> None:
    token = websocket.query_params.get("ticket", "")
    ticket = ticket_store.consume(token)
    if ticket is None:
        await websocket.close(code=4401)
        return
    room = None
    try:
        room = registry.get_by_code(roomCode)
    except Exception:
        await websocket.close(code=4404)
        return
    player = room.players.get(ticket.player_id)
    if room.id != ticket.room_id or player is None or player.kicked:
        await websocket.close(code=4403)
        return
    if room.clock.now() >= room.ttl_expires_at:
        await websocket.close(code=4404)
        return
    was_disconnected = not player.connected
    connection = await connections.connect(websocket, room, player.id)
    hello = {
        "type": "hello",
        "seq": room.event_bus.seq,
        "at": room.clock.now().isoformat(),
        "roomCode": room.code,
        "playerId": player.id,
        "phase": room.phase.value,
        "resync": {"required": True, "snapshotUrl": "/v1/games/current/snapshot"},
    }
    try:
        await connections.send(connection, hello)
        if was_disconnected:
            room.reconnect(player.id)
        else:
            room.event_bus.publish_room(
                "player_presence", {"playerId": player.id, "state": "JOINED"}
            )
        await _serve_connection(connection)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        pass
    finally:
        if not connection.closed:
            room.disconnect(player.id)
            await connections.close(connection, 1000)


async def _serve_connection(connection: Connection) -> None:
    async def send_events() -> None:
        while not connection.closed:
            event = await connection.queue.get()
            await connections.send(connection, event)

    async def heartbeat() -> None:
        while not connection.closed:
            await asyncio.sleep(settings.heartbeat_seconds)
            if connection.closed:
                return
            connection.room.event_bus.publish_player(
                connection.player_id,
                "heartbeat",
                {"phase": connection.room.phase.value},
            )

    async def read_frames() -> None:
        try:
            while not connection.closed:
                await connection.websocket.receive()
                event = {
                    "type": "error",
                    "seq": connection.room.event_bus.next_seq(),
                    "at": connection.room.clock.now().isoformat(),
                    "code": "CLIENT_FRAME_REJECTED",
                    "willClose": True,
                }
                await connections.send(connection, event)
                connection.room.disconnect(connection.player_id)
                await connections.close(connection, 4400)
                return
        except WebSocketDisconnect:
            return

    tasks = [
        asyncio.create_task(send_events()),
        asyncio.create_task(heartbeat()),
        asyncio.create_task(read_frames()),
    ]
    _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
