from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlmodel import select

from openapi_server.impl.config import settings
from openapi_server.impl.db import read
from openapi_server.impl.products import verify_image_url
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
    root = Path(settings.media_root).resolve()
    path = (root / key).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404)
    suffix = path.suffix.lower()
    content_type = {
        ".webp": "image/webp",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix, "application/octet-stream")
    return FileResponse(
        path, media_type=content_type, headers={"Cache-Control": "private, max-age=60"}
    )
