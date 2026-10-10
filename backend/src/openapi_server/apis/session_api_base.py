# coding: utf-8

from typing import ClassVar, Dict, List, Tuple  # noqa: F401

from openapi_server.models.error import Error
from openapi_server.models.game_snapshot import GameSnapshot
from openapi_server.models.inline_object import InlineObject
from openapi_server.models.ws_ticket import WsTicket
from openapi_server.security_api import get_token_sessionToken

class BaseSessionApi:
    subclasses: ClassVar[Tuple] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        BaseSessionApi.subclasses = BaseSessionApi.subclasses + (cls,)
    async def ws_ticket_post(
        self,
    ) -> WsTicket:
        """Exchanges the long-lived session token (header) for a short-lived, single-use connection ticket for the AsyncAPI WebSocket. The session token itself never appears in a URL or query string. Tickets expire in 60 seconds and open exactly one connection. """
        ...


    async def games_current_snapshot_get(
        self,
    ) -> GameSnapshot:
        """THE recovery contract for reconnects and mid-game rejoins. Returns the absolute, per-phase, per-player redacted state: phase and deadlines, queue position and per-card statuses, the active card with its drip-redacted fields, the server-side draft value, lock states, current reveal slide index, and vote options. Redaction rules are identical to the per-resource GET endpoints. The client refetches this after any reconnect where it may have missed events; the WebSocket stream is a live view, this is the truth. """
        ...
