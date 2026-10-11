"""Validation shared by the HTTP handlers for names and author text."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Mapping

from openapi_server.impl.errors import ApiError

PRICE_WORDS = frozenset({"cheap", "expensive", "dollar", "bucks", "cost", "pricey"})
# English number words commonly used to encode a price without digits.
NUMBER_WORDS = frozenset(
    {
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
        "thirty",
        "forty",
        "fourty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
        "hundred",
        "thousand",
        "million",
        "billion",
        "trillion",
    }
)
CURRENCY_SYMBOLS = "$€£¥₹"
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def _word_set(words: Iterable[Any] | Mapping[str, Any] | None, kind: str) -> set[str]:
    if words is None:
        return set()
    if isinstance(words, Mapping):
        items = words.items()
        return {
            str(word).casefold()
            for word, word_kind in items
            if str(word_kind).casefold() == kind
        }
    result: set[str] = set()
    for item in words:
        if isinstance(item, Mapping):
            word, word_kind = item.get("word"), item.get("kind")
        else:
            word, word_kind = getattr(item, "word", None), getattr(item, "kind", None)
        if word and (word_kind is None or str(word_kind).casefold() == kind):
            result.add(str(word).casefold())
    return result


def _banned_words(
    supplied: Iterable[Any] | Mapping[str, Any] | None, kind: str
) -> set[str]:
    builtin = {"price_word": set(PRICE_WORDS), "number_word": set(NUMBER_WORDS)}.get(
        kind, set()
    )
    builtin.update(_word_set(supplied, kind))
    return builtin


def _text_errors(
    field: str, value: str, banned_words: Iterable[Any] | Mapping[str, Any] | None
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if any(char.isdigit() for char in value):
        errors.append(
            {
                "field": field,
                "rule": "DIGITS_REJECTED",
                "message": "Digits are not allowed.",
            }
        )
    if any(symbol in value for symbol in CURRENCY_SYMBOLS):
        errors.append(
            {
                "field": field,
                "rule": "CURRENCY_SYMBOL_REJECTED",
                "message": "Currency symbols are not allowed.",
            }
        )

    token_words = {match.group(0).casefold() for match in _WORD_RE.finditer(value)}
    for rule, kind in (
        ("NUMBER_WORD_REJECTED", "number_word"),
        ("PRICE_WORD_REJECTED", "price_word"),
        ("PROFANITY_REJECTED", "profanity"),
    ):
        banned = _banned_words(banned_words, kind)
        if not banned:
            continue
        found = sorted(token_words & banned)
        if found:
            word = found[0]
            errors.append(
                {
                    "field": field,
                    "rule": rule,
                    "message": f"The word '{word}' is not allowed.",
                }
            )
    return errors


def validate_display_name(
    name: str, banned_words: Iterable[Any] | Mapping[str, Any] | None = None
) -> list[dict[str, str]]:
    """Return fieldErrors for a display name (2–24 characters, profanity filtered)."""
    if not isinstance(name, str):
        return [
            {
                "field": "name",
                "rule": "VALIDATION_FAILED",
                "message": "Name must be text.",
            }
        ]
    errors: list[dict[str, str]] = []
    if len(name) < 2:
        errors.append(
            {
                "field": "name",
                "rule": "TOO_SHORT",
                "message": "Name must be at least 2 characters.",
            }
        )
    if len(name) > 24:
        errors.append(
            {
                "field": "name",
                "rule": "TOO_LONG",
                "message": "Name must be at most 24 characters.",
            }
        )
    errors.extend(
        error
        for error in _text_errors("name", name, banned_words)
        if error["rule"] == "PROFANITY_REJECTED"
    )
    return errors


def _get(submission: Any, key: str, alias: str | None = None) -> Any:
    if isinstance(submission, Mapping):
        return submission.get(key, submission.get(alias) if alias else None)
    return getattr(submission, key, getattr(submission, alias, None) if alias else None)


def validate_author_submission(
    submission: Any,
    active_categories: Iterable[Any] | Mapping[str, Any] | None = None,
    banned_words: Iterable[Any] | Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Validate the partial author-card fields; return contract-shaped fieldErrors."""
    errors: list[dict[str, str]] = []
    title = _get(submission, "title")
    if title is not None:
        if not isinstance(title, str):
            errors.append(
                {
                    "field": "title",
                    "rule": "TOO_SHORT",
                    "message": "Title must be text.",
                }
            )
        else:
            if len(title) < 8:
                errors.append(
                    {
                        "field": "title",
                        "rule": "TOO_SHORT",
                        "message": "Title must be at least 8 characters.",
                    }
                )
            if len(title) > 60:
                errors.append(
                    {
                        "field": "title",
                        "rule": "TOO_LONG",
                        "message": "Title must be at most 60 characters.",
                    }
                )
            errors.extend(_text_errors("title", title, banned_words))

    bullets = _get(submission, "bullets")
    if bullets is not None:
        if not isinstance(bullets, (list, tuple)) or len(bullets) > 3:
            errors.append(
                {
                    "field": "bullets",
                    "rule": "BULLET_COUNT",
                    "message": "Provide no more than 3 bullets.",
                }
            )
        else:
            for index, bullet in enumerate(bullets):
                field = f"bullets.{index}"
                if not isinstance(bullet, str):
                    errors.append(
                        {
                            "field": field,
                            "rule": "TOO_SHORT",
                            "message": "Bullet must be text.",
                        }
                    )
                    continue
                if len(bullet) < 15:
                    errors.append(
                        {
                            "field": field,
                            "rule": "TOO_SHORT",
                            "message": "Bullet must be at least 15 characters.",
                        }
                    )
                if len(bullet) > 80:
                    errors.append(
                        {
                            "field": field,
                            "rule": "TOO_LONG",
                            "message": "Bullet must be at most 80 characters.",
                        }
                    )
                errors.extend(_text_errors(field, bullet, banned_words))

    rating = _get(submission, "star_rating", "starRating")
    if rating is not None:
        try:
            numeric = Decimal(str(rating))
            if not numeric.is_finite() or numeric < 1 or numeric > 5:
                errors.append(
                    {
                        "field": "starRating",
                        "rule": "STAR_RATING_STEP",
                        "message": "Rating must be from 1.0 to 5.0.",
                    }
                )
            elif numeric * 2 != (numeric * 2).to_integral_value():
                errors.append(
                    {
                        "field": "starRating",
                        "rule": "STAR_RATING_STEP",
                        "message": "Rating must use 0.5 increments.",
                    }
                )
        except (InvalidOperation, ValueError):
            errors.append(
                {
                    "field": "starRating",
                    "rule": "STAR_RATING_STEP",
                    "message": "Rating must be numeric.",
                }
            )

    category = _get(submission, "category")
    if category is not None:
        if active_categories is None:
            try:
                from openapi_server.impl.content import load_categories

                active_categories = load_categories()
            except (ImportError, AttributeError, RuntimeError):
                active_categories = ()
        if isinstance(active_categories, Mapping):
            valid = {
                str(slug)
                for slug, entry in active_categories.items()
                if not isinstance(entry, Mapping) or entry.get("active", True)
            }
        else:
            valid = set()
            for entry in active_categories or ():
                if isinstance(entry, str):
                    valid.add(entry)
                elif isinstance(entry, Mapping):
                    if entry.get("active", True):
                        slug = entry.get("slug")
                        if slug is not None:
                            valid.add(str(slug))
                elif getattr(entry, "active", True):
                    slug = getattr(entry, "slug", None)
                    if slug is not None:
                        valid.add(str(slug))
        if category not in valid:
            errors.append(
                {
                    "field": "category",
                    "rule": "CATEGORY_UNKNOWN",
                    "message": "Select an active category.",
                }
            )
    return errors


def parse_money(value: Any) -> int:
    """Parse a numeric dollar amount (or integer cents) into integer cents.

    Numeric values are interpreted as dollars except integers, which represent
    the API's integer-cents values. Text accepts plain decimal/dollar notation.
    """
    if isinstance(value, bool):
        raise ApiError(422, "VALUE_NOT_NUMERIC", "Value must be numeric.")
    try:
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            raise InvalidOperation
        if text.startswith("$"):
            text = text[1:].strip()
        text = text.replace(",", "")
        amount = Decimal(text)
        if not amount.is_finite() or amount < 0:
            raise InvalidOperation
        return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        raise ApiError(422, "VALUE_NOT_NUMERIC", "Value must be numeric.") from None


parse_money_cents = parse_money
