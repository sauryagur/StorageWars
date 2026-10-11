from __future__ import annotations

from fastapi.responses import JSONResponse

from openapi_server.apis.author_api_base import BaseAuthorApi
from openapi_server.impl.engine.registry import registry
from openapi_server.impl.errors import ApiError, require_session
from openapi_server.impl.persistence import persist_room
from openapi_server.impl.products import sign_image_url
from openapi_server.impl.validation import validate_author_submission
from openapi_server.impl.views import author_card_stored, author_card_view


def _response(model, status_code: int) -> JSONResponse:
    return JSONResponse(
        model.model_dump(by_alias=True, exclude_unset=True, mode="json"),
        status_code=status_code,
    )


class AuthorApiImpl(BaseAuthorApi):
    async def games_current_author_card_get(self) -> JSONResponse:
        session = require_session()
        room = registry.get_by_code(session.room_code)
        if room.id != session.room_id:
            raise ApiError(403, "WRONG_ROOM")
        if room.phase.value != "AUTHOR":
            raise ApiError(409, "WRONG_PHASE", phase=room.phase.value)
        card = room.card_for_author(session.player_id)
        image_url = sign_image_url(
            card.product, room_id=room.id, player_id=session.player_id
        )
        return _response(
            author_card_view(
                card, image_url, card.product.price_band, deadline_at=room.deadline
            ),
            200,
        )

    async def games_current_author_card_put(
        self, author_card_submission
    ) -> JSONResponse:
        session = require_session()
        room = registry.get_by_code(session.room_code)
        if room.id != session.room_id:
            raise ApiError(403, "WRONG_ROOM")
        if room.phase.value != "AUTHOR":
            raise ApiError(409, "WRONG_PHASE", phase=room.phase.value)

        from openapi_server.impl.content import load_banned_words, load_categories

        field_errors = validate_author_submission(
            author_card_submission,
            active_categories=await load_categories(active_only=True),
            banned_words=await load_banned_words(),
        )
        if field_errors:
            raise ApiError(
                422,
                "VALIDATION_FAILED",
                "Author card validation failed.",
                field_errors=field_errors,
            )

        card = room.submit(
            session.player_id, author_card_submission.model_dump(exclude_unset=True)
        )
        await persist_room(room)
        return _response(author_card_stored(card), 200)
