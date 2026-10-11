from __future__ import annotations

from fastapi.responses import JSONResponse

from openapi_server.apis.rooms_api_base import BaseRoomsApi
from openapi_server.impl.context import client_ip
from openapi_server.impl.context import SessionContext
from openapi_server.impl.engine.registry import registry
from openapi_server.impl.errors import ApiError, require_session
from openapi_server.impl.persistence import persist_room
from openapi_server.impl.products import sample_products
from openapi_server.impl.ratelimit import check_rate_limit
from openapi_server.impl.validation import validate_display_name
from openapi_server.models.join_response import JoinResponse
from openapi_server.models.room_state import RoomState
from openapi_server.models.room_state_players_inner import RoomStatePlayersInner
from openapi_server.models.rooms_room_code_start_post202_response import (
    RoomsRoomCodeStartPost202Response,
)
from openapi_server.models.rooms_post_request import RoomsPostRequest
from openapi_server.models.rooms_room_code_join_post_request import (
    RoomsRoomCodeJoinPostRequest,
)


def _response(model, status_code: int) -> JSONResponse:
    return JSONResponse(
        model.model_dump(by_alias=True, exclude_unset=True, mode="json"),
        status_code=status_code,
    )


def _session_in_room(room_code: str) -> SessionContext:
    session = require_session()
    if session.room_code.upper() != room_code.upper():
        raise ApiError(403, "WRONG_ROOM")
    return session


def _join_response(room, player, token: str, *, rejoined: bool = False) -> JoinResponse:
    values = {
        "roomId": room.id,
        "roomCode": room.code,
        "playerId": player.id,
        "sessionToken": token,
        "isCreator": player.id == room.creator_player_id,
        "rejoined": rejoined,
        "phase": room.phase.value,
        "ttlExpiresAt": room.ttl_expires_at,
    }
    if rejoined and room.phase.value != "LOBBY":
        values["snapshotUrl"] = "/v1/games/current/snapshot"
    return JoinResponse.model_validate(values)


async def _display_name_errors(name: str):
    from openapi_server.impl.content import load_banned_words

    return validate_display_name(name, await load_banned_words())


class RoomsApiImpl(BaseRoomsApi):
    async def rooms_post(self, rooms_post_request: RoomsPostRequest) -> JSONResponse:
        check_rate_limit("create_ip", client_ip.get())
        name = rooms_post_request.name
        field_errors = await _display_name_errors(name)
        if field_errors:
            raise ApiError(
                422,
                "VALIDATION_FAILED",
                "Invalid display name.",
                field_errors=field_errors,
            )
        room, player, token = registry.create_room(name)
        await persist_room(room)
        return _response(_join_response(room, player, token), 201)

    async def rooms_room_code_join_post(
        self,
        roomCode: str,
        rooms_room_code_join_post_request: RoomsRoomCodeJoinPostRequest,
    ) -> JSONResponse:
        check_rate_limit("join_ip", client_ip.get())
        request = rooms_room_code_join_post_request.actual_instance
        if request is None:
            raise ApiError(422, "VALIDATION_FAILED", "Join request is required.")
        if hasattr(request, "session_token"):
            room, player, token = registry.rejoin(roomCode, request.session_token)
            await persist_room(room)
            return _response(_join_response(room, player, token, rejoined=True), 200)

        field_errors = await _display_name_errors(request.name)
        if field_errors:
            raise ApiError(
                422,
                "VALIDATION_FAILED",
                "Invalid display name.",
                field_errors=field_errors,
            )
        try:
            room, player, token = registry.join(roomCode, request.name)
        except ApiError as exc:
            if exc.code == "ROOM_NOT_FOUND":
                check_rate_limit(
                    "join_failed_code_ip", f"{client_ip.get()}:{roomCode.upper()}"
                )
            raise
        await persist_room(room)
        return _response(_join_response(room, player, token), 200)

    async def rooms_room_code_get(self, roomCode: str) -> JSONResponse:
        session = _session_in_room(roomCode)
        room = registry.get_by_code(roomCode)
        if room.id != session.room_id:
            raise ApiError(403, "WRONG_ROOM")
        player = room.players.get(session.player_id)
        if player is None or player.kicked:
            raise ApiError(403, "WRONG_ROOM")
        players = [
            RoomStatePlayersInner.model_validate(
                {
                    "playerId": seat.id,
                    "name": seat.name,
                    "isCreator": seat.id == room.creator_player_id,
                    "connected": seat.connected,
                }
            )
            for seat in room.seats
        ]
        state = RoomState.model_validate(
            {
                "phase": room.phase.value,
                "players": players,
                "canStart": player.id == room.creator_player_id
                and room.phase.value == "LOBBY"
                and 2 <= len(room.seats) <= 8,
                "isCreator": player.id == room.creator_player_id,
                "ttlExpiresAt": room.ttl_expires_at,
            }
        )
        return _response(state, 200)

    async def rooms_room_code_start_post(self, roomCode: str) -> JSONResponse:
        session = _session_in_room(roomCode)
        room = registry.get_by_code(roomCode)
        if room.id != session.room_id:
            raise ApiError(403, "WRONG_ROOM")
        if session.player_id != room.creator_player_id:
            raise ApiError(403, "NOT_CREATOR")
        if room.phase.value != "LOBBY":
            raise ApiError(409, "GAME_IN_PROGRESS")
        if not 2 <= len(room.seats) <= 8:
            raise ApiError(
                409, "VALIDATION_FAILED", "A room needs 2–8 players to start."
            )
        products = await sample_products(len(room.seats), room.rng)
        room.start(products, session.player_id)
        await persist_room(room)
        response = RoomsRoomCodeStartPost202Response.model_validate(
            {
                "phase": room.phase.value,
                "authorDeadlineAt": room.deadline,
            }
        )
        return _response(response, 202)
