# coding: utf-8

from typing import ClassVar, Dict, List, Tuple  # noqa: F401

from openapi_server.models.author_card_stored import AuthorCardStored
from openapi_server.models.author_card_submission import AuthorCardSubmission
from openapi_server.models.author_card_view import AuthorCardView
from openapi_server.models.author_validation_error import AuthorValidationError
from openapi_server.models.inline_object import InlineObject
from openapi_server.security_api import get_token_sessionToken

class BaseAuthorApi:
    subclasses: ClassVar[Tuple] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        BaseAuthorApi.subclasses = BaseAuthorApi.subclasses + (cls,)
    async def games_current_author_card_get(
        self,
    ) -> AuthorCardView:
        """Returns ONLY the product image and the coarse price band — never title, description, exact price, or review data. The image URL is signed and scoped to this player and the AUTHOR phase window. """
        ...


    async def games_current_author_card_put(
        self,
        author_card_submission: AuthorCardSubmission,
    ) -> AuthorCardStored:
        """Server-side validation: length rules, digit / number-word / currency-symbol / price-word rejection, profanity filter. Fields are individually optional to support the PRD&#39;s partial submission rule: filled fields are stored, the rest remain blank (null). An author who submits nothing before the 60s timeout is marked SKIPPED — that card is excluded from the queue, carousel, and votes, and scores no author points. Repeated PUTs before the deadline overwrite the stored card (last write wins); after the deadline the card is final. """
        ...
