from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import select

from openapi_server.impl.db import read, write
from openapi_server.impl.tables import BannedWord, Category

_DATA = Path(__file__).with_name("data")
_categories: list[Category] | None = None
_banned_words: list[BannedWord] | None = None


def _json(name: str):
    with (_DATA / name).open(encoding="utf-8") as source:
        return json.load(source)


async def seed_reference_data() -> None:
    categories = _json("categories.json")
    words = _json("banned_words.json")

    def seed(session):
        for data in categories:
            row = session.exec(
                select(Category).where(Category.slug == data["slug"])
            ).first()
            if row is None:
                session.add(Category(**data, sigma=0.5, active=True))
            else:
                row.display_name = data["display_name"]
        for data in words:
            row = session.exec(
                select(BannedWord).where(BannedWord.word == data["word"])
            ).first()
            if row is None:
                session.add(BannedWord(**data))
            else:
                row.kind = data["kind"]

    await write(seed)
    invalidate_content_cache()


def invalidate_content_cache() -> None:
    global _categories, _banned_words
    _categories = None
    _banned_words = None


async def load_categories(*, active_only: bool = False) -> list[Category]:
    global _categories
    if _categories is None:
        _categories = await read(
            lambda session: list(session.exec(select(Category)).all())
        )
    return (
        [item for item in _categories if item.active]
        if active_only
        else list(_categories)
    )


async def load_banned_words() -> list[BannedWord]:
    global _banned_words
    if _banned_words is None:
        _banned_words = await read(
            lambda session: list(session.exec(select(BannedWord)).all())
        )
    return list(_banned_words)
