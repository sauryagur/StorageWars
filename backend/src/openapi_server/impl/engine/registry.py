from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any

from openapi_server.impl.clock import Clock, get_clock
from openapi_server.impl.config import settings
from openapi_server.impl.errors import ApiError
from openapi_server.impl.tables import hash_session_token

logger = logging.getLogger(__name__)

ROOM_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class RoomRegistry:
    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or get_clock()
        self.rooms: dict[str, Any] = {}
        self.tokens: dict[str, tuple[str, str]] = {}
        self._sweeper: asyncio.Task | None = None

    def create_room(self, name: str):
        from openapi_server.impl.engine.room import Player, RoomEngine

        while True:
            code = "".join(secrets.choice(ROOM_CHARS) for _ in range(4))
            if code not in self.rooms:
                break
        player_id = secrets.token_hex(16)
        player = Player(player_id, name, creator=True, joined_at=self.clock.now())
        room = RoomEngine(name, code=code, creator=player, clock=self.clock)
        self.rooms[code] = room
        token = self._mint(player, room)
        room.event_bus.publish_room("room_created", {"playerId": player.id})
        return room, player, token

    def get_by_code(self, code: str):
        room = self.rooms.get(code.upper())
        if room is None or self.clock.now() >= room.ttl_expires_at:
            raise ApiError(404, "ROOM_NOT_FOUND")
        return room

    def join(self, code: str, name: str):
        room = self.get_by_code(code)
        claim_deadline = getattr(room, "seat_claim_expires_at", None)
        if claim_deadline is not None:
            if self.clock.now() < claim_deadline:
                raise ApiError(409, "GAME_IN_PROGRESS")
            self.sweep()
            room = self.get_by_code(code)
        player = room.add_player(name)
        token = self._mint(player, room)
        room.event_bus.publish_room("player_joined", {"playerId": player.id})
        return room, player, token

    def rejoin(self, code: str, token: str):
        room = self.get_by_code(code)
        digest = hash_session_token(token)
        claim_player_id = getattr(room, "claim_token_hashes", {}).get(digest)
        claim_deadline = getattr(room, "seat_claim_expires_at", None)
        if claim_player_id is not None:
            if claim_deadline is None or self.clock.now() >= claim_deadline:
                self.sweep()
                raise ApiError(410, "REJOIN_EXPIRED")
            player = room.players[claim_player_id]
            room.claim_token_hashes.pop(digest, None)
            player.token_hash = digest
            self.tokens[digest] = (room.id, player.id)
            room.reconnect(player.id)
            return room, player, token
        identity = self.resolve(token)
        if identity is None:
            raise ApiError(410, "REJOIN_EXPIRED")
        old_room, player = identity
        if old_room.id != room.id:
            raise ApiError(403, "WRONG_ROOM")
        if player.kicked:
            raise ApiError(410, "REJOIN_EXPIRED")
        expiry = room._rejoin_expiry.get(player.id)
        if expiry and self.clock.now() >= expiry:
            self.expire_seat(player.id)
            raise ApiError(410, "REJOIN_EXPIRED")
        room.reconnect(player.id)
        return room, player, token

    def replay(self, old_room, caller_id: str):
        from datetime import timedelta
        from openapi_server.impl.engine.room import Player, RoomEngine

        if old_room.immutable:
            raise ApiError(
                409, "WRONG_PHASE", phase=old_room.phase.value, retry_in_phase="FINAL"
            )
        if old_room.phase.value != "FINAL":
            raise ApiError(
                409, "WRONG_PHASE", phase=old_room.phase.value, retry_in_phase="FINAL"
            )
        while True:
            code = "".join(secrets.choice(ROOM_CHARS) for _ in range(4))
            if code not in self.rooms:
                break
        new_players = []
        for old_player in old_room.seats:
            player = Player(
                secrets.token_hex(16),
                old_player.name,
                creator=old_player.id == old_room.creator_player_id,
                joined_at=self.clock.now(),
                connected=False,
            )
            new_players.append((old_player, player))
        creator = next(
            player
            for old, player in new_players
            if old.id == old_room.creator_player_id
        )
        room = RoomEngine(
            old_room.name,
            code=code,
            creator=creator,
            clock=self.clock,
            replay_of_room_id=old_room.id,
        )
        room.players = {player.id: player for _, player in new_players}
        room.creator_player_id = creator.id
        room.seat_claim_expires_at = self.clock.now() + timedelta(
            seconds=settings.seat_claim_seconds
        )
        room.claim_token_hashes = {
            old.token_hash: new.id for old, new in new_players if old.token_hash
        }
        self.rooms[code] = room
        room.start_timers()
        old_room.immutable = True
        old_room.event_bus.publish_room(
            "replay_started",
            {
                "newRoomCode": room.code,
                "newRoomId": room.id,
                "seatClaimExpiresAt": room.seat_claim_expires_at.isoformat(),
            },
        )
        return room

    def mint_session_token(self, room, player) -> str:
        return self._mint(player, room)

    def _mint(self, player, room) -> str:
        token = secrets.token_urlsafe(settings.session_token_bytes)
        digest = hash_session_token(token)
        player.token_hash = digest
        self.tokens[digest] = (room.id, player.id)
        return token

    def resolve(self, token: str):
        if not token:
            return None
        digest = hash_session_token(token)
        identity = self.tokens.get(digest)
        if identity is None:
            return None
        for room in self.rooms.values():
            if room.id == identity[0]:
                player = room.players.get(identity[1])
                if self.clock.now() >= room.ttl_expires_at:
                    return None
                return (
                    (room, player) if player is not None and not player.kicked else None
                )
        return None

    def resolve_hash(self, token_hash: str):
        identity = self.tokens.get(token_hash)
        if identity is None:
            return None
        for room in self.rooms.values():
            if room.id == identity[0]:
                player = room.players.get(identity[1])
                return (room, player) if player is not None else None
        return None

    def expire_seat(self, player_id: str) -> None:
        for room in self.rooms.values():
            player = room.players.get(player_id)
            if player is None:
                continue
            self.tokens.pop(player.token_hash, None)
            player.kicked = True
            player.token_hash = ""
            room._skip_player_queue(player_id)
            if room.phase.value == "GUESS":
                room._maybe_enter_reveal()
            room._rejoin_expiry.pop(player_id, None)
            if room.phase.value == "LOBBY" and room.creator_player_id == player_id:
                remaining = sorted(
                    (p for p in room.seats if p.id != player_id),
                    key=lambda p: p.joined_at,
                )
                room.creator_player_id = remaining[0].id if remaining else None
                if remaining:
                    for p in room.players.values():
                        p.creator = p.id == room.creator_player_id
            return

    def sweep(self) -> list[Any]:
        now = self.clock.now()
        expired = []
        for code, room in tuple(self.rooms.items()):
            for player_id, expiry in tuple(room._rejoin_expiry.items()):
                if now >= expiry:
                    self.expire_seat(player_id)
            claim_deadline = getattr(room, "seat_claim_expires_at", None)
            if claim_deadline is not None and now >= claim_deadline:
                for digest, player_id in tuple(room.claim_token_hashes.items()):
                    self.tokens.pop(digest, None)
                    room.players.pop(player_id, None)
                    room.claim_token_hashes.pop(digest, None)
                if room.creator_player_id not in room.players:
                    remaining = sorted(room.players.values(), key=lambda p: p.joined_at)
                    room.creator_player_id = remaining[0].id if remaining else None
                    for player in remaining:
                        player.creator = player.id == room.creator_player_id
                room.seat_claim_expires_at = None
            if now >= room.ttl_expires_at:
                room.phase = room.phase.__class__.CLOSED
                room.event_bus.publish_room("room_closed", {"reason": "TTL_EXPIRED"})
                expired.append(room)
                del self.rooms[code]
                for digest, (_, pid) in tuple(self.tokens.items()):
                    if pid in room.players:
                        self.tokens.pop(digest, None)
        return expired

    async def _sweep_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            expired = self.sweep()
            from openapi_server.impl.realtime import connections
            from openapi_server.impl.persistence import persist_room

            for room in expired:
                await persist_room(room)
                await connections.close_room(room.id, 1000)

    def start_sweeper(self) -> asyncio.Task:
        if self._sweeper is None or self._sweeper.done():
            self._sweeper = asyncio.create_task(self._sweep_loop())
        return self._sweeper

    async def tick_all(self) -> None:
        """Advance every live room once.

        Serverless runtimes have no long-lived timer tasks, so each request
        drives the clock instead of `RoomEngine.start_timers`. Failures are
        logged per room: one broken room must not fail the request.
        """
        for room in tuple(self.rooms.values()):
            try:
                await room.tick()
            except Exception:
                logger.exception("tick failed for room %s", room.code)

    def reset(self) -> None:
        if self._sweeper:
            self._sweeper.cancel()
            self._sweeper = None
        self.rooms.clear()
        self.tokens.clear()


registry = RoomRegistry()
