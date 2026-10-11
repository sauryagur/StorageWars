from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from openapi_server.impl.clock import Clock, get_clock
from openapi_server.impl.config import settings
from openapi_server.impl.engine.events import EventBus
from openapi_server.impl.errors import ApiError
from openapi_server.impl.scoring import (
    author_points,
    clamp_and_round,
    funniest_bonus,
    guess_points,
    multiplier,
)
from openapi_server.impl.tables import Phase


@dataclass
class Player:
    id: str
    name: str
    token_hash: str = ""
    creator: bool = False
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    connected: bool = True
    disconnected_at: datetime | None = None
    kicked: bool = False
    kick_reason: str | None = None


@dataclass
class Guess:
    player_id: str
    value_cents: int | None = None
    draft_present: bool = False
    slider_touched: bool = False
    opened_at: datetime | None = None
    cap_at: datetime | None = None
    lock_eligible_at: datetime | None = None
    drip_bullets_at: datetime | None = None
    drip_rating_at: datetime | None = None
    drip_bullets_emitted: bool = False
    drip_rating_emitted: bool = False
    locked_at: datetime | None = None
    card_seconds: float = 0
    multiplier: float = 1
    points: int = 0
    accuracy: float = 0
    z: float = 0
    timed_out: bool = False
    status: str = "QUEUED"


@dataclass
class Card:
    id: str
    author_id: str
    product: Any
    status: str = "ASSIGNED"
    title: str | None = None
    bullets: list[str] | None = None
    star_rating: float | None = None
    review_bucket: str | None = None
    category: str | None = None
    submitted_at: datetime | None = None
    guesses: dict[str, Guess] = field(default_factory=dict)
    author_points: int = 0
    funniest_bonus: int = 0
    funniest_votes: int = 0


@dataclass
class Votekick:
    target_id: str
    reason: str
    expires_at: datetime
    votes: set[str] = field(default_factory=set)


class RoomEngine:
    def __init__(
        self,
        name: str = "",
        *,
        room_id: str | None = None,
        code: str = "",
        creator: Player | None = None,
        clock: Clock | None = None,
        rng: random.Random | None = None,
        replay_of_room_id: str | None = None,
    ):
        self.id = room_id or uuid4().hex
        self.code = code
        self.name = name
        self.clock = clock or get_clock()
        self.rng = rng or random.Random()
        self.phase = Phase.LOBBY
        self.players: dict[str, Player] = {}
        if creator:
            self.players[creator.id] = creator
        self.creator_player_id = creator.id if creator else None
        self.cards: dict[str, Card] = {}
        self.deadline: datetime | None = None
        self.created_at = self.clock.now()
        self.ttl_expires_at = self.created_at + timedelta(
            seconds=settings.room_ttl_seconds
        )
        self.replay_of_room_id = replay_of_room_id
        self.end_reason: str | None = None
        self.reveal_order: list[str] = []
        self.reveal_index = 0
        self.vote_deadline: datetime | None = None
        self.votes: dict[str, str] = {}
        self.votekick: Votekick | None = None
        self.queues: dict[str, list[str]] = {}
        self.active_cards: dict[str, str] = {}
        self.event_bus = EventBus(self.id, self.clock, settings.progress_coalesce_ms)
        self.immutable = False
        self.seat_claim_expires_at: datetime | None = None
        self.claim_token_hashes: dict[str, str] = {}
        self._timer_task: asyncio.Task | None = None
        self._rejoin_expiry: dict[str, datetime] = {}

    @property
    def seats(self) -> list[Player]:
        return [p for p in self.players.values() if not p.kicked]

    def add_player(
        self, name: str, player_id: str | None = None, *, token_hash: str = ""
    ) -> Player:
        if self.phase != Phase.LOBBY:
            raise ApiError(409, "GAME_IN_PROGRESS")
        if len(self.seats) >= 8:
            raise ApiError(409, "ROOM_FULL")
        if any(p.name.casefold() == name.casefold() for p in self.seats):
            raise ApiError(409, "NAME_TAKEN")
        player = Player(
            player_id or uuid4().hex, name, token_hash, joined_at=self.clock.now()
        )
        self.players[player.id] = player
        return player

    def start(self, products: list[Any], caller_id: str) -> None:
        if caller_id != self.creator_player_id:
            raise ApiError(403, "NOT_CREATOR")
        if self.phase != Phase.LOBBY:
            raise ApiError(409, "GAME_IN_PROGRESS")
        if not 4 <= len(self.seats) <= 8:
            raise ApiError(
                409, "VALIDATION_FAILED", "A room needs 4–8 players to start."
            )
        if len(products) != len(self.seats):
            raise ValueError("one distinct product per seated player is required")
        for player, product in zip(self.seats, products):
            card = Card(uuid4().hex, player.id, product)
            self.cards[card.id] = card
        self._enter_phase(Phase.AUTHOR, settings.author_seconds)

    def submit(self, player_id: str, data: dict[str, Any]) -> Card:
        self._require_phase(Phase.AUTHOR)
        card = self.card_for_author(player_id)
        if card.status == "SKIPPED":
            raise ApiError(409, "WRONG_PHASE")
        for key in ("title", "bullets", "star_rating", "review_bucket", "category"):
            if key in data:
                setattr(card, key, data[key])
        card.status = "SUBMITTED"
        card.submitted_at = self.clock.now()
        self.event_bus.coalesce(
            "author",
            "author_progress",
            {
                "submitted": sum(c.status == "SUBMITTED" for c in self.cards.values()),
                "total": len(self.cards),
            },
        )
        if all(c.status != "ASSIGNED" for c in self.cards.values()):
            self._enter_guess()
        return card

    def card_for_author(self, player_id: str) -> Card:
        card = next((c for c in self.cards.values() if c.author_id == player_id), None)
        if card is None:
            raise ApiError(404, "NOT_IN_QUEUE")
        return card

    def _enter_guess(self) -> None:
        submitted = [card for card in self.cards.values() if card.status == "SUBMITTED"]
        if not submitted:
            self.event_bus.publish_room("game_over", {"endedReason": "ABANDONED"})
            self.end_reason = "COMPLETED"
            self._enter_phase(Phase.FINAL)
            return
        for player in self.seats:
            ids = [c.id for c in submitted if c.author_id != player.id]
            random.Random(f"{self.id}:{player.id}").shuffle(ids)
            self.queues[player.id] = ids
            for card in submitted:
                if card.author_id != player.id:
                    card.guesses[player.id] = Guess(player.id)
        self._enter_phase(Phase.GUESS)
        if not any(self.queues.values()):
            self._enter_reveal()

    def queue_for(self, player_id: str) -> list[str]:
        if player_id not in self.queues:
            raise ApiError(409, "WRONG_PHASE", phase=self.phase.value)
        return list(self.queues[player_id])

    def open(self, player_id: str, card_id: str) -> Guess:
        self._require_phase(Phase.GUESS)
        queue = self.queues.get(player_id, [])
        if card_id not in queue:
            raise ApiError(404, "NOT_IN_QUEUE")
        active = self.active_cards.get(player_id)
        guess = self.cards[card_id].guesses[player_id]
        if guess.status == "IN_PROGRESS" and active == card_id:
            return guess
        if guess.status in ("LOCKED", "AUTO_LOCKED", "SCORED_ZERO"):
            raise ApiError(409, "ALREADY_LOCKED")
        expected = next(
            (
                cid
                for cid in queue
                if self.cards[cid].guesses[player_id].status
                in ("QUEUED", "IN_PROGRESS")
            ),
            None,
        )
        if active is not None:
            raise ApiError(409, "CARD_ACTIVE")
        if card_id != expected:
            raise ApiError(409, "NOT_NEXT_CARD")
        now = self.clock.now()
        guess.status = "IN_PROGRESS"
        guess.opened_at = now
        guess.cap_at = now + timedelta(seconds=settings.card_cap_seconds)
        guess.lock_eligible_at = now + timedelta(seconds=settings.min_dwell_seconds)
        self.active_cards[player_id] = card_id
        guess.drip_bullets_at = now + timedelta(seconds=settings.drip_bullets_seconds)
        guess.drip_rating_at = now + timedelta(seconds=settings.drip_rating_seconds)
        self.start_timers()
        return guess

    def draft(
        self, player_id: str, card_id: str, value: int
    ) -> tuple[Guess, bool, bool]:
        self._require_phase(Phase.GUESS)
        guess = self._guess(player_id, card_id)
        if guess.status != "IN_PROGRESS":
            raise ApiError(409, "CARD_ACTIVE")
        cents, clamped, rounded = clamp_and_round(value)
        guess.value_cents = cents
        guess.draft_present = True
        return guess, clamped, rounded

    def touch(self, player_id: str, card_id: str) -> None:
        self._require_phase(Phase.GUESS)
        guess = self._guess(player_id, card_id)
        if guess.status != "IN_PROGRESS":
            raise ApiError(409, "WRONG_PHASE")
        guess.slider_touched = True

    def lock(
        self,
        player_id: str,
        card_id: str,
        value: int | None = None,
        *,
        timed_out: bool = False,
    ) -> Guess:
        self._require_phase(Phase.GUESS)
        guess = self._guess(player_id, card_id)
        if guess.status != "IN_PROGRESS":
            raise ApiError(
                403 if guess.status == "LOCKED" else 409,
                "ALREADY_LOCKED" if guess.status == "LOCKED" else "WRONG_PHASE",
            )
        if timed_out:
            if guess.draft_present and guess.slider_touched:
                self._score_guess(guess, self.cards[card_id], timed_out=True)
                guess.status = "AUTO_LOCKED"
            else:
                guess.value_cents = None
                guess.points = 0
                guess.accuracy = 0
                guess.status = "SCORED_ZERO"
                guess.timed_out = True
                guess.locked_at = self.clock.now()
            self.active_cards.pop(player_id, None)
            self._maybe_enter_reveal()
            self.event_bus.coalesce(
                "guess",
                "guess_progress",
                {
                    "locked": sum(
                        g.status in ("LOCKED", "AUTO_LOCKED", "SCORED_ZERO", "SKIPPED")
                        for card in self.cards.values()
                        for g in card.guesses.values()
                    ),
                    "total": sum(len(queue) for queue in self.queues.values()),
                },
            )
            if self.phase == Phase.GUESS:
                self.start_timers()
            return guess
        if not guess.slider_touched:
            raise ApiError(403, "SLIDER_UNTOUCHED")
        now = self.clock.now()
        if guess.lock_eligible_at and now < guess.lock_eligible_at:
            raise ApiError(403, "LOCK_TOO_EARLY")
        if value is not None:
            guess.value_cents = clamp_and_round(value)[0]
            guess.draft_present = True
        if guess.value_cents is None:
            raise ApiError(422, "VALUE_NOT_NUMERIC")
        self._score_guess(guess, self.cards[card_id])
        guess.status = "LOCKED"
        self.active_cards.pop(player_id, None)
        self.event_bus.publish_player(
            player_id,
            "lock_confirmed",
            {
                "cardId": card_id,
                "lockedAt": guess.locked_at.isoformat(),
                "points": None,
            },
        )
        self._maybe_enter_reveal()
        self.event_bus.coalesce(
            "guess",
            "guess_progress",
            {
                "locked": sum(
                    g.status in ("LOCKED", "AUTO_LOCKED", "SCORED_ZERO", "SKIPPED")
                    for card in self.cards.values()
                    for g in card.guesses.values()
                ),
                "total": sum(len(queue) for queue in self.queues.values()),
            },
        )
        if self.phase == Phase.GUESS:
            self.start_timers()
        return guess

    def _score_guess(
        self, guess: Guess, card: Card, *, timed_out: bool = False
    ) -> None:
        now = self.clock.now()
        guess.locked_at = now
        elapsed = (
            min(
                settings.card_cap_seconds,
                max(0.0, (now - guess.opened_at).total_seconds()),
            )
            if guess.opened_at
            else 0.0
        )
        guess.card_seconds = elapsed
        guess.multiplier = multiplier(elapsed)
        guess.timed_out = timed_out
        if guess.value_cents is None:
            guess.points = 0
            guess.accuracy = 0
            return
        price = card.product.price_cents
        category = getattr(card.product, "category", None)
        sigma = getattr(category, "sigma", 0.5) if category else 0.5
        z = abs(math.log(guess.value_cents / price)) / sigma
        guess.z = z
        guess.accuracy = max(0.0, 1.0 - z / 2.0)
        guess.points = guess_points(guess.value_cents, price, sigma, elapsed)

    def _guess(self, player_id: str, card_id: str) -> Guess:
        if card_id not in self.queues.get(player_id, []):
            raise ApiError(404, "NOT_IN_QUEUE")
        return self.cards[card_id].guesses[player_id]

    def _maybe_enter_reveal(self) -> None:
        if self.phase != Phase.GUESS:
            return
        if all(
            all(
                self.cards[cid].guesses[p.id].status
                in ("LOCKED", "AUTO_LOCKED", "SCORED_ZERO", "SKIPPED")
                for cid in self.queues[p.id]
            )
            for p in self.seats
        ):
            self.event_bus.publish_room("all_guessers_done", {})
            self._enter_reveal()

    def _skip_player_queue(self, player_id: str) -> None:
        for card_id in self.queues.get(player_id, []):
            guess = self.cards[card_id].guesses[player_id]
            if guess.status in ("QUEUED", "IN_PROGRESS"):
                guess.status = "SKIPPED"
                guess.timed_out = True
        self.active_cards.pop(player_id, None)

    def _enter_reveal(self) -> None:
        self.reveal_order = [
            c.id for c in self.cards.values() if c.status == "SUBMITTED"
        ]
        random.Random(self.id).shuffle(self.reveal_order)
        self.reveal_index = 0
        self._calculate_author_scores()
        self._enter_phase(Phase.REVEAL, settings.slide_seconds)

    def _calculate_author_scores(self) -> None:
        for card in self.cards.values():
            if card.status != "SUBMITTED":
                continue
            eligible = [
                g.accuracy
                for g in card.guesses.values()
                if not self.players[g.player_id].kicked
            ]
            card.author_points = author_points(eligible)
        counts = {
            card.id: sum(1 for cid in self.votes.values() if cid == card.id)
            for card in self.cards.values()
        }
        bonuses = funniest_bonus(counts)
        for card in self.cards.values():
            card.funniest_votes = counts.get(card.id, 0)
            card.funniest_bonus = bonuses.get(card.id, 0)

    def advance_reveal(self, player_id: str) -> None:
        self._require_phase(Phase.REVEAL)
        if player_id != self.creator_player_id:
            raise ApiError(403, "NOT_CREATOR")
        self.reveal_index += 1
        self._advance_slide_or_vote()

    def vote_options(self, player_id: str) -> list[str]:
        self._require_phase(Phase.VOTE)
        return [
            cid for cid in self.reveal_order if self.cards[cid].author_id != player_id
        ]

    def vote(self, player_id: str, card_id: str) -> None:
        self._require_phase(Phase.VOTE)
        if player_id in self.votes:
            raise ApiError(409, "ALREADY_VOTED")
        card = self.cards.get(card_id)
        if card is None or card.status != "SUBMITTED":
            raise ApiError(404, "NOT_IN_QUEUE")
        if card.author_id == player_id:
            raise ApiError(403, "OWN_CARD_FORBIDDEN")
        self.votes[player_id] = card_id
        self.event_bus.coalesce(
            "vote",
            "vote_progress",
            {"votesCast": len(self.votes), "total": len(self.seats)},
        )
        if all(
            p.id in self.votes or len(self.vote_options(p.id)) == 0 for p in self.seats
        ):
            self._enter_final()

    def _enter_final(self) -> None:
        self._calculate_author_scores()
        self._enter_phase(Phase.FINAL)

    def _advance_slide_or_vote(self) -> None:
        if self.reveal_index >= len(self.reveal_order):
            self._enter_phase(Phase.VOTE, settings.vote_seconds)
            self.vote_deadline = self.deadline
        else:
            self.deadline = self.clock.now() + timedelta(seconds=settings.slide_seconds)
            self.event_bus.publish_room(
                "slide_changed",
                {
                    "index": self.reveal_index,
                    "cardId": self.reveal_order[self.reveal_index],
                    "deadlineAt": self.deadline.isoformat(),
                },
            )
            self.start_timers()

    def next_deadline(self) -> datetime | None:
        deadlines = [
            self.deadline,
            self.votekick.expires_at if self.votekick else None,
            self.seat_claim_expires_at,
        ]
        deadlines.extend(self._rejoin_expiry.values())
        if self.phase == Phase.GUESS:
            for card_id, guesser_id in (
                (card_id, player_id) for player_id, card_id in self.active_cards.items()
            ):
                guess = self.cards[card_id].guesses[guesser_id]
                if guess.cap_at is not None:
                    deadlines.append(guess.cap_at)
                if guess.drip_bullets_at is not None and not guess.drip_bullets_emitted:
                    deadlines.append(guess.drip_bullets_at)
                if guess.drip_rating_at is not None and not guess.drip_rating_emitted:
                    deadlines.append(guess.drip_rating_at)
        return min((item for item in deadlines if item is not None), default=None)

    def start_timers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        current = asyncio.current_task()
        if self._timer_task is current:
            return
        if self._timer_task is not None and not self._timer_task.done():
            self._timer_task.cancel()
        self._timer_task = loop.create_task(self._timer_loop())

    async def _timer_loop(self) -> None:
        while self.phase not in (Phase.FINAL, Phase.CLOSED):
            deadline = self.next_deadline()
            if deadline is None:
                return
            await self.clock.sleep_until(deadline)
            await self.tick()

    def stop_timers(self) -> None:
        if self._timer_task is not None:
            self._timer_task.cancel()
            self._timer_task = None

    def async_tick(self) -> None:
        """Apply due timers, driven by tests or the production room task."""
        now = self.clock.now()
        if self.seat_claim_expires_at and now >= self.seat_claim_expires_at:
            from openapi_server.impl.engine.registry import registry

            registry.sweep()
        if self.votekick and now >= self.votekick.expires_at:
            self.event_bus.publish_room("votekick_resolved", {"result": "EXPIRED"})
            self.votekick = None
        for player_id, expiry in tuple(self._rejoin_expiry.items()):
            if now >= expiry:
                from openapi_server.impl.engine.registry import registry

                registry.expire_seat(player_id)
        if self.phase == Phase.AUTHOR and self.deadline and now >= self.deadline:
            for card in self.cards.values():
                if card.status == "ASSIGNED":
                    card.status = "SKIPPED"
            self._enter_guess()
        elif self.phase == Phase.GUESS:
            for player_id, card_id in tuple(self.active_cards.items()):
                card = self.cards[card_id]
                guess = card.guesses[player_id]
                if (
                    guess.drip_bullets_at
                    and now >= guess.drip_bullets_at
                    and not guess.drip_bullets_emitted
                ):
                    self.event_bus.publish_player(
                        player_id,
                        "drip_revealed",
                        {"cardId": card_id, "stage": "BULLETS"},
                    )
                    guess.drip_bullets_emitted = True
                if (
                    guess.drip_rating_at
                    and now >= guess.drip_rating_at
                    and not guess.drip_rating_emitted
                ):
                    self.event_bus.publish_player(
                        player_id,
                        "drip_revealed",
                        {"cardId": card_id, "stage": "RATING"},
                    )
                    guess.drip_rating_emitted = True
                if guess.cap_at and now >= guess.cap_at:
                    self.lock(player_id, card_id, timed_out=True)
                    self.event_bus.publish_room(
                        "card_capped",
                        {
                            "cardId": card_id,
                            "playerId": player_id,
                            "status": (
                                "AUTO_LOCKED"
                                if guess.status == "AUTO_LOCKED"
                                else "SCORED_ZERO"
                            ),
                        },
                    )
        elif self.phase == Phase.REVEAL and self.deadline and now >= self.deadline:
            self.reveal_index += 1
            self._advance_slide_or_vote()
        elif self.phase == Phase.VOTE and self.deadline and now >= self.deadline:
            self._enter_final()

    async def tick(self) -> None:
        self.async_tick()
        from openapi_server.impl.persistence import persist_room

        await persist_room(self)

    def begin_votekick(
        self, caller_id: str, target_id: str, reason: str
    ) -> dict[str, Any]:
        if self.votekick and self.clock.now() < self.votekick.expires_at:
            raise ApiError(409, "VOTEKICK_IN_PROGRESS")
        if (
            target_id == caller_id
            or target_id not in self.players
            or self.players[target_id].kicked
        ):
            raise ApiError(409, "KICK_TARGET_INVALID")
        self.votekick = Votekick(
            target_id,
            reason,
            self.clock.now() + timedelta(seconds=settings.votekick_seconds),
        )
        self.start_timers()
        return self.cast_votekick(caller_id)

    def cast_votekick(self, player_id: str) -> dict[str, Any]:
        vk = self.votekick
        if vk is None:
            raise ApiError(409, "VOTEKICK_IN_PROGRESS")
        if self.clock.now() >= vk.expires_at:
            self.event_bus.publish_room("votekick_resolved", {"result": "EXPIRED"})
            self.votekick = None
            return {"votesCast": 0, "requiredVotes": 0, "resolved": True}
        if (
            player_id == vk.target_id
            or player_id not in self.players
            or self.players[player_id].kicked
        ):
            raise ApiError(403, "KICK_TARGET_INVALID")
        if player_id in vk.votes:
            eligible = [p for p in self.seats if p.id != vk.target_id]
            return {
                "votesCast": len(vk.votes),
                "requiredVotes": math.ceil(2 * len(eligible) / 3),
                "resolved": False,
            }
        vk.votes.add(player_id)
        eligible = [p for p in self.seats if p.id != vk.target_id]
        required = math.ceil(2 * len(eligible) / 3)
        if len(vk.votes) >= required:
            self.players[vk.target_id].kicked = True
            self.players[vk.target_id].kick_reason = vk.reason
            self.event_bus.publish_room(
                "votekick_resolved",
                {"result": "KICKED", "playerId": vk.target_id, "reason": vk.reason},
            )
            self.event_bus.publish_room(
                "player_presence", {"playerId": vk.target_id, "state": "KICKED"}
            )
            self.votekick = None
            self._skip_player_queue(vk.target_id)
            if len(self.seats) < 4:
                self.event_bus.publish_room(
                    "game_over",
                    {
                        "endedReason": "TOO_FEW_PLAYERS",
                        "completedCards": len(
                            [c for c in self.cards.values() if c.status == "SUBMITTED"]
                        ),
                    },
                )
                self.end_reason = "TOO_FEW_PLAYERS"
                self._enter_final()
            else:
                self._maybe_enter_reveal()
            return {
                "votesCast": len(vk.votes),
                "requiredVotes": required,
                "resolved": True,
            }
        self.event_bus.coalesce(
            "votekick",
            "votekick_progress",
            {
                "votesCast": len(vk.votes),
                "requiredVotes": required,
                "targetPlayerId": vk.target_id,
            },
        )
        return {
            "votesCast": len(vk.votes),
            "requiredVotes": required,
            "resolved": False,
        }

    def disconnect(self, player_id: str) -> None:
        player = self.players[player_id]
        if not player.connected:
            return
        player.connected = False
        player.disconnected_at = self.clock.now()
        if self.phase == Phase.GUESS and player_id in self.active_cards:
            card_id = self.active_cards[player_id]
            guess = self.cards[card_id].guesses[player_id]
            self.lock(player_id, card_id, timed_out=True)
            self.event_bus.publish_room(
                "card_capped",
                {
                    "cardId": card_id,
                    "playerId": player_id,
                    "status": (
                        "AUTO_LOCKED"
                        if guess.status == "AUTO_LOCKED"
                        else "SCORED_ZERO"
                    ),
                },
            )
        if self.votekick and self.votekick.target_id == player_id:
            self.event_bus.publish_room("votekick_resolved", {"result": "CANCELLED"})
            self.votekick = None
        self._rejoin_expiry[player_id] = self.clock.now() + timedelta(
            seconds=settings.rejoin_grace_seconds
        )
        self.event_bus.publish_room(
            "player_presence",
            {
                "playerId": player_id,
                "state": "LEFT",
                "rejoinGraceUntil": self._rejoin_expiry[player_id].isoformat(),
            },
        )
        self.start_timers()

    def reconnect(self, player_id: str) -> None:
        player = self.players[player_id]
        player.connected = True
        player.disconnected_at = None
        self._rejoin_expiry.pop(player_id, None)
        self.event_bus.publish_room(
            "player_presence", {"playerId": player_id, "state": "REJOINED"}
        )
        self.start_timers()

    def _enter_phase(self, phase: Phase, seconds: float | None = None) -> None:
        self.phase = phase
        self.deadline = (
            self.clock.now() + timedelta(seconds=seconds)
            if seconds is not None
            else None
        )
        self.ttl_expires_at = max(
            self.ttl_expires_at,
            self.clock.now() + timedelta(seconds=settings.room_ttl_seconds / 2),
        )
        if phase == Phase.FINAL:
            self.ttl_expires_at = max(
                self.ttl_expires_at, self.clock.now() + timedelta(minutes=10)
            )
        self.event_bus.publish_room(
            "phase_changed",
            {
                "phase": phase.value,
                "deadlineAt": self.deadline.isoformat() if self.deadline else None,
            },
        )
        self.start_timers()

    def _require_phase(self, phase: Phase) -> None:
        if self.phase != phase:
            retry = {
                "AUTHOR": "AUTHOR",
                "GUESS": "GUESS",
                "REVEAL": "REVEAL",
                "VOTE": "VOTE",
                "FINAL": "FINAL",
            }.get(phase.value, phase.value)
            raise ApiError(
                409, "WRONG_PHASE", phase=self.phase.value, retry_in_phase=retry
            )
