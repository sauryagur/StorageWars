from __future__ import annotations

from fastapi.responses import JSONResponse, Response

from openapi_server.apis.guess_api_base import BaseGuessApi
from openapi_server.impl.engine.registry import registry
from openapi_server.impl.errors import ApiError, require_session
from openapi_server.impl.persistence import persist_room
from openapi_server.impl.ratelimit import check_rate_limit
from openapi_server.impl.scoring import clamp_and_round, format_money, multiplier
from openapi_server.models.lock_response import LockResponse
from openapi_server.models.guess_queue_progress import GuessQueueProgress
from openapi_server.impl.views import guess_card_view, guess_queue, value_echo


def _response(model, status_code: int) -> JSONResponse:
    return JSONResponse(
        model.model_dump(by_alias=True, exclude_unset=True, mode="json"),
        status_code=status_code,
    )


def _room_and_player():
    session = require_session()
    room = registry.get_by_code(session.room_code)
    if room.id != session.room_id:
        raise ApiError(403, "WRONG_ROOM")
    return session, room


def _guessable(room, player_id: str, card_id: str):
    if card_id not in room.queues.get(player_id, []):
        raise ApiError(404, "NOT_IN_QUEUE")
    card = room.cards[card_id]
    return card, card.guesses[player_id]


def _view(room, card, guess):
    view = guess_card_view(card, guess, room.clock.now())
    if guess.opened_at is None:
        return view
    elapsed = max(0.0, (room.clock.now() - guess.opened_at).total_seconds())
    values = view.model_dump(by_alias=True, exclude_unset=True, mode="python")
    values["multiplierNow"] = multiplier(elapsed)
    return type(view).model_validate(values)


def _card_key(card_id) -> str:
    return card_id.hex if hasattr(card_id, "hex") else str(card_id).replace("-", "")


class GuessApiImpl(BaseGuessApi):
    async def games_current_guess_queue_get(self) -> JSONResponse:
        session, room = _room_and_player()
        if room.phase.value != "GUESS":
            raise ApiError(409, "WRONG_PHASE", phase=room.phase.value)
        queue_ids = room.queue_for(session.player_id)
        cards = [room.cards[card_id] for card_id in queue_ids]
        my_guesses = [
            room.cards[card_id].guesses[session.player_id] for card_id in queue_ids
        ]
        done_status = {"LOCKED", "AUTO_LOCKED", "SCORED_ZERO", "SKIPPED"}
        next_card_id = next(
            (
                card_id
                for card_id in queue_ids
                if room.cards[card_id].guesses[session.player_id].status == "QUEUED"
            ),
            None,
        )
        active_card_id = room.active_cards.get(session.player_id)
        all_done = all(guess.status in done_status for guess in my_guesses)
        all_players_done = all(
            all(
                room.cards[card_id].guesses[player.id].status in done_status
                for card_id in room.queues.get(player.id, [])
            )
            for player in room.seats
        )
        progress = GuessQueueProgress(
            myLocked=sum(guess.status in done_status for guess in my_guesses),
            myTimedOut=sum(guess.timed_out for guess in my_guesses),
            myTotal=len(my_guesses),
            allPlayersDone=all_players_done,
        )
        return _response(
            guess_queue(
                cards,
                session.player_id,
                active_card_id=active_card_id,
                next_card_id=next_card_id,
                all_done=all_done,
                progress=progress,
            ),
            200,
        )

    async def games_current_guess_cards_card_id_open_post(self, cardId) -> JSONResponse:
        session, room = _room_and_player()
        check_rate_limit("open_session", session.session_token_hash)
        key = _card_key(cardId)
        guess = room.open(session.player_id, key)
        await persist_room(room)
        card = room.cards[key]
        return _response(_view(room, card, guess), 200)

    async def games_current_guess_cards_card_id_get(self, cardId) -> JSONResponse:
        session, room = _room_and_player()
        if room.phase.value != "GUESS":
            raise ApiError(409, "WRONG_PHASE", phase=room.phase.value)
        card, guess = _guessable(room, session.player_id, _card_key(cardId))
        if guess.opened_at is None:
            raise ApiError(409, "NOT_NEXT_CARD")
        return _response(_view(room, card, guess), 200)

    async def games_current_guess_cards_card_id_draft_put(
        self, cardId, value_input
    ) -> JSONResponse:
        session, room = _room_and_player()
        guess, was_clamped, was_rounded = room.draft(
            session.player_id, _card_key(cardId), value_input.value_cents
        )
        return _response(
            value_echo(
                guess.value_cents,
                format_money(guess.value_cents),
                was_clamped=was_clamped,
                was_rounded=was_rounded,
            ),
            200,
        )

    async def games_current_guess_cards_card_id_touch_post(self, cardId) -> Response:
        session, room = _room_and_player()
        check_rate_limit("misc_session", session.session_token_hash)
        room.touch(session.player_id, _card_key(cardId))
        await persist_room(room)
        return Response(status_code=204)

    async def games_current_guess_cards_card_id_lock_post(
        self, cardId, value_input
    ) -> JSONResponse:
        session, room = _room_and_player()
        check_rate_limit("submit_session", session.session_token_hash)
        card_id = _card_key(cardId)
        _, was_clamped, was_rounded = clamp_and_round(value_input.value_cents)
        guess = room.lock(session.player_id, card_id, value_input.value_cents)
        await persist_room(room)
        next_card_id = next(
            (
                queued_id
                for queued_id in room.queues.get(session.player_id, [])
                if room.cards[queued_id].guesses[session.player_id].status == "QUEUED"
            ),
            None,
        )
        response = LockResponse.model_validate(
            {
                "valueCents": guess.value_cents,
                "formattedValue": format_money(guess.value_cents),
                "wasClamped": was_clamped,
                "wasRounded": was_rounded,
                "cardId": card_id,
                "lockedAt": guess.locked_at,
                "cardSeconds": guess.card_seconds,
                "multiplier": guess.multiplier,
                "nextCardId": next_card_id,
            }
        )
        return _response(response, 200)
