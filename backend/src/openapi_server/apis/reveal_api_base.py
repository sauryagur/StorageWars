# coding: utf-8

from typing import ClassVar, Dict, List, Tuple  # noqa: F401

from typing import Any
from openapi_server.models.error import Error
from openapi_server.models.inline_object import InlineObject
from openapi_server.models.reveal_slide import RevealSlide
from openapi_server.security_api import get_token_sessionToken

class BaseRevealApi:
    subclasses: ClassVar[Tuple] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        BaseRevealApi.subclasses = BaseRevealApi.subclasses + (cls,)
    async def games_current_reveal_get(
        self,
    ) -> RevealSlide:
        """Shared carousel over the SUBMITTED cards, shuffled order, ~12s per slide, auto-advancing; the creator can advance early. This is the only pre-FINAL context in which product secrets (image, original title/description, true price) are released. Slides carry NO points — scores appear only on the final scoreboard (this resolves the PRD&#39;s internal contradiction in favor of hidden scores). """
        ...


    async def games_current_reveal_advance_post(
        self,
    ) -> None:
        ...
