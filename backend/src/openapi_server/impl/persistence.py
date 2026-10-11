from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from sqlmodel import Session

from openapi_server.impl.db import write
from openapi_server.impl.tables import (
    AuthoredCard,
    GameEvent,
    GameEventType,
    GuessRecord,
    KickReason,
    Phase,
    PlayerRecord,
    ReviewBucket,
    RoomRecord,
    VoteRecord,
    hash_session_token,
)

_EVENT_TYPES = {
    "room_created": GameEventType.ROOM_CREATED,
    "player_joined": GameEventType.PLAYER_JOINED,
    "author_progress": GameEventType.AUTHOR_SUBMITTED,
    "lock_confirmed": GameEventType.GUESS_LOCKED,
    "card_capped": GameEventType.GUESS_TIMED_OUT,
    "slide_changed": GameEventType.REVEAL_SLIDE_SHOWN,
    "drip_revealed": GameEventType.DRIP_STAGE_SHOWN,
    "replay_started": GameEventType.REPLAY_STARTED,
    "room_closed": GameEventType.ROOM_CLOSED,
    "vote_progress": GameEventType.VOTE_CAST,
    "all_guessers_done": GameEventType.ALL_GUESSERS_DONE,
}


def _stable_id(*parts: str) -> str:
    # Stable across retries and supported by both SQLite and PostgreSQL.
    return ":".join(parts)


def _enum_or_none(enum_type, value):
    if value is None:
        return None
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        return None


def _event_payload(event: dict[str, Any], final: bool) -> dict[str, Any]:
    # Realtime event payloads are not the score/guess store. In particular,
    # scrub guess-looking fields until the room reaches FINAL.
    payload = {
        key: value for key, value in event.items() if key not in {"type", "seq", "at"}
    }
    if not final:
        for key in tuple(payload):
            if "guess" in key.casefold() or key.casefold() in {
                "value",
                "valuecents",
                "price",
                "pricecents",
            }:
                payload.pop(key)
    return payload


def _upsert(session: Session, model, key: str, values: dict[str, Any]) -> None:
    record = session.get(model, key)
    if record is None:
        record = model(id=key, **values)
        session.add(record)
    else:
        for name, value in values.items():
            setattr(record, name, value)


def _persist(session: Session, room) -> None:
    players = list(room.players.values())
    cards = list(room.cards.values())
    _upsert(
        session,
        RoomRecord,
        room.id,
        {
            "code": room.code,
            "state": room.phase,
            "creator_player_id": room.creator_player_id,
            "player_count": len(room.seats),
            "product_count": len(cards),
            "created_at": room.created_at,
            "ttl_expires_at": room.ttl_expires_at,
            "started_at": next(
                (
                    datetime.fromisoformat(event["at"])
                    for event in room.event_bus.history
                    if event.get("type") == "phase_changed"
                    and event.get("phase") == "AUTHOR"
                ),
                None,
            ),
            "ended_at": next(
                (
                    datetime.fromisoformat(event["at"])
                    for event in reversed(room.event_bus.history)
                    if event.get("type") == "phase_changed"
                    and event.get("phase") in ("FINAL", "CLOSED")
                ),
                None,
            ),
            "replay_of_room_id": room.replay_of_room_id,
        },
    )
    for player in players:
        _upsert(
            session,
            PlayerRecord,
            player.id,
            {
                "room_id": room.id,
                "display_name": player.name,
                "session_token_hash": player.token_hash
                or hash_session_token(player.id),
                "is_creator": player.id == room.creator_player_id,
                "joined_at": player.joined_at,
                "disconnected_at": player.disconnected_at,
                "kicked": player.kicked,
                "kick_reason": _enum_or_none(KickReason, player.kick_reason),
            },
        )
    for card in cards:
        _upsert(
            session,
            AuthoredCard,
            card.id,
            {
                "room_id": room.id,
                "product_id": card.product.id,
                "author_player_id": card.author_id,
                "title": card.title,
                "bullets": card.bullets or [],
                "star_rating": card.star_rating,
                "review_bucket": _enum_or_none(ReviewBucket, card.review_bucket),
                "submitted": card.status == "SUBMITTED",
                "submitted_at": card.submitted_at,
                "author_points": (
                    card.author_points if room.phase == Phase.FINAL else None
                ),
                "funniest_bonus": (
                    card.funniest_bonus if room.phase == Phase.FINAL else None
                ),
                "funniest_votes": (
                    card.funniest_votes if room.phase == Phase.FINAL else None
                ),
            },
        )
        for guess in card.guesses.values():
            if guess.status not in ("LOCKED", "AUTO_LOCKED", "SCORED_ZERO"):
                continue
            _upsert(
                session,
                GuessRecord,
                _stable_id(card.id, guess.player_id),
                {
                    "card_id": card.id,
                    "guesser_player_id": guess.player_id,
                    "value_cents": guess.value_cents,
                    "locked_at": guess.locked_at or room.clock.now(),
                    "card_seconds": guess.card_seconds,
                    "multiplier": guess.multiplier,
                    "z": (
                        (guess.z if guess.value_cents is not None else None)
                        if room.phase == Phase.FINAL
                        else None
                    ),
                    "accuracy": guess.accuracy if room.phase == Phase.FINAL else None,
                    "points": guess.points if room.phase == Phase.FINAL else None,
                    "timed_out": guess.timed_out,
                },
            )
    for voter_id, card_id in room.votes.items():
        _upsert(
            session,
            VoteRecord,
            _stable_id(room.id, voter_id),
            {
                "room_id": room.id,
                "voter_player_id": voter_id,
                "card_id": card_id,
            },
        )
    event_history = getattr(room.event_bus, "history", ())
    final_seq = next(
        (
            item.get("seq")
            for item in event_history
            if item.get("type") == "phase_changed" and item.get("phase") == "FINAL"
        ),
        None,
    )
    for event in event_history:
        event_type = _EVENT_TYPES.get(event.get("type"))
        if event.get("type") == "votekick_resolved":
            event_type = (
                GameEventType.PLAYER_KICKED if event.get("result") == "KICKED" else None
            )
        if event.get("type") == "player_presence" and event.get("state") == "LEFT":
            event_type = GameEventType.PLAYER_DISCONNECTED
        if event.get("type") == "phase_changed":
            phase = event.get("phase")
            event_type = (
                GameEventType.GAME_STARTED
                if phase == "AUTHOR"
                else GameEventType.GAME_FINAL if phase == "FINAL" else None
            )
        if event_type is None:
            continue
        seq = event.get("seq")
        if seq is None:
            continue
        event_id = (
            int.from_bytes(
                hashlib.sha256(f"{room.id}:{seq}".encode()).digest()[:8], "big"
            )
            & 0x7FFFFFFFFFFFFFFF
        )
        if session.get(GameEvent, event_id) is None:
            session.add(
                GameEvent(
                    id=event_id,
                    room_id=room.id,
                    event_type=event_type,
                    payload=_event_payload(
                        event,
                        final_seq is not None and event.get("seq", 0) >= final_seq,
                    ),
                    ts=(
                        datetime.fromisoformat(event["at"])
                        if event.get("at")
                        else room.clock.now()
                    ),
                )
            )


async def persist_room(room) -> None:
    """Write the current RoomEngine projection through the shared DB worker."""
    await write(lambda session: _persist(session, room))
