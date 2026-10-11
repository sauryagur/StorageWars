"""Explicit serializers at the API redaction boundary.

Functions accept engine/dataclass values and return generated Pydantic response
models. Handlers should serialize those models with
``model_dump(by_alias=True, exclude_unset=True, mode="json")``.

Guesser serializers deliberately select only safe fields; never pass a product
or its raw attributes through to a guesser-facing model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

from openapi_server.models.author_card_stored import AuthorCardStored
from openapi_server.models.author_card_view import AuthorCardView
from openapi_server.models.author_card_view_constraints import AuthorCardViewConstraints
from openapi_server.models.final_scoreboard import FinalScoreboard
from openapi_server.models.game_snapshot import GameSnapshot
from openapi_server.models.guess_card_view import GuessCardView
from openapi_server.models.guess_queue import GuessQueue
from openapi_server.models.join_response import JoinResponse
from openapi_server.models.lock_response import LockResponse
from openapi_server.models.product_admin import ProductAdmin
from openapi_server.models.replay_response import ReplayResponse
from openapi_server.models.report_admin import ReportAdmin
from openapi_server.models.reveal_slide import RevealSlide
from openapi_server.models.room_state import RoomState
from openapi_server.models.value_echo import ValueEcho
from openapi_server.models.vote_options import VoteOptions


def _get(value: Any, key: str, default: Any = None) -> Any:
    return (
        value.get(key, default)
        if isinstance(value, Mapping)
        else getattr(value, key, default)
    )


def join_response(
    room: Any, player: Any, token: str, *, rejoined: bool = False
) -> JoinResponse:
    """Build JoinResponse from a room/seat and the newly issued plaintext token."""
    return JoinResponse(
        roomId=_get(room, "id"),
        roomCode=_get(room, "code"),
        playerId=_get(player, "id"),
        sessionToken=token,
        isCreator=bool(_get(player, "creator", False)),
        rejoined=rejoined,
        phase=_get(room, "phase"),
        ttlExpiresAt=_get(room, "ttl_expires_at"),
        snapshotUrl=(
            None
            if str(_get(room, "phase")) in ("LOBBY", "Phase.LOBBY")
            else "/v1/games/current/snapshot"
        ),
    )


def room_state(room: Any, caller_id: str) -> RoomState:
    """Return lobby/room data; product information is intentionally excluded."""
    players = [
        _get(p, "__view__", None)
        or {
            "playerId": _get(p, "id"),
            "displayName": _get(p, "name"),
            "isCreator": bool(_get(p, "creator", False)),
            "connected": bool(_get(p, "connected", True)),
        }
        for p in _get(room, "players", [])
    ]
    creator = any(
        str(_get(p, "id")) == str(caller_id) and _get(p, "creator", False)
        for p in _get(room, "players", [])
    )
    phase = _get(room, "phase")
    return RoomState(
        phase=phase,
        players=players,
        canStart=creator
        and len(players) >= 2
        and len(players) <= 8
        and str(phase) in ("LOBBY", "Phase.LOBBY"),
        isCreator=creator,
        ttlExpiresAt=_get(room, "ttl_expires_at"),
    )


def replay_response(room: Any, claim_expires_at: datetime) -> ReplayResponse:
    """Describe the new replay room and its seat-claim deadline."""
    return ReplayResponse(
        newRoomId=_get(room, "id"),
        newRoomCode=_get(room, "code"),
        seatClaimExpiresAt=claim_expires_at,
    )


def author_card_view(
    card: Any, image_url: str, price_band: Any, *, deadline_at: datetime
) -> AuthorCardView:
    """Expose only image and price band to the author during AUTHOR."""
    constraints = AuthorCardViewConstraints(
        titleMinChars=8,
        titleMaxChars=60,
        bulletMinChars=15,
        bulletMaxChars=80,
        bulletSlots=3,
        starRatingMin=1.0,
        starRatingMax=5.0,
        starRatingStep=0.5,
    )
    return AuthorCardView(
        cardId=_get(card, "id"),
        imageUrl=image_url,
        priceBand=price_band,
        deadlineAt=deadline_at,
        status=_get(card, "status"),
        constraints=constraints,
    )


def author_card_stored(card: Any) -> AuthorCardStored:
    """Return the author's saved draft, including blank fields as null."""
    return AuthorCardStored(
        cardId=_get(card, "id"),
        status=_get(card, "status"),
        submittedAt=_get(card, "submitted_at"),
        title=_get(card, "title"),
        bullets=_get(card, "bullets"),
        starRating=_get(card, "star_rating"),
        reviewBucket=_get(card, "review_bucket"),
        category=_get(card, "category"),
    )


def guess_queue(
    cards: Iterable[Any],
    player_id: str,
    *,
    active_card_id: Any,
    next_card_id: Any,
    all_done: bool,
    progress: Any,
) -> GuessQueue:
    """Build a redacted queue and the caller's progress/position."""
    from openapi_server.models.guess_queue_cards_inner import GuessQueueCardsInner
    from openapi_server.models.guess_queue_my_position import GuessQueueMyPosition

    queue_status = {
        "QUEUED": "UNOPENED",
        "AUTO_LOCKED": "TIMED_OUT",
        "SCORED_ZERO": "TIMED_OUT",
    }
    safe_cards = []
    for card in cards:
        if (
            str(_get(card, "author_id")) == str(player_id)
            or _get(card, "status") != "SUBMITTED"
        ):
            continue
        guess = _get(card, "guesses", {}).get(player_id)
        status = _get(guess, "status", "QUEUED")
        safe_cards.append(
            GuessQueueCardsInner(
                cardId=_get(card, "id"),
                status=queue_status.get(status, status),
            )
        )
    return GuessQueue(
        cards=safe_cards,
        myPosition=GuessQueueMyPosition(
            activeCardId=active_card_id, nextCardId=next_card_id, allDone=all_done
        ),
        progress=progress,
    )


def guess_card_view(card: Any, guess: Any, now: datetime) -> GuessCardView:
    """Serialize a guess card without any product secret. Drip keys are omitted
    until their timestamp has arrived; after arrival a blank author value is
    explicitly serialized as null (including a null bullet list).
    """
    values: dict[str, Any] = {
        "cardId": _get(card, "id"),
        "status": _get(guess, "status"),
        "openedAt": _get(guess, "opened_at"),
        "capAt": _get(guess, "cap_at"),
        "lockEligibleAt": _get(guess, "lock_eligible_at"),
        "multiplierNow": _get(guess, "multiplier", 1.0),
        "draftValueCents": (
            _get(guess, "value_cents") if _get(guess, "draft_present", False) else None
        ),
        "sliderTouched": bool(_get(guess, "slider_touched", False)),
        "title": _get(card, "title"),
        "category": _get(card, "category"),
    }
    if _get(guess, "locked_at") is not None:
        values["locked"] = True
        values["lockedValueCents"] = _get(guess, "value_cents")
    if _get(guess, "drip_bullets_at") is not None and now >= _get(
        guess, "drip_bullets_at"
    ):
        values["bullets"] = _get(card, "bullets")
    if _get(guess, "drip_rating_at") is not None and now >= _get(
        guess, "drip_rating_at"
    ):
        values["starRating"] = _get(card, "star_rating")
        values["reviewBucket"] = _get(card, "review_bucket")
    return GuessCardView(**values)


def value_echo(
    value_cents: int,
    formatted_value: str,
    *,
    was_clamped: bool = False,
    was_rounded: bool = False,
) -> ValueEcho:
    """Echo the accepted normalized draft and its display form."""
    return ValueEcho(
        valueCents=value_cents,
        formattedValue=formatted_value,
        wasClamped=was_clamped,
        wasRounded=was_rounded,
    )


def lock_response(
    guess: Any,
    *,
    card_id: Any,
    locked_at: datetime,
    formatted_value: str,
    was_clamped: bool = False,
    was_rounded: bool = False,
    next_card_id: Any = None,
) -> LockResponse:
    """Return the lock acknowledgement; it contains no product truth or score."""
    return LockResponse(
        cardId=card_id,
        lockedAt=locked_at,
        cardSeconds=_get(guess, "card_seconds"),
        multiplier=_get(guess, "multiplier"),
        valueCents=_get(guess, "value_cents"),
        formattedValue=formatted_value,
        wasClamped=was_clamped,
        wasRounded=was_rounded,
        nextCardId=next_card_id,
    )


def game_snapshot(
    room: Any, player_id: str, *, seq: int, phase_view: Mapping[str, Any] | None = None
) -> GameSnapshot:
    """Create a per-player snapshot; copy only the supplied phase block."""
    phase = _get(room, "phase")
    data = {
        "roomId": _get(room, "id"),
        "roomCode": _get(room, "code"),
        "playerId": player_id,
        "phase": phase,
        "seq": seq,
    }
    if phase_view:
        data.update(phase_view)
    return GameSnapshot(**data)


def reveal_slide(
    card: Any, *, index: int, total: int, auto_advance_at: datetime, can_advance: bool
) -> RevealSlide:
    """Serialize complete card truth for the REVEAL phase only."""
    from openapi_server.models.author_card_submission import AuthorCardSubmission
    from openapi_server.models.reveal_slide_card import RevealSlideCard
    from openapi_server.models.reveal_slide_card_original import RevealSlideCardOriginal
    from openapi_server.models.reveal_slide_card_guesses_inner import (
        RevealSlideCardGuessesInner,
    )

    product = _get(card, "product")
    original = RevealSlideCardOriginal(
        title=_get(product, "original_title"),
        description=_get(product, "original_description"),
        imageUrl=_get(product, "image_url"),
        priceCents=_get(product, "price_cents"),
        priceBand=_get(product, "price_band"),
        snapshotDate=_get(product, "snapshot_date"),
    )
    authored = AuthorCardSubmission(
        title=_get(card, "title"),
        category=_get(card, "category"),
        bullets=_get(card, "bullets"),
        starRating=_get(card, "star_rating"),
        reviewBucket=_get(card, "review_bucket"),
    )
    guesses = [
        RevealSlideCardGuessesInner(
            playerId=gid,
            valueCents=_get(g, "value_cents"),
            points=_get(g, "points"),
            accuracy=_get(g, "accuracy"),
            cardSeconds=_get(g, "card_seconds"),
            multiplier=_get(g, "multiplier"),
            timedOut=_get(g, "timed_out"),
        )
        for gid, g in _get(card, "guesses", {}).items()
    ]
    card_model = RevealSlideCard(
        cardId=_get(card, "id"),
        authorName=_get(_get(card, "author"), "name", "Player"),
        authored=authored,
        original=original,
        guesses=guesses,
    )
    return RevealSlide(
        slideIndex=index,
        slideCount=total,
        autoAdvanceAt=auto_advance_at,
        canAdvance=can_advance,
        card=card_model,
    )


def vote_options(
    cards: Iterable[Any], player_id: str, *, deadline_at: datetime, my_vote_cast: bool
) -> VoteOptions:
    """Return voteable authored summaries, excluding the caller's own card."""
    from openapi_server.models.vote_options_options_inner import VoteOptionsOptionsInner

    options = [
        VoteOptionsOptionsInner(
            cardId=_get(c, "id"),
            authorName=_get(_get(c, "author"), "name", "Player"),
            title=_get(c, "title"),
            category=_get(c, "category"),
            starRating=_get(c, "star_rating"),
            reviewBucket=_get(c, "review_bucket"),
        )
        for c in cards
        if str(_get(c, "author_id")) != str(player_id)
        and _get(c, "status") == "SUBMITTED"
    ]
    return VoteOptions(options=options, deadlineAt=deadline_at, myVoteCast=my_vote_cast)


def final_scoreboard(data: Mapping[str, Any]) -> FinalScoreboard:
    """Validate and wrap the fully computed final scoreboard payload."""
    return FinalScoreboard(**dict(data))


def product_admin(product: Any) -> ProductAdmin:
    """Serialize an administrative product record."""
    return ProductAdmin(
        id=_get(product, "id"),
        imageStorageKey=_get(product, "image_storage_key"),
        originalTitle=_get(product, "original_title"),
        originalDescription=_get(product, "original_description"),
        priceCents=_get(product, "price_cents"),
        currency=_get(product, "currency", "USD"),
        category=_get(product, "category"),
        starRating=_get(product, "star_rating"),
        reviewCount=_get(product, "review_count"),
        snapshotDate=_get(product, "snapshot_date"),
        priceBand=_get(product, "price_band"),
        active=_get(product, "active", True),
    )


def report_admin(report: Any) -> ReportAdmin:
    """Serialize an administrative report row."""
    return ReportAdmin(
        id=_get(report, "id"),
        roomCode=_get(report, "room_code"),
        reportedCardId=_get(report, "reported_card_id"),
        reportedPlayerId=_get(report, "reported_player_id"),
        reporterPlayerId=_get(report, "reporter_player_id"),
        reason=_get(report, "reason"),
        note=_get(report, "note"),
        status=_get(report, "status"),
        resolutionNote=_get(report, "resolution_note"),
        createdAt=_get(report, "created_at"),
    )
