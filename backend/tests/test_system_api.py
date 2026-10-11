import pytest

from openapi_server.impl.scoring import (
    author_points,
    clamp_and_round,
    format_money,
    funniest_bonus,
    guess_points,
    multiplier,
)
from openapi_server.impl.validation import (
    validate_author_submission,
    validate_display_name,
)


def test_health_is_served_under_versioned_prefix(client):
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert client.get("/health").status_code == 404


@pytest.mark.parametrize(
    "value,expected,clamped,rounded",
    [
        (99, 100, True, False),
        (100, 100, False, False),
        (100_000, 100_000, False, False),
        (100_001, 100_000, True, False),
        (1999, 1999, False, False),
        (2000, 2000, False, False),
        (2001, 2000, False, True),
    ],
)
def test_clamp_and_round_boundaries(value, expected, clamped, rounded):
    assert clamp_and_round(value) == (expected, clamped, rounded)


def test_money_format_multiplier_and_guess_scoring_boundaries():
    assert format_money(1999) == "$19.99"
    assert format_money(2000) == "$20"
    assert [multiplier(t) for t in (0, 10, 20, 25)] == [1.0, 0.85, 0.7, 0.7]
    assert guess_points(10_000, 10_000, 0.5, 0) == 1000
    assert guess_points(round(10_000 * __import__("math").exp(1)), 10_000, 0.5, 0) == 0
    assert guess_points(100_000, 10_000, 0.5, 0) == 0


def test_author_and_funniest_scoring_include_zero_and_split_ties():
    assert author_points([1.0, 0.5, 0.0]) == 500
    assert funniest_bonus({"a": 3, "b": 3, "c": 3, "d": 2}) == {
        "a": 100,
        "b": 100,
        "c": 100,
        "d": 0,
    }


def test_partial_author_validation_and_display_name_rules():
    assert (
        validate_author_submission(
            {"title": "Nice useful item", "category": "home"}, {"home"}
        )
        == []
    )
    errors = validate_author_submission(
        {"title": "Cheap item 123", "category": "missing"}, {"home"}
    )
    rules = {item["rule"] for item in errors}
    assert "DIGITS_REJECTED" in rules
    assert "PRICE_WORD_REJECTED" in rules
    assert "CATEGORY_UNKNOWN" in rules
    assert validate_display_name("A")
    assert validate_display_name("Player") == []
