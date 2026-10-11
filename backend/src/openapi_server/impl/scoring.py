"""Deterministic server-side money normalization and game scoring."""

from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping


def _round_half_up(value: float) -> int:
    """Round a non-negative score with ties going up (not Python's ties-even)."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def clamp_and_round(value_cents: int) -> tuple[int, bool, bool]:
    """Clamp slider value to $1–$1000 and round values >= $20 to dollars."""
    cents = max(100, min(100_000, int(value_cents)))
    was_clamped = cents != value_cents
    if cents >= 2_000:
        rounded = ((cents + 50) // 100) * 100
        return rounded, was_clamped, rounded != cents
    return cents, was_clamped, False


def format_money(cents: int) -> str:
    """Format cents with cents below $20 and whole dollars from $20 onward."""
    cents = int(cents)
    if cents < 2_000:
        return f"${cents // 100}.{cents % 100:02d}"
    return f"${(cents + 50) // 100}"


def multiplier(t: float) -> float:
    elapsed = max(0.0, min(20.0, float(t)))
    return 1.0 - 0.3 * elapsed / 20.0


def guess_points(guess_cents: int, price_cents: int, sigma: float, t: float) -> int:
    """Compute score from absolute log-price error and the elapsed-time factor."""
    guess, price, spread = float(guess_cents), float(price_cents), float(sigma)
    if guess <= 0 or price <= 0 or not math.isfinite(guess + price):
        raise ValueError("guess_cents and price_cents must be positive finite values")
    if spread <= 0 or not math.isfinite(spread):
        raise ValueError("sigma must be positive and finite")
    z = abs(math.log(guess / price)) / spread
    accuracy = max(0.0, 1.0 - z / 2.0)
    return _round_half_up(1_000 * accuracy * multiplier(t))


def author_points(accuracies: Iterable[float]) -> int:
    values = [float(value) for value in accuracies]
    if not values:
        return 0
    if any(not math.isfinite(value) for value in values):
        raise ValueError("accuracies must be finite")
    return _round_half_up(1_000 * sum(values) / len(values))


def funniest_bonus(votes_by_card: Mapping[Any, int]) -> dict[Any, int]:
    """Split 300 points only among cards tied for the unique nonzero top count."""
    bonuses = {card: 0 for card in votes_by_card}
    highest = max(votes_by_card.values(), default=0)
    if highest <= 0:
        return bonuses
    tied = [card for card, count in votes_by_card.items() if count == highest]
    if len(tied) == 1:
        bonuses[tied[0]] = 300
    else:
        share = _round_half_up(300 / len(tied))
        for card in tied:
            bonuses[card] = share
    return bonuses


def leaderboard(
    players: Iterable[Any], totals: Mapping[Any, int] | None = None
) -> tuple[list[dict[str, Any]], Any | None]:
    """Return competition-ranked rows and a unique winner ID, if one exists.

    ``players`` accepts IDs or mappings/objects with player_id (or playerId) and
    an optional total/points; ``totals`` overrides embedded totals.
    """
    entries: list[tuple[Any, int]] = []
    for player in players:
        if isinstance(player, Mapping):
            player_id = player.get(
                "player_id", player.get("playerId", player.get("id"))
            )
            score = player.get("total", player.get("points", 0))
        elif isinstance(player, (str, int)):
            player_id, score = player, 0
        else:
            player_id = getattr(
                player,
                "player_id",
                getattr(player, "playerId", getattr(player, "id", None)),
            )
            score = getattr(player, "total", getattr(player, "points", 0))
        if player_id is None:
            raise ValueError("each player must have an ID")
        if totals is not None:
            score = totals.get(player_id, 0)
        entries.append((player_id, int(score)))
    ordered = sorted(entries, key=lambda entry: -entry[1])
    rankings: list[dict[str, Any]] = []
    previous_score: int | None = None
    rank = 0
    for index, (player_id, score) in enumerate(ordered, 1):
        if score != previous_score:
            rank = index
            previous_score = score
        rankings.append({"playerId": player_id, "rank": rank, "totalPoints": score})
    winner = (
        ordered[0][0]
        if ordered and (len(ordered) == 1 or ordered[0][1] > ordered[1][1])
        else None
    )
    return rankings, winner
