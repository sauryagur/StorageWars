# coding: utf-8

from typing import ClassVar, Dict, List, Tuple  # noqa: F401

from pydantic import Field, field_validator
from typing_extensions import Annotated
from openapi_server.models.error import Error
from openapi_server.models.inline_object1 import InlineObject1
from openapi_server.models.join_response import JoinResponse
from openapi_server.models.room_state import RoomState
from openapi_server.models.rooms_post_request import RoomsPostRequest
from openapi_server.models.rooms_room_code_join_post_request import RoomsRoomCodeJoinPostRequest
from openapi_server.models.rooms_room_code_start_post202_response import RoomsRoomCodeStartPost202Response
from openapi_server.security_api import get_token_sessionToken

class BaseRoomsApi:
    subclasses: ClassVar[Tuple] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        BaseRoomsApi.subclasses = BaseRoomsApi.subclasses + (cls,)
    async def rooms_post(
        self,
        rooms_post_request: RoomsPostRequest,
    ) -> JoinResponse:
        ...


    async def rooms_room_code_join_post(
        self,
        roomCode: Annotated[str, Field(min_length=4, max_length=4, description="4-character room code (convenience ID, not a secret).")],
        rooms_room_code_join_post_request: RoomsRoomCodeJoinPostRequest,
    ) -> JoinResponse:
        """Two distinct operations, discriminated by the request body:  * **New join:** requires &#x60;name&#x60;. Creates a new seat and a new   session token. Returns 409 if the game is in progress, the   room is full, or the name is taken. * **Rejoin:** requires &#x60;sessionToken&#x60; (an existing token from   this room). Resolves the existing seat BEFORE any new-join   prohibition applies — so rejoining during AUTHOR or GUESS is   explicitly permitted. &#x60;name&#x60; is optional and ignored.   Returns the same session token, plus the current phase so   the client can fetch a snapshot. Rejoin is permitted in   LOBBY, AUTHOR, GUESS, REVEAL, and VOTE; in FINAL the token   resolves but the room is read-only.  A failed room code is throttled per IP (429) to blunt enumeration of the 4-character code space. """
        ...


    async def rooms_room_code_get(
        self,
        roomCode: Annotated[str, Field(min_length=4, max_length=4, description="4-character room code (convenience ID, not a secret).")],
    ) -> RoomState:
        """Current phase and player list. The session token must belong to a seat in this room. Never contains game secrets or scores. """
        ...


    async def rooms_room_code_start_post(
        self,
        roomCode: Annotated[str, Field(min_length=4, max_length=4, description="4-character room code (convenience ID, not a secret).")],
    ) -> RoomsRoomCodeStartPost202Response:
        """Samples N distinct products — log-uniform by price, sampled WITHOUT replacement within the game, one per player — and moves the room to AUTHOR with a 60-second server timer. The (room, product) uniqueness invariant is enforced server-side. """
        ...
