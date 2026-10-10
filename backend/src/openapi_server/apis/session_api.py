# coding: utf-8

from typing import Dict, List  # noqa: F401
import importlib
import pkgutil

from openapi_server.apis.session_api_base import BaseSessionApi
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

from openapi_server.models.error import Error
from openapi_server.models.game_snapshot import GameSnapshot
from openapi_server.models.inline_object import InlineObject
from openapi_server.models.ws_ticket import WsTicket
from openapi_server.models.extra_models import TokenModel  # noqa: F401
from openapi_server.security_api import get_token_sessionToken

router = APIRouter()

ns_pkg = openapi_server.impl
for _, name, _ in pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + "."):
    importlib.import_module(name)


@router.post(
    "/ws/ticket",
    responses={
        201: {"model": WsTicket, "description": "Ticket minted."},
        429: {"model": Error, "description": "Ticket minting rate-limited (per session)."},
    },
    tags=["Session"],
    summary="Mint a single-use WebSocket ticket",
    response_model_by_alias=True,
)
async def ws_ticket_post(
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> WsTicket:
    """Exchanges the long-lived session token (header) for a short-lived, single-use connection ticket for the AsyncAPI WebSocket. The session token itself never appears in a URL or query string. Tickets expire in 60 seconds and open exactly one connection. """
    if not BaseSessionApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseSessionApi.subclasses[0]().ws_ticket_post()


@router.get(
    "/games/current/snapshot",
    responses={
        200: {"model": GameSnapshot, "description": "Snapshot."},
        409: {"model": InlineObject, "description": "Operation not valid for the current phase."},
    },
    tags=["Session"],
    summary="Authoritative per-player state snapshot",
    response_model_by_alias=True,
)
async def games_current_snapshot_get(
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> GameSnapshot:
    """THE recovery contract for reconnects and mid-game rejoins. Returns the absolute, per-phase, per-player redacted state: phase and deadlines, queue position and per-card statuses, the active card with its drip-redacted fields, the server-side draft value, lock states, current reveal slide index, and vote options. Redaction rules are identical to the per-resource GET endpoints. The client refetches this after any reconnect where it may have missed events; the WebSocket stream is a live view, this is the truth. """
    if not BaseSessionApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseSessionApi.subclasses[0]().games_current_snapshot_get()
