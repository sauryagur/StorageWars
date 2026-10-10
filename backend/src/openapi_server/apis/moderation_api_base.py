# coding: utf-8

from typing import ClassVar, Dict, List, Tuple  # noqa: F401

from pydantic import Field, field_validator
from typing import Any
from typing_extensions import Annotated
from openapi_server.models.error import Error
from openapi_server.models.inline_object1 import InlineObject1
from openapi_server.models.report_request import ReportRequest
from openapi_server.models.rooms_room_code_votekick_post200_response import RoomsRoomCodeVotekickPost200Response
from openapi_server.models.rooms_room_code_votekick_post_request import RoomsRoomCodeVotekickPostRequest
from openapi_server.security_api import get_token_sessionToken

class BaseModerationApi:
    subclasses: ClassVar[Tuple] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        BaseModerationApi.subclasses = BaseModerationApi.subclasses + (cls,)
    async def reports_post(
        self,
        report_request: ReportRequest,
    ) -> None:
        """For offensive content or AFK only. Exactly one of reportedCardId / reportedPlayerId must be present, and the target must belong to the reporter&#39;s room. Reports never carry game secrets to moderators before the reveal. """
        ...


    async def rooms_room_code_votekick_post(
        self,
        roomCode: Annotated[str, Field(min_length=4, max_length=4, description="4-character room code (convenience ID, not a secret).")],
        rooms_room_code_votekick_post_request: RoomsRoomCodeVotekickPostRequest,
    ) -> RoomsRoomCodeVotekickPost200Response:
        """Reasons are offensive content or AFK only — NOT cheating accusations (per PRD). Semantics:  * Exactly one ACTIVE votekick per room; the active vote must   resolve or expire before a different target can be raised   (409 VOTEKICK_IN_PROGRESS). * One vote per player per votekick. Duplicate calls are   idempotent: they return the current tally and emit no event. * Threshold: ceil(2/3 of OTHER players), evaluated on each   new vote; the kick executes when reached. * The votekick expires after 30s without reaching threshold. * A kicked player&#39;s card and guesses are removed from   everyone&#39;s totals; their vote is discarded, and votes cast   for their card are discarded. Scoring is prior-based, so   removal requires no crowd recomputation. * If fewer than 4 players remain, the game ends early:   phase moves to FINAL with endedReason TOO_FEW_PLAYERS and   the completed cards. * If the target disconnects before resolution, the votekick   is CANCELLED (no kick; disconnect rules apply instead). """
        ...
