# coding: utf-8

from typing import Dict, List  # noqa: F401
import importlib
import pkgutil

from openapi_server.apis.author_api_base import BaseAuthorApi
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

from openapi_server.models.author_card_stored import AuthorCardStored
from openapi_server.models.author_card_submission import AuthorCardSubmission
from openapi_server.models.author_card_view import AuthorCardView
from openapi_server.models.author_validation_error import AuthorValidationError
from openapi_server.models.inline_object import InlineObject
from openapi_server.models.extra_models import TokenModel  # noqa: F401
from openapi_server.security_api import get_token_sessionToken

router = APIRouter()

ns_pkg = openapi_server.impl
for _, name, _ in pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + "."):
    importlib.import_module(name)


@router.get(
    "/games/current/author-card",
    responses={
        200: {"model": AuthorCardView, "description": "Author card view."},
        409: {"model": InlineObject, "description": "Operation not valid for the current phase."},
    },
    tags=["Author"],
    summary="Get my card to author",
    response_model_by_alias=True,
)
async def games_current_author_card_get(
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> AuthorCardView:
    """Returns ONLY the product image and the coarse price band — never title, description, exact price, or review data. The image URL is signed and scoped to this player and the AUTHOR phase window. """
    if not BaseAuthorApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseAuthorApi.subclasses[0]().games_current_author_card_get()


@router.put(
    "/games/current/author-card",
    responses={
        200: {"model": AuthorCardStored, "description": "Card stored (fully or partially)."},
        409: {"model": InlineObject, "description": "Operation not valid for the current phase."},
        422: {"model": AuthorValidationError, "description": "Validation failure. &#x60;fieldErrors&#x60; is field-level for live inline display; each entry names the rule and, for word-list rules, the offending word. "},
    },
    tags=["Author"],
    summary="Submit my authored card (full or partial)",
    response_model_by_alias=True,
)
async def games_current_author_card_put(
    author_card_submission: AuthorCardSubmission = Body(..., description=""),
    token_sessionToken: TokenModel = Security(
        get_token_sessionToken
    ),
) -> AuthorCardStored:
    """Server-side validation: length rules, digit / number-word / currency-symbol / price-word rejection, profanity filter. Fields are individually optional to support the PRD&#39;s partial submission rule: filled fields are stored, the rest remain blank (null). An author who submits nothing before the 60s timeout is marked SKIPPED — that card is excluded from the queue, carousel, and votes, and scores no author points. Repeated PUTs before the deadline overwrite the stored card (last write wins); after the deadline the card is final. """
    if not BaseAuthorApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseAuthorApi.subclasses[0]().games_current_author_card_put(author_card_submission)
