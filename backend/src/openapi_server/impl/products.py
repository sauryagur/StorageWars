from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from random import Random

from sqlalchemy.orm import selectinload
from sqlmodel import select

from openapi_server.impl.config import settings
from openapi_server.impl.db import read
from openapi_server.impl.tables import Product


async def sample_products(
    n: int, rng: Random, used_ids: set[int] | None = None
) -> list[Product]:
    used_ids = used_ids or set()
    products = await read(
        lambda session: list(
            session.exec(
                select(Product)
                .where(Product.active)
                .options(selectinload(Product.image), selectinload(Product.category))
            ).all()
        )
    )
    pool = [
        item for item in products if item.id is not None and item.id not in used_ids
    ]
    if len(pool) < n:
        raise ValueError("not enough distinct active products")
    # Weighted sampling without replacement; inverse-price weighting approximates
    # a uniform distribution in log-price space while preserving the product pool.
    keys = []
    for product in pool:
        weight = 1.0 / max(product.price_cents, 1)
        key = rng.random() ** (1.0 / weight)
        keys.append((key, product))
    keys.sort(key=lambda row: row[0], reverse=True)
    return [product for _, product in keys[:n]]


def sign_image_url(
    product: Product, *, room_id: str, player_id: str | None = None
) -> str:
    exp = int(time.time()) + settings.image_url_ttl_seconds
    key = product.image.storage_key
    signature = hmac.new(
        settings.image_url_secret.encode(),
        f"{key}|{exp}|{room_id}|{player_id or ''}".encode(),
        hashlib.sha256,
    ).hexdigest()
    from urllib.parse import quote

    room = quote(room_id, safe="")
    player = quote(player_id or "", safe="")
    return (
        f"{settings.public_base_url}/media/products/{quote(key, safe='/')}"
        f"?exp={exp}&sig={signature}&roomId={room}&playerId={player}"
    )


def verify_image_url(
    key: str, exp: int, sig: str, room_id: str, player_id: str | None = None
) -> bool:
    if exp < int(time.time()):
        return False
    expected = hmac.new(
        settings.image_url_secret.encode(),
        f"{key}|{exp}|{room_id}|{player_id or ''}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return secrets.compare_digest(expected, sig)
