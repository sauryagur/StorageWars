from __future__ import annotations

from fastapi.responses import Response

from openapi_server.apis.moderation_api_base import BaseModerationApi
from openapi_server.impl.db import write
from openapi_server.impl.engine.registry import registry
from openapi_server.impl.errors import ApiError, require_session
from openapi_server.impl.persistence import persist_room
from openapi_server.models.report_request import ReportRequest
from openapi_server.models.rooms_room_code_votekick_post200_response import (
    RoomsRoomCodeVotekickPost200Response,
)
from openapi_server.models.rooms_room_code_votekick_post_request import (
    RoomsRoomCodeVotekickPostRequest,
)
from openapi_server.impl.tables import Report, ReportReason


class ModerationApiImpl(BaseModerationApi):
    async def reports_post(self, report_request: ReportRequest) -> Response:
        session = require_session()
        has_card = report_request.reported_card_id is not None
        has_player = report_request.reported_player_id is not None
        if has_card == has_player:
            raise ApiError(422, "EXACTLY_ONE_TARGET")
        if (
            report_request.room_code
            and report_request.room_code.upper() != session.room_code.upper()
        ):
            raise ApiError(403, "WRONG_ROOM")
        room = registry.get_by_code(session.room_code)
        if room is None:
            raise ApiError(404, "ROOM_NOT_FOUND")
        card_id = report_request.reported_card_id.hex if has_card else None
        player_id = report_request.reported_player_id.hex if has_player else None
        if has_card and (
            card_id not in room.cards
            or room.cards[card_id].status not in ("SUBMITTED", "SKIPPED", "ASSIGNED")
        ):
            raise ApiError(
                422, "VALIDATION_FAILED", "Reported card is not in this room"
            )
        if has_player and (
            player_id not in room.players or room.players[player_id].kicked
        ):
            raise ApiError(
                422, "VALIDATION_FAILED", "Reported player is not in this room"
            )
        try:
            reason = ReportReason(report_request.reason)
        except (TypeError, ValueError) as exc:
            raise ApiError(422, "VALIDATION_FAILED", "Invalid report reason") from exc

        report = Report(
            room_code=room.code,
            room_id=room.id,
            reporter_player_id=session.player_id,
            reported_card_id=card_id,
            reported_player_id=player_id,
            reason=reason,
            note=report_request.note,
        )
        await persist_room(room)
        await write(lambda db: db.add(report))
        return Response(status_code=202)

    async def rooms_room_code_votekick_post(
        self,
        roomCode: str,
        rooms_room_code_votekick_post_request: RoomsRoomCodeVotekickPostRequest,
    ) -> RoomsRoomCodeVotekickPost200Response:
        session = require_session()
        if session.room_code.upper() != roomCode.upper():
            raise ApiError(403, "WRONG_ROOM")
        room = registry.get_by_code(roomCode)
        if room is None:
            raise ApiError(404, "ROOM_NOT_FOUND")
        result = room.begin_votekick(
            session.player_id,
            rooms_room_code_votekick_post_request.target_player_id.hex,
            rooms_room_code_votekick_post_request.reason,
        )
        await persist_room(room)
        return RoomsRoomCodeVotekickPost200Response.model_validate(result)
