# coding: utf-8

from typing import Dict, List  # noqa: F401
import importlib
import pkgutil

from openapi_server.apis.moderation_api_base import BaseModerationApi
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
from openapi_server.models.inline_object1 import InlineObject1
from openapi_server.models.report_request import ReportRequest
from openapi_server.models.rooms_room_code_votekick_post200_response import RoomsRoomCodeVotekickPost200Response
from openapi_server.models.rooms_room_code_votekick_post_request import RoomsRoomCodeVotekickPostRequest
from openapi_server.models.extra_models import TokenModel  # noqa: F401
from openapi_server.security_api import get_token_sessionToken

router = APIRouter()

ns_pkg = openapi_server.impl
for _, name, _ in pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + "."):
    importlib.import_module(name)


@router.post(
    "/reports",
    responses={
        202: {"description": "Report recorded."},
        422: {"model": InlineObject1, "description": "Input validation failure."},
    },
    tags=["Moderation"],
    summary="Report a card or a player",
    response_model_by_alias=True,
)
async def reports_post(
    report_request: ReportRequest = Body(..., description=""),
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> None:
    """For offensive content or AFK only. Exactly one of reportedCardId / reportedPlayerId must be present, and the target must belong to the reporter&#39;s room. Reports never carry game secrets to moderators before the reveal. """
    if not BaseModerationApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseModerationApi.subclasses[0]().reports_post(report_request)


@router.post(
    "/rooms/{roomCode}/votekick",
    responses={
        200: {"model": RoomsRoomCodeVotekickPost200Response, "description": "Vote recorded or duplicate (idempotent). Returns the current tally. "},
        403: {"model": Error, "description": "Not the room creator, token not bound to this room (WRONG_ROOM), or action forbidden for this seat. "},
        409: {"model": Error, "description": "Another votekick is active for a different target, or wrong phase. "},
    },
    tags=["Moderation"],
    summary="Cast a votekick vote (idempotent)",
    response_model_by_alias=True,
)
async def rooms_room_code_votekick_post(
    roomCode: Annotated[str, Field(min_length=4, max_length=4, description="4-character room code (convenience ID, not a secret).")] = Path(..., description="4-character room code (convenience ID, not a secret).", regex=r"^[A-Z0-9]{4}$", min_length=4, max_length=4),
    rooms_room_code_votekick_post_request: RoomsRoomCodeVotekickPostRequest = Body(..., description=""),
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> RoomsRoomCodeVotekickPost200Response:
    """Reasons are offensive content or AFK only — NOT cheating accusations (per PRD). Semantics:  * Exactly one ACTIVE votekick per room; the active vote must   resolve or expire before a different target can be raised   (409 VOTEKICK_IN_PROGRESS). * One vote per player per votekick. Duplicate calls are   idempotent: they return the current tally and emit no event. * Threshold: ceil(2/3 of OTHER players), evaluated on each   new vote; the kick executes when reached. * The votekick expires after 30s without reaching threshold. * A kicked player&#39;s card and guesses are removed from   everyone&#39;s totals; their vote is discarded, and votes cast   for their card are discarded. Scoring is prior-based, so   removal requires no crowd recomputation. * If fewer than 4 players remain, the game ends early:   phase moves to FINAL with endedReason TOO_FEW_PLAYERS and   the completed cards. * If the target disconnects before resolution, the votekick   is CANCELLED (no kick; disconnect rules apply instead). """
    if not BaseModerationApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseModerationApi.subclasses[0]().rooms_room_code_votekick_post(roomCode, rooms_room_code_votekick_post_request)
