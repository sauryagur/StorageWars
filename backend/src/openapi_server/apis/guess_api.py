# coding: utf-8

from typing import Dict, List  # noqa: F401
import importlib
import pkgutil

from openapi_server.apis.guess_api_base import BaseGuessApi
import openapi_server.impl

from fastapi import (  # noqa: F401
    APIRouter,
    Body,
    Cookie,
    Depends,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    Response,
    Security,
    status,
)

from typing import Any
from uuid import UUID
from openapi_server.models.error import Error
from openapi_server.models.guess_card_view import GuessCardView
from openapi_server.models.guess_queue import GuessQueue
from openapi_server.models.inline_object import InlineObject
from openapi_server.models.lock_response import LockResponse
from openapi_server.models.value_echo import ValueEcho
from openapi_server.models.value_input import ValueInput
from openapi_server.models.extra_models import TokenModel  # noqa: F401
from openapi_server.security_api import get_token_sessionToken

router = APIRouter()

ns_pkg = openapi_server.impl
for _, name, _ in pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + "."):
    importlib.import_module(name)


@router.get(
    "/games/current/guess/queue",
    responses={
        200: {"model": GuessQueue, "description": "Queue stubs plus progress counts."},
        409: {"model": InlineObject, "description": "Operation not valid for the current phase."},
    },
    tags=["Guess"],
    summary="My shuffled card queue",
    response_model_by_alias=True,
)
async def games_current_guess_queue_get(
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> GuessQueue:
    """Card order is shuffled PER PLAYER, so card positions reveal nothing on voice chat. Only SUBMITTED cards appear; skipped cards are excluded and not counted in totals. Exposes card IDs and statuses only — content access is governed by the server-side one-active-card state machine on the open endpoint, regardless of what IDs a client holds. """
    if not BaseGuessApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseGuessApi.subclasses[0]().games_current_guess_queue_get()


@router.post(
    "/games/current/guess/cards/{cardId}/open",
    responses={
        200: {"model": GuessCardView, "description": "Card opened; returns the 0s-drip representation."},
        404: {"model": Error, "description": "Card not in this player&#39;s queue."},
        409: {"model": Error, "description": "Not the next eligible card, another card is active, the card is locked, or wrong phase. The error carries the client&#39;s authoritative queue position so it can recover. "},
        429: {"model": Error, "description": "Open attempts rate-limited (anti-fuzzing)."},
    },
    tags=["Guess"],
    summary="Open the next card (starts its drip schedule)",
    response_model_by_alias=True,
)
async def games_current_guess_cards_card_id_open_post(
    cardId: UUID = Path(..., description=""),
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> GuessCardView:
    """THE queue state machine, server-enforced:  * Exactly ONE active card per player at any time. * Only the player&#39;s NEXT eligible card may be opened. Opening   a future card, a locked card, an already-open card, or a   card not in this player&#39;s queue is rejected (409/404). * Opening a card starts its drip timers ONCE; retries can   never reset or extend them. * A locked card cannot be reopened or modified. * The server, not the client, determines queue position and   whether a lock advances it.  This is a POST because it changes state; the GET on the card is read-only and always returns the current representation. """
    if not BaseGuessApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseGuessApi.subclasses[0]().games_current_guess_cards_card_id_open_post(cardId)


@router.get(
    "/games/current/guess/cards/{cardId}",
    responses={
        200: {"model": GuessCardView, "description": "Drip-redacted card view."},
        404: {"model": Error, "description": "Card not in this player&#39;s queue."},
        409: {"model": InlineObject, "description": "Operation not valid for the current phase."},
    },
    tags=["Guess"],
    summary="Read my active card (drip-redacted, read-only)",
    response_model_by_alias=True,
)
async def games_current_guess_cards_card_id_get(
    cardId: UUID = Path(..., description=""),
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> GuessCardView:
    """Read-only. NEVER starts or resets timers — only &#x60;open&#x60; does. The card&#39;s information is determined by the server clock relative to the server-recorded &#x60;openedAt&#x60;:  * 0s — title, category * 5s — bullet slots * 10s — star rating, review-count bucket * 20s — hard cap; latest draft value auto-locks  ABSENT field &#x3D; drip stage not reached. &#x60;null&#x60; &#x3D; the stage is reached but the author left the field blank. Distinct meanings, never conflated. This schema structurally cannot carry the image, original title, original description, or price. """
    if not BaseGuessApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseGuessApi.subclasses[0]().games_current_guess_cards_card_id_get(cardId)


@router.put(
    "/games/current/guess/cards/{cardId}/draft",
    responses={
        200: {"model": ValueEcho, "description": "Draft accepted (and normalized)."},
        404: {"model": Error, "description": "Card not in this player&#39;s queue."},
        409: {"model": Error, "description": "Card is not the active card, already locked, or wrong phase."},
        422: {"model": Error, "description": "Non-numeric / unparseable value."},
    },
    tags=["Guess"],
    summary="Update the server-side draft value (the slider position)",
    response_model_by_alias=True,
)
async def games_current_guess_cards_card_id_draft_put(
    cardId: UUID = Path(..., description=""),
    value_input: ValueInput = Body(..., description=""),
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> ValueEcho:
    """Keeps the latest slider position in authoritative server state. THIS is what makes the disconnect auto-lock rule implementable: a player who drafts $127.50, touches the slider, and then loses their connection has their draft auto-locked at the card&#39;s 20s cap. A player who never touched the slider scores zero. Drafts are throttled server-side (coalesced; only the latest value matters) and are NOT persisted per-keystroke — the latest value is authoritative and persisted at lock time or cap time. Numeric values are clamped to [100, 100000] cents and rounded per the money rule; the normalized value is echoed. """
    if not BaseGuessApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseGuessApi.subclasses[0]().games_current_guess_cards_card_id_draft_put(cardId, value_input)


@router.post(
    "/games/current/guess/cards/{cardId}/touch",
    responses={
        204: {"description": "Touch recorded (idempotent)."},
        409: {"model": InlineObject, "description": "Operation not valid for the current phase."},
    },
    tags=["Guess"],
    summary="Report slider touched (enables Lock)",
    response_model_by_alias=True,
)
async def games_current_guess_cards_card_id_touch_post(
    cardId: UUID = Path(..., description=""),
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> None:
    """Idempotent. Lock is disabled until the slider has been touched AND 3 seconds of minimum dwell have elapsed since open. Touch state also governs disconnect auto-lock (auto-lock fires only if touched). """
    if not BaseGuessApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseGuessApi.subclasses[0]().games_current_guess_cards_card_id_touch_post(cardId)


@router.post(
    "/games/current/guess/cards/{cardId}/lock",
    responses={
        200: {"model": LockResponse, "description": "Lock confirmed."},
        403: {"model": Error, "description": "Minimum dwell (3s) not met, slider untouched, or card already locked. "},
        404: {"model": Error, "description": "Card not in this player&#39;s queue."},
        409: {"model": InlineObject, "description": "Operation not valid for the current phase."},
        422: {"model": Error, "description": "Non-numeric value."},
    },
    tags=["Guess"],
    summary="Lock my guess (permanent)",
    response_model_by_alias=True,
)
async def games_current_guess_cards_card_id_lock_post(
    cardId: UUID = Path(..., description=""),
    value_input: ValueInput = Body(..., description=""),
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> LockResponse:
    """Commits the guess permanently and advances the queue. The lock timestamp is stamped by the SERVER. The live multiplier is M(t) &#x3D; 1.0 - 0.3 * (t / 20), t &#x3D; server-measured seconds on the card, clamped to [0, 20]. Points are computed server-side but NEVER returned before FINAL.  Value handling: numeric input is clamped to [100, 100000] cents and rounded per the money rule ($20+ -&gt; whole dollars); the normalized value is echoed with &#x60;wasClamped&#x60;/&#x60;wasRounded&#x60; flags so typos are visible. Non-numeric input is rejected (422). Locking without a prior draft/touch is rejected (403 SLIDER_UNTOUCHED). """
    if not BaseGuessApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseGuessApi.subclasses[0]().games_current_guess_cards_card_id_lock_post(cardId, value_input)
