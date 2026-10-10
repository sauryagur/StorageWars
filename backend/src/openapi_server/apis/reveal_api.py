# coding: utf-8

from typing import Dict, List  # noqa: F401
import importlib
import pkgutil

from openapi_server.apis.reveal_api_base import BaseRevealApi
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
from openapi_server.models.error import Error
from openapi_server.models.inline_object import InlineObject
from openapi_server.models.reveal_slide import RevealSlide
from openapi_server.models.extra_models import TokenModel  # noqa: F401
from openapi_server.security_api import get_token_sessionToken

router = APIRouter()

ns_pkg = openapi_server.impl
for _, name, _ in pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + "."):
    importlib.import_module(name)


@router.get(
    "/games/current/reveal",
    responses={
        200: {"model": RevealSlide, "description": "Current slide."},
        409: {"model": InlineObject, "description": "Operation not valid for the current phase."},
    },
    tags=["Reveal"],
    summary="Current reveal slide",
    response_model_by_alias=True,
)
async def games_current_reveal_get(
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> RevealSlide:
    """Shared carousel over the SUBMITTED cards, shuffled order, ~12s per slide, auto-advancing; the creator can advance early. This is the only pre-FINAL context in which product secrets (image, original title/description, true price) are released. Slides carry NO points — scores appear only on the final scoreboard (this resolves the PRD&#39;s internal contradiction in favor of hidden scores). """
    if not BaseRevealApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseRevealApi.subclasses[0]().games_current_reveal_get()


@router.post(
    "/games/current/reveal/advance",
    responses={
        202: {"description": "Advanced."},
        403: {"model": Error, "description": "Not the room creator, token not bound to this room (WRONG_ROOM), or action forbidden for this seat. "},
        409: {"model": InlineObject, "description": "Operation not valid for the current phase."},
    },
    tags=["Reveal"],
    summary="Advance the carousel early (creator only)",
    response_model_by_alias=True,
)
async def games_current_reveal_advance_post(
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> None:
    if not BaseRevealApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseRevealApi.subclasses[0]().games_current_reveal_advance_post()
