from __future__ import annotations

from fastapi.responses import JSONResponse

from openapi_server.apis.session_api_base import BaseSessionApi
from openapi_server.impl.engine.registry import registry
from openapi_server.impl.errors import ApiError, require_session
from openapi_server.impl.ratelimit import check_rate_limit
from openapi_server.impl.realtime import ticket_store
from openapi_server.models.game_snapshot import GameSnapshot
from openapi_server.models.ws_ticket import WsTicket


def _response(model, status_code: int) -> JSONResponse:
    return JSONResponse(
        model.model_dump(by_alias=True, exclude_unset=True, mode="json"),
        status_code=status_code,
    )


class SessionApiImpl(BaseSessionApi):
    async def ws_ticket_post(self) -> JSONResponse:
        session = require_session()
        check_rate_limit("ticket_session", session.session_token_hash)
        ticket, expires_at = ticket_store.mint(session.player_id, session.room_id)
        return _response(
            WsTicket.model_validate({"ticket": ticket, "expiresAt": expires_at}), 201
        )

    async def games_current_snapshot_get(self) -> JSONResponse:
        session = require_session()
        room = registry.get_by_code(session.room_code)
        if room.id != session.room_id:
            raise ApiError(403, "WRONG_ROOM")
        player = room.players.get(session.player_id)
        if player is None or player.kicked:
            raise ApiError(403, "WRONG_ROOM")

        phase = room.phase.value
        snapshot: dict[str, object] = {
            "roomId": room.id,
            "roomCode": room.code,
            "playerId": player.id,
            "phase": phase,
            "seq": room.event_bus.seq,
        }
        if phase == "LOBBY":
            snapshot["lobby"] = {
                "players": [
                    {
                        "playerId": seat.id,
                        "name": seat.name,
                        "isCreator": seat.id == room.creator_player_id,
                        "connected": seat.connected,
                    }
                    for seat in room.seats
                ]
            }
        elif phase == "AUTHOR":
            card = next(
                (card for card in room.cards.values() if card.author_id == player.id),
                None,
            )
            snapshot["author"] = {
                "submitted": bool(card and card.status == "SUBMITTED"),
                "progress": {
                    "submitted": sum(
                        card.status == "SUBMITTED" for card in room.cards.values()
                    ),
                    "skipped": sum(
                        card.status == "SKIPPED" for card in room.cards.values()
                    ),
                    "total": len(room.cards),
                },
            }
        elif phase == "GUESS":
            queue_ids = room.queue_for(player.id)
            active_id = room.active_cards.get(player.id)
            my_guesses = [
                card.guesses[player.id]
                for card in room.cards.values()
                if player.id in card.guesses
            ]
            snapshot["guess"] = {
                "queue": {
                    "cards": [
                        {
                            "cardId": card_id,
                            "status": (
                                {
                                    "QUEUED": "UNOPENED",
                                    "AUTO_LOCKED": "TIMED_OUT",
                                    "SCORED_ZERO": "TIMED_OUT",
                                }.get(
                                    room.cards[card_id].guesses[player.id].status,
                                    room.cards[card_id].guesses[player.id].status,
                                )
                                if player.id in room.cards[card_id].guesses
                                else "UNOPENED"
                            ),
                        }
                        for card_id in queue_ids
                        if card_id in room.cards
                    ],
                    "myPosition": {
                        "activeCardId": active_id,
                        "nextCardId": next(
                            (
                                card_id
                                for card_id in queue_ids
                                if player.id in room.cards[card_id].guesses
                                and room.cards[card_id].guesses[player.id].status
                                == "QUEUED"
                            ),
                            None,
                        ),
                        "allDone": not queue_ids and active_id is None,
                    },
                    "progress": {
                        "myLocked": sum(
                            guess.status == "LOCKED" for guess in my_guesses
                        ),
                        "myTimedOut": sum(guess.timed_out for guess in my_guesses),
                        "myTotal": len(queue_ids),
                        "allPlayersDone": all(
                            not room.queues.get(seat.id)
                            and seat.id not in room.active_cards
                            for seat in room.seats
                        ),
                    },
                }
            }
        elif phase == "REVEAL":
            snapshot["reveal"] = {
                "slideIndex": room.reveal_index,
                "slideCount": len(room.reveal_order),
            }
        elif phase == "VOTE":
            snapshot["vote"] = {
                "myVoteCast": player.id in room.votes,
                "deadlineAt": room.vote_deadline,
            }
        elif phase == "FINAL":
            snapshot["final"] = {}

        return _response(GameSnapshot.model_validate(snapshot), 200)
