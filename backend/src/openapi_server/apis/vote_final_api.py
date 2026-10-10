# coding: utf-8

from typing import Dict, List  # noqa: F401
import importlib
import pkgutil

from openapi_server.apis.vote_final_api_base import BaseVoteFinalApi
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

from pydantic import Field, field_validator
from typing import Any
from typing_extensions import Annotated
from openapi_server.models.error import Error
from openapi_server.models.final_scoreboard import FinalScoreboard
from openapi_server.models.games_current_vote_post_request import GamesCurrentVotePostRequest
from openapi_server.models.inline_object import InlineObject
from openapi_server.models.replay_response import ReplayResponse
from openapi_server.models.vote_options import VoteOptions
from openapi_server.models.extra_models import TokenModel  # noqa: F401
from openapi_server.security_api import get_token_sessionToken

router = APIRouter()

ns_pkg = openapi_server.impl
for _, name, _ in pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + "."):
    importlib.import_module(name)


@router.post(
    "/rooms/{roomCode}/replay",
    responses={
        201: {"model": ReplayResponse, "description": "New room created; seat claim window opened."},
        403: {"model": Error, "description": "Not the room creator, token not bound to this room (WRONG_ROOM), or action forbidden for this seat. "},
        409: {"model": Error, "description": "Not in FINAL phase."},
    },
    tags=["Vote &amp; Final"],
    summary="Create a replay room (creator only, FINAL phase only)",
    response_model_by_alias=True,
)
async def rooms_room_code_replay_post(
    roomCode: Annotated[str, Field(min_length=4, max_length=4, description="4-character room code (convenience ID, not a secret).")] = Path(..., description="4-character room code (convenience ID, not a secret).", regex=r"^[A-Z0-9]{4}$", min_length=4, max_length=4),
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> ReplayResponse:
    """REPLAY SEMANTICS (single model): replay always creates a NEW room linked to the old one via replayOfRoomId. The old room, its records, and its scores are immutable history. The creator receives the new room code and a seat-claim window. Every player (including the creator) claims a seat in the new room by calling join with their EXISTING session token inside the window; the server maps old token to new seat, so no new credentials are issued and no player ever receives another player&#39;s token. Unclaimed seats expire with the window. """
    if not BaseVoteFinalApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseVoteFinalApi.subclasses[0]().rooms_room_code_replay_post(roomCode)


@router.get(
    "/games/current/vote/options",
    responses={
        200: {"model": VoteOptions, "description": "Vote options."},
        409: {"model": InlineObject, "description": "Operation not valid for the current phase."},
    },
    tags=["Vote &amp; Final"],
    summary="Cards eligible for my funniest-card vote",
    response_model_by_alias=True,
)
async def games_current_vote_options_get(
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> VoteOptions:
    """The canonical vote-phase representation: the SUBMITTED cards excluding the voter&#39;s own, with the minimal presentation needed to choose one. A rejoining client that missed slides recovers its options from here (and from the snapshot). Individual votes and tallies remain hidden until FINAL. Voting ends when all eligible players have voted OR the vote deadline (server-set, ~30s, tunable) expires; non-voters simply record no vote and cost no one anything. """
    if not BaseVoteFinalApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseVoteFinalApi.subclasses[0]().games_current_vote_options_get()


@router.post(
    "/games/current/vote",
    responses={
        202: {"description": "Vote recorded."},
        403: {"model": Error, "description": "Cannot vote for own card."},
        409: {"model": Error, "description": "Already voted, or wrong phase."},
    },
    tags=["Vote &amp; Final"],
    summary="Cast funniest-card vote (one, final)",
    response_model_by_alias=True,
)
async def games_current_vote_post(
    games_current_vote_post_request: GamesCurrentVotePostRequest = Body(..., description=""),
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> None:
    """One hidden vote per player, for a card that is not the voter&#39;s own. The vote is FINAL when cast — it cannot be replaced or withdrawn (409 ALREADY_VOTED). Most votes wins +300 for the author, split on ties. Votes cast for a card whose author is later kicked are discarded; the kicked player&#39;s own vote is also discarded. """
    if not BaseVoteFinalApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseVoteFinalApi.subclasses[0]().games_current_vote_post(games_current_vote_post_request)


@router.get(
    "/games/current/final",
    responses={
        200: {"model": FinalScoreboard, "description": "Final scoreboard."},
        409: {"model": InlineObject, "description": "Operation not valid for the current phase."},
    },
    tags=["Vote &amp; Final"],
    summary="Final scoreboard",
    response_model_by_alias=True,
)
async def games_current_final_get(
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> FinalScoreboard:
    """Ranked scoreboard with full breakdown. Also the result for EARLY-ENDED games: &#x60;endedReason&#x60; is TOO_FEW_PLAYERS when a votekick dropped the room under 4 players, and the response includes only the cards completed by that point — the client never has to infer how an interrupted phase resolves. Author points use the mean accuracy over ALL eligible guessers on the card (kicked players excluded; zero-accuracy and timed-out guesses count as 0 in the denominator — never a mean over locked guesses only). """
    if not BaseVoteFinalApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseVoteFinalApi.subclasses[0]().games_current_final_get()
