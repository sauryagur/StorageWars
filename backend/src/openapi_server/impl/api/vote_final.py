from __future__ import annotations

import asyncio
from datetime import date, datetime
from fastapi.responses import JSONResponse, Response

from openapi_server.apis.reveal_api_base import BaseRevealApi
from openapi_server.apis.vote_final_api_base import BaseVoteFinalApi
from openapi_server.impl.engine.registry import registry
from openapi_server.impl.products import sign_image_url
from openapi_server.impl.errors import ApiError, require_session
from openapi_server.impl.persistence import persist_room
from openapi_server.models.author_card_submission import AuthorCardSubmission
from openapi_server.models.final_scoreboard import FinalScoreboard
from openapi_server.models.final_scoreboard_rankings_inner import (
    FinalScoreboardRankingsInner,
)
from openapi_server.models.final_scoreboard_rankings_inner_breakdown import (
    FinalScoreboardRankingsInnerBreakdown,
)
from openapi_server.models.final_scoreboard_rankings_inner_per_card_inner import (
    FinalScoreboardRankingsInnerPerCardInner,
)
from openapi_server.models.games_current_vote_post_request import (
    GamesCurrentVotePostRequest,
)
from openapi_server.models.reveal_slide import RevealSlide
from openapi_server.models.reveal_slide_card import RevealSlideCard
from openapi_server.models.reveal_slide_card_guesses_inner import (
    RevealSlideCardGuessesInner,
)
from openapi_server.models.reveal_slide_card_original import RevealSlideCardOriginal
from openapi_server.models.vote_options import VoteOptions
from openapi_server.models.vote_options_options_inner import VoteOptionsOptionsInner
from openapi_server.models.replay_response import ReplayResponse


def _response(model, status_code: int) -> JSONResponse:
    return JSONResponse(
        model.model_dump(by_alias=True, exclude_unset=True, mode="json"),
        status_code=status_code,
    )


def _room():
    session = require_session()
    room = registry.get_by_code(session.room_code)
    if room is None:
        raise ApiError(404, "ROOM_NOT_FOUND")
    return room, session


def _date(value):
    return (
        value.date()
        if isinstance(value, datetime)
        else value if isinstance(value, date) else date.today()
    )


class RevealApiImpl(BaseRevealApi):
    async def games_current_reveal_get(self) -> JSONResponse:
        room, session = _room()
        if room.phase.value != "REVEAL":
            raise ApiError(
                409, "WRONG_PHASE", phase=room.phase.value, retry_in_phase="REVEAL"
            )
        if not room.reveal_order:
            raise ApiError(
                409, "WRONG_PHASE", phase=room.phase.value, retry_in_phase="REVEAL"
            )
        index = min(room.reveal_index, len(room.reveal_order) - 1)
        card = room.cards[room.reveal_order[index]]
        product = card.product
        author = room.players[card.author_id]
        authored = AuthorCardSubmission.model_validate(
            {
                "title": card.title,
                "bullets": card.bullets,
                "starRating": card.star_rating,
                "reviewBucket": card.review_bucket,
                "category": card.category,
            }
        )
        original = RevealSlideCardOriginal.model_validate(
            {
                "imageUrl": sign_image_url(product, room_id=room.id),
                "title": product.original_title,
                "description": product.original_description,
                "priceCents": product.price_cents,
                "snapshotDate": _date(product.snapshot_date),
                "category": product.category.slug if product.category else "",
            }
        )
        guesses = [
            RevealSlideCardGuessesInner.model_validate(
                {
                    "playerName": room.players[guess.player_id].name,
                    "valueCents": guess.value_cents,
                    "lockedAt": guess.locked_at,
                    "cardSeconds": guess.card_seconds if not guess.timed_out else None,
                    "timedOut": guess.timed_out,
                }
            )
            for guess in card.guesses.values()
            if guess.status in ("LOCKED", "AUTO_LOCKED", "SCORED_ZERO")
            and guess.value_cents is not None
        ]
        reveal_card = RevealSlideCard.model_validate(
            {
                "cardId": card.id,
                "authorName": author.name,
                "authored": authored,
                "original": original,
                "guesses": guesses,
                "axisMinCents": 100,
                "axisMaxCents": 100000,
            }
        )
        slide = RevealSlide.model_validate(
            {
                "slideIndex": index,
                "slideCount": len(room.reveal_order),
                "autoAdvanceAt": room.deadline,
                "canAdvance": session.player_id == room.creator_player_id,
                "card": reveal_card,
            }
        )
        return _response(slide, 200)

    async def games_current_reveal_advance_post(self) -> Response:
        room, session = _room()
        room.advance_reveal(session.player_id)
        await persist_room(room)
        return Response(status_code=202)


class VoteFinalApiImpl(BaseVoteFinalApi):
    async def rooms_room_code_replay_post(self, roomCode: str) -> JSONResponse:
        session = require_session()
        if session.room_code.upper() != roomCode.upper():
            raise ApiError(403, "WRONG_ROOM")
        room = registry.get_by_code(roomCode)
        if room is None:
            raise ApiError(404, "ROOM_NOT_FOUND")
        if session.player_id != room.creator_player_id:
            raise ApiError(403, "NOT_CREATOR")
        if room.phase.value != "FINAL":
            raise ApiError(
                409, "WRONG_PHASE", phase=room.phase.value, retry_in_phase="FINAL"
            )
        if room.immutable:
            raise ApiError(
                409, "WRONG_PHASE", phase=room.phase.value, retry_in_phase="FINAL"
            )
        new_room = registry.replay(room, session.player_id)
        await persist_room(room)
        await persist_room(new_room)
        await asyncio.sleep(0)
        from openapi_server.impl.realtime import connections

        await connections.close_room(room.id, 4411)
        result = ReplayResponse.model_validate(
            {
                "newRoomId": new_room.id,
                "newRoomCode": new_room.code,
                "seatClaimExpiresAt": new_room.seat_claim_expires_at,
            }
        )
        return _response(result, 201)

    async def games_current_vote_options_get(self) -> JSONResponse:
        room, session = _room()
        card_ids = room.vote_options(session.player_id)
        options = [
            VoteOptionsOptionsInner.model_validate(
                {
                    "cardId": card_id,
                    "authorName": room.players[room.cards[card_id].author_id].name,
                    "title": room.cards[card_id].title,
                    "category": room.cards[card_id].category,
                    "starRating": room.cards[card_id].star_rating,
                    "reviewBucket": room.cards[card_id].review_bucket,
                }
            )
            for card_id in card_ids
        ]
        result = VoteOptions.model_validate(
            {
                "options": options,
                "deadlineAt": room.vote_deadline or room.deadline,
                "myVoteCast": session.player_id in room.votes,
            }
        )
        return _response(result, 200)

    async def games_current_vote_post(
        self, games_current_vote_post_request: GamesCurrentVotePostRequest
    ) -> Response:
        room, session = _room()
        room.vote(session.player_id, games_current_vote_post_request.card_id.hex)
        await persist_room(room)
        return Response(status_code=202)

    async def games_current_final_get(self) -> JSONResponse:
        room, _ = _room()
        if room.phase.value != "FINAL":
            raise ApiError(
                409, "WRONG_PHASE", phase=room.phase.value, retry_in_phase="FINAL"
            )
        per_player = {}
        for player in room.seats:
            guesser = sum(
                g.points
                for card in room.cards.values()
                for g in card.guesses.values()
                if g.player_id == player.id and not player.kicked
            )
            authored_points = sum(
                card.author_points
                for card in room.cards.values()
                if card.author_id == player.id and card.status == "SUBMITTED"
            )
            bonus = sum(
                card.funniest_bonus
                for card in room.cards.values()
                if card.author_id == player.id and card.status == "SUBMITTED"
            )
            rows = []
            for card in room.cards.values():
                if card.status != "SUBMITTED":
                    continue
                if card.author_id == player.id:
                    rows.append(
                        {
                            "cardId": card.id,
                            "role": "AUTHOR",
                            "status": "SUBMITTED",
                            "points": card.author_points,
                            "funniestVotes": card.funniest_votes,
                        }
                    )
                guess = card.guesses.get(player.id)
                if guess:
                    rows.append(
                        {
                            "cardId": card.id,
                            "role": "GUESSER",
                            "status": guess.status,
                            "points": guess.points,
                            "accuracy": guess.accuracy,
                            "lockedAt": guess.locked_at,
                        }
                    )
            per_player[player.id] = {
                "player": player,
                "guesser": guesser,
                "author": authored_points,
                "bonus": bonus,
                "total": guesser + authored_points + bonus,
                "perCard": rows,
            }
        ordered = sorted(
            per_player.values(),
            key=lambda entry: (-entry["total"], entry["player"].joined_at),
        )
        unique_winner = len(ordered) == 1 or (
            ordered and ordered[0]["total"] > ordered[1]["total"]
        )
        rankings = []
        last_score = None
        rank = 0
        for position, entry in enumerate(ordered, 1):
            if entry["total"] != last_score:
                rank = position
                last_score = entry["total"]
            breakdown = FinalScoreboardRankingsInnerBreakdown.model_validate(
                {
                    "guesserPoints": entry["guesser"],
                    "authorPoints": entry["author"],
                    "funniestBonus": entry["bonus"],
                }
            )
            rankings.append(
                FinalScoreboardRankingsInner.model_validate(
                    {
                        "rank": rank,
                        "playerId": entry["player"].id,
                        "name": entry["player"].name,
                        "totalPoints": entry["total"],
                        "breakdown": breakdown,
                        "perCard": [
                            FinalScoreboardRankingsInnerPerCardInner.model_validate(row)
                            for row in entry["perCard"]
                        ],
                    }
                )
            )
        result = FinalScoreboard.model_validate(
            {
                "endedReason": room.end_reason or "COMPLETED",
                "winnerPlayerId": (
                    ordered[0]["player"].id if unique_winner and ordered else None
                ),
                "rankings": rankings,
            }
        )
        return _response(result, 200)
