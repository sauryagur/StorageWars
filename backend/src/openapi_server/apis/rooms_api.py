# coding: utf-8

from typing import Dict, List  # noqa: F401
import importlib
import pkgutil

from openapi_server.apis.rooms_api_base import BaseRoomsApi
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
from typing_extensions import Annotated
from openapi_server.models.error import Error
from openapi_server.models.inline_object1 import InlineObject1
from openapi_server.models.join_response import JoinResponse
from openapi_server.models.room_state import RoomState
from openapi_server.models.rooms_post_request import RoomsPostRequest
from openapi_server.models.rooms_room_code_join_post_request import RoomsRoomCodeJoinPostRequest
from openapi_server.models.rooms_room_code_start_post202_response import RoomsRoomCodeStartPost202Response
from openapi_server.models.extra_models import TokenModel  # noqa: F401
from openapi_server.security_api import get_token_sessionToken

router = APIRouter()

ns_pkg = openapi_server.impl
for _, name, _ in pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + "."):
    importlib.import_module(name)


@router.post(
    "/rooms",
    responses={
        201: {"model": JoinResponse, "description": "Room created; caller joined as creator."},
        422: {"model": InlineObject1, "description": "Input validation failure."},
        429: {"model": Error, "description": "Rate-limited (join enumeration, ticket minting, or input flood)."},
    },
    tags=["Rooms"],
    summary="Create a room and join as creator",
    response_model_by_alias=True,
)
async def rooms_post(
    rooms_post_request: RoomsPostRequest = Body(..., description=""),
) -> JoinResponse:
    if not BaseRoomsApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseRoomsApi.subclasses[0]().rooms_post(rooms_post_request)


@router.post(
    "/rooms/{roomCode}/join",
    responses={
        200: {"model": JoinResponse, "description": "Joined or rejoined."},
        404: {"model": Error, "description": "Room not found or TTL-expired."},
        409: {"model": Error, "description": "New join blocked: game in progress, room full (8), or name taken. Rejoin requests never receive GAME_IN_PROGRESS. "},
        410: {"model": Error, "description": "Rejoin token expired or seat reclaimed (grace period elapsed, or the room closed)."},
        422: {"model": InlineObject1, "description": "Input validation failure."},
        429: {"model": Error, "description": "Rate-limited (join enumeration, ticket minting, or input flood)."},
    },
    tags=["Rooms"],
    summary="Join a room, or rejoin an existing seat",
    response_model_by_alias=True,
)
async def rooms_room_code_join_post(
    roomCode: Annotated[str, Field(min_length=4, max_length=4, description="4-character room code (convenience ID, not a secret).")] = Path(..., description="4-character room code (convenience ID, not a secret).", regex=r"^[A-Z0-9]{4}$", min_length=4, max_length=4),
    rooms_room_code_join_post_request: RoomsRoomCodeJoinPostRequest = Body(..., description=""),
) -> JoinResponse:
    """Two distinct operations, discriminated by the request body:  * **New join:** requires &#x60;name&#x60;. Creates a new seat and a new   session token. Returns 409 if the game is in progress, the   room is full, or the name is taken. * **Rejoin:** requires &#x60;sessionToken&#x60; (an existing token from   this room). Resolves the existing seat BEFORE any new-join   prohibition applies — so rejoining during AUTHOR or GUESS is   explicitly permitted. &#x60;name&#x60; is optional and ignored.   Returns the same session token, plus the current phase so   the client can fetch a snapshot. Rejoin is permitted in   LOBBY, AUTHOR, GUESS, REVEAL, and VOTE; in FINAL the token   resolves but the room is read-only.  A failed room code is throttled per IP (429) to blunt enumeration of the 4-character code space. """
    if not BaseRoomsApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseRoomsApi.subclasses[0]().rooms_room_code_join_post(roomCode, rooms_room_code_join_post_request)


@router.get(
    "/rooms/{roomCode}",
    responses={
        200: {"model": RoomState, "description": "Room state."},
        403: {"model": Error, "description": "Not the room creator, token not bound to this room (WRONG_ROOM), or action forbidden for this seat. "},
        404: {"model": Error, "description": "Room not found or TTL-expired."},
    },
    tags=["Rooms"],
    summary="Room / lobby state",
    response_model_by_alias=True,
)
async def rooms_room_code_get(
    roomCode: Annotated[str, Field(min_length=4, max_length=4, description="4-character room code (convenience ID, not a secret).")] = Path(..., description="4-character room code (convenience ID, not a secret).", regex=r"^[A-Z0-9]{4}$", min_length=4, max_length=4),
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> RoomState:
    """Current phase and player list. The session token must belong to a seat in this room. Never contains game secrets or scores. """
    if not BaseRoomsApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseRoomsApi.subclasses[0]().rooms_room_code_get(roomCode)


@router.post(
    "/rooms/{roomCode}/start",
    responses={
        202: {"model": RoomsRoomCodeStartPost202Response, "description": "Game started; room in AUTHOR."},
        403: {"model": Error, "description": "Not the room creator, token not bound to this room (WRONG_ROOM), or action forbidden for this seat. "},
        409: {"model": Error, "description": "Fewer than 2 players, or game in progress."},
    },
    tags=["Rooms"],
    summary="Start the game (creator only)",
    response_model_by_alias=True,
)
async def rooms_room_code_start_post(
    roomCode: Annotated[str, Field(min_length=4, max_length=4, description="4-character room code (convenience ID, not a secret).")] = Path(..., description="4-character room code (convenience ID, not a secret).", regex=r"^[A-Z0-9]{4}$", min_length=4, max_length=4),
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> RoomsRoomCodeStartPost202Response:
    """Samples N distinct products — log-uniform by price, sampled WITHOUT replacement within the game, one per player — and moves the room to AUTHOR with a 60-second server timer. The (room, product) uniqueness invariant is enforced server-side. """
    if not BaseRoomsApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseRoomsApi.subclasses[0]().rooms_room_code_start_post(roomCode)
