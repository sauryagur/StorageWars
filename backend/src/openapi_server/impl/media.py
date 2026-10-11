from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from sqlmodel import select

from openapi_server.impl.config import settings
from openapi_server.impl.db import read
from openapi_server.impl.products import verify_image_url
from openapi_server.impl.storage import content_type_for, get_storage
from openapi_server.impl.tables import ProductImage


async def media_route(
    key: str, exp: int, sig: str, roomId: str, playerId: str | None = None
):
    if not verify_image_url(key, exp, sig, roomId, playerId):
        raise HTTPException(status_code=403)
    image = await read(
        lambda session: session.exec(
            select(ProductImage).where(ProductImage.storage_key == key)
        ).first()
    )
    if image is None:
        raise HTTPException(status_code=404)
    storage = get_storage(settings)
    headers = {"Cache-Control": "private, max-age=60"}
    signed = storage.presigned_url(key)
    if signed is not None:
        # Redirect to the object store: the bucket stays private, the redirect
        # signature outlives only this request, and the bytes never transit the
        # API. Scope still comes from the HMAC checked above.
        return RedirectResponse(signed, status_code=307, headers=headers)
    path = storage.local_path(key)
    if path is None:
        raise HTTPException(status_code=404)
    return FileResponse(
        path, media_type=content_type_for(key), headers=headers
    )
