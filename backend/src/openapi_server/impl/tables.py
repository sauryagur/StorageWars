"""
impulse_buy/models.py

SQLModel schema for Impulse Buy.

DURABILITY MODEL
----------------
Durable source of truth ....... Category, ProductImage, Product,
                                 BannedWord (content pool + tuning)
Moderation ..................... Report
Append-through game records .... RoomRecord, PlayerRecord, AuthoredCard,
                                 GuessRecord, VoteRecord, GameEvent
The authoritative phase state machine, timers, and drip schedules run in
memory; tables 6-11 are written through as events complete, so analytics
and moderation survive without making the DB a coordination point.

SECRET BOUNDARY
---------------
Product.price_cents, original_title, original_description, and
ProductImage.storage_key must NEVER be projected onto any response
consumed before the REVEAL phase. Serializers are written against
explicit view models (see openapi.yaml), never against these tables
directly.
"""

import hashlib
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class Phase(str, PyEnum):
    """Server-authoritative game phases (PRD §Game flow)."""

    LOBBY = "LOBBY"
    AUTHOR = "AUTHOR"  # parallel, 60s
    GUESS = "GUESS"  # per-player, pipelined, 20s/card hard cap
    REVEAL = "REVEAL"  # shared carousel, ~12s/slide
    VOTE = "VOTE"  # funniest-card, hidden until final
    FINAL = "FINAL"  # scores revealed only now
    CLOSED = "CLOSED"  # TTL expired or abandoned


class PriceBand(int, PyEnum):
    """Coarse band shown to the author. NEVER the exact price."""

    B1 = 1  # under 15 USD
    B2 = 2  # 15 to 60 USD
    B3 = 3  # 60 to 200 USD
    B4 = 4  # over 200 USD


class ReviewBucket(str, PyEnum):
    """Review-count buckets shown to guessers at the 10s drip stage."""

    UNDER_10 = "UNDER_10"
    TEN_TO_99 = "TEN_TO_99"
    HUNDRED_TO_999 = "HUNDRED_TO_999"
    THOUSAND_TO_9999 = "THOUSAND_TO_9999"
    TEN_THOUSAND_PLUS = "TEN_THOUSAND_PLUS"


class KickReason(str, PyEnum):
    """Votekick is ONLY for these (PRD §Votekick rules)."""

    OFFENSIVE_CONTENT = "OFFENSIVE_CONTENT"
    AFK = "AFK"


class ReportReason(str, PyEnum):
    OFFENSIVE_CONTENT = "OFFENSIVE_CONTENT"
    OFFENSIVE_NAME = "OFFENSIVE_NAME"
    AFK = "AFK"
    OTHER = "OTHER"


class ReportStatus(str, PyEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class GameEventType(str, PyEnum):
    """Append-only analytics events backing the success-metrics dashboard."""

    ROOM_CREATED = "ROOM_CREATED"
    PLAYER_JOINED = "PLAYER_JOINED"
    PLAYER_DISCONNECTED = "PLAYER_DISCONNECTED"
    PLAYER_KICKED = "PLAYER_KICKED"
    GAME_STARTED = "GAME_STARTED"  # link-open -> first-card funnel
    AUTHOR_SUBMITTED = "AUTHOR_SUBMITTED"
    AUTHOR_SKIPPED = "AUTHOR_SKIPPED"  # timeout / disconnect
    GUESS_CARD_OPENED = "GUESS_CARD_OPENED"
    DRIP_STAGE_SHOWN = "DRIP_STAGE_SHOWN"  # 0s / 5s / 10s
    SLIDER_TOUCHED = "SLIDER_TOUCHED"
    GUESS_LOCKED = "GUESS_LOCKED"  # carries lock time -> spread metric
    GUESS_TIMED_OUT = "GUESS_TIMED_OUT"
    ALL_GUESSERS_DONE = "ALL_GUESSERS_DONE"
    REVEAL_SLIDE_SHOWN = "REVEAL_SLIDE_SHOWN"
    REVEAL_ADVANCED_EARLY = "REVEAL_ADVANCED_EARLY"
    VOTE_CAST = "VOTE_CAST"
    GAME_FINAL = "GAME_FINAL"  # completion-rate metric
    REPLAY_STARTED = "REPLAY_STARTED"  # replay-rate metric
    ROOM_CLOSED = "ROOM_CLOSED"


# --------------------------------------------------------------------------
# Content pool (durable source of truth)
# --------------------------------------------------------------------------


class Category(SQLModel, table=True):
    """~12 curated categories. sigma_category is the prior spread used to
    normalize log-space error (PRD §Scoring). Tunable from playtest data."""

    __tablename__ = "categories"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True, max_length=32)
    display_name: str = Field(max_length=64)
    # Default 0.5 -> zero point ~2.7x off in either direction.
    sigma: float = Field(default=0.5)
    active: bool = Field(default=True)
    products: list["Product"] = Relationship(back_populates="category")


class ProductImage(SQLModel, table=True):
    """Re-encoded, metadata- and filename-stripped image on our own CDN.
    The URL is derived from storage_key and is ONLY ever sent to the
    card's author (pre-reveal) and to everyone (reveal)."""

    __tablename__ = "product_images"

    id: Optional[int] = Field(default=None, primary_key=True)
    storage_key: str = Field(unique=True, max_length=256)
    content_hash: str = Field(index=True, max_length=64)  # near-dup detection
    width: int
    height: int
    bytes_size: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Product(SQLModel, table=True):
    """Curated product. Curated for: working image, snapshot price, single
    clear variant, 2-500 USD, log-uniform price sampling, lookup-resistant
    (unbranded / multipacks / bundles), no adult/weapon/offensive items."""

    __tablename__ = "products"

    id: Optional[int] = Field(default=None, primary_key=True)
    image_id: int = Field(foreign_key="product_images.id", index=True)
    image: ProductImage = Relationship()

    # --- SECRETS: never leave the server before REVEAL ---
    original_title: str = Field(max_length=512)
    original_description: str = Field(max_length=4096)
    price_cents: int = Field(index=True)  # snapshot price
    # ------------------------------------------------------

    currency: str = Field(default="USD", max_length=3)
    category_id: int = Field(foreign_key="categories.id", index=True)
    category: Category = Relationship(back_populates="products")

    star_rating: Optional[float] = Field(default=None)  # 1.0..5.0
    review_count: Optional[int] = Field(default=None)

    snapshot_date: datetime = Field()  # "snapshot price as of ..."
    price_band: PriceBand = Field()  # derived at insert; author sees this
    active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def compute_band(price_cents: int) -> PriceBand:
        if price_cents < 1500:
            return PriceBand.B1
        if price_cents < 6000:
            return PriceBand.B2
        if price_cents < 20000:
            return PriceBand.B3
        return PriceBand.B4


class BannedWord(SQLModel, table=True):
    """Server-side author-text validation list: profanity plus price words
    ("cheap", "expensive", "dollar", "bucks", "cost", "pricey") and number
    words ("fifty", "hundred"). Digits and currency symbols are rejected
    by the parser, not by this table."""

    __tablename__ = "banned_words"

    id: Optional[int] = Field(default=None, primary_key=True)
    word: str = Field(unique=True, max_length=64)
    kind: str = Field(index=True)  # "profanity" | "price_word" | "number_word"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --------------------------------------------------------------------------
# Game records (write-through from the in-memory state machine)
# --------------------------------------------------------------------------


class RoomRecord(SQLModel, table=True):
    """One room session. The live state machine is in memory; this row is
    the durable projection used for completion/replay metrics and for
    linking replay chains. Short TTL handled by the room service, which
    ultimately sets state=CLOSED."""

    __tablename__ = "room_records"
    __table_args__ = (UniqueConstraint("code"),)

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    code: str = Field(max_length=4, index=True)  # 4-char room code
    state: Phase = Field(default=Phase.LOBBY, index=True)
    creator_player_id: Optional[str] = Field(default=None)

    player_count: int = Field(default=0)
    product_count: int = Field(default=0)  # cards authored & played

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(default=None)
    ended_at: Optional[datetime] = Field(default=None)
    ttl_expires_at: datetime = Field(index=True)

    # Replay chains: "at least 50% of games produce a replay"
    replay_of_room_id: Optional[str] = Field(
        default=None, foreign_key="room_records.id"
    )

    players: list["PlayerRecord"] = Relationship(back_populates="room")
    cards: list["AuthoredCard"] = Relationship(back_populates="room")


class PlayerRecord(SQLModel, table=True):
    """A player in a room. No accounts: identity is a session token
    (hashed here) + display name. Rejoin = same token, same name."""

    __tablename__ = "player_records"
    __table_args__ = (
        UniqueConstraint("room_id", "session_token_hash"),
        UniqueConstraint("room_id", "display_name"),
    )

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    room_id: str = Field(foreign_key="room_records.id", index=True)
    room: RoomRecord = Relationship(back_populates="players")

    display_name: str = Field(max_length=24)  # profanity-filtered
    # Session token is issued to the client; only its SHA-256 is stored.
    session_token_hash: str = Field(max_length=64)
    is_creator: bool = Field(default=False)

    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    disconnected_at: Optional[datetime] = Field(default=None)
    kicked: bool = Field(default=False)  # votekick outcome
    kick_reason: Optional[KickReason] = Field(default=None)


class AuthoredCard(SQLModel, table=True):
    """One player's authored card for one product. Product secrets stay on
    Product; this row holds only what the author submitted (which is exactly
    what guessers may progressively receive)."""

    __tablename__ = "authored_cards"
    __table_args__ = (UniqueConstraint("room_id", "author_player_id"),)

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    room_id: str = Field(foreign_key="room_records.id", index=True)
    room: RoomRecord = Relationship(back_populates="cards")

    product_id: int = Field(foreign_key="products.id", index=True)
    author_player_id: str = Field(foreign_key="player_records.id", index=True)

    # --- author-submitted, validated fields (8-60 chars etc.) ---
    title: Optional[str] = Field(default=None, max_length=60)
    bullets: list[str] = Field(
        default_factory=list, sa_column=Column(JSON)
    )  # exactly 3, each 15-80 chars
    star_rating: Optional[float] = Field(default=None)  # 1.0..5.0, half steps
    review_bucket: Optional[ReviewBucket] = Field(default=None)
    category_slug: Optional[str] = Field(default=None, max_length=32)

    submitted: bool = Field(default=False)  # false => card skipped (timeout)
    submitted_at: Optional[datetime] = Field(default=None)

    # Computed at REVEAL. Hidden from clients until FINAL.
    author_points: Optional[int] = Field(default=None)
    funniest_bonus: Optional[int] = Field(default=None)
    funniest_votes: Optional[int] = Field(default=None)

    guesses: list["GuessRecord"] = Relationship(back_populates="card")


class GuessRecord(SQLModel, table=True):
    """One guesser's locked guess on one card. Lock time is stamped by the
    SERVER (latency-fairness). points/accuracy/z are computed at lock on
    the server but never exposed before FINAL."""

    __tablename__ = "guess_records"
    __table_args__ = (UniqueConstraint("card_id", "guesser_player_id"),)

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    card_id: str = Field(foreign_key="authored_cards.id", index=True)
    card: AuthoredCard = Relationship(back_populates="guesses")
    guesser_player_id: str = Field(foreign_key="player_records.id", index=True)

    value_cents: Optional[int] = Field(default=None)  # null when timed out before entry
    locked_at: datetime = Field()  # server timestamp only
    card_seconds: float = Field()  # t at lock, clamped 0..20
    multiplier: float = Field()  # M(t) = 1 - 0.3 * (t/20)

    # --- computed, hidden until FINAL ---
    z: Optional[float] = Field(default=None)  # |ln(guess/price)| / sigma
    accuracy: Optional[float] = Field(default=None)
    points: Optional[int] = Field(default=None)

    timed_out: bool = Field(default=False)  # auto-locked at 20s cap


class VoteRecord(SQLModel, table=True):
    """Funniest-card vote: one per player, never for their own card,
    hidden until after FINAL scoring is fixed."""

    __tablename__ = "vote_records"
    __table_args__ = (UniqueConstraint("room_id", "voter_player_id"),)

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    room_id: str = Field(foreign_key="room_records.id", index=True)
    voter_player_id: str = Field(foreign_key="player_records.id")
    card_id: str = Field(foreign_key="authored_cards.id", index=True)
    cast_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --------------------------------------------------------------------------
# Moderation & analytics
# --------------------------------------------------------------------------


class Report(SQLModel, table=True):
    """Report button output. Reports never expose game secrets to
    moderators viewing them pre-reveal; content is attached post-game."""

    __tablename__ = "reports"

    id: Optional[int] = Field(default=None, primary_key=True)
    room_code: str = Field(max_length=4, index=True)
    room_id: str = Field(foreign_key="room_records.id", index=True)
    reporter_player_id: str = Field(foreign_key="player_records.id")
    reported_card_id: Optional[str] = Field(
        default=None, foreign_key="authored_cards.id", index=True
    )
    reported_player_id: Optional[str] = Field(
        default=None, foreign_key="player_records.id", index=True
    )
    reason: ReportReason
    note: Optional[str] = Field(default=None, max_length=500)
    status: ReportStatus = Field(default=ReportStatus.OPEN, index=True)
    resolution_note: Optional[str] = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GameEvent(SQLModel, table=True):
    """Append-only event stream backing the PRD success-metrics dashboard:
    lock-time spread, lazy-strategy ratio, completion rate, replay rate.
    Payloads are redacted server-side; guess values never appear in
    payloads before FINAL."""

    __tablename__ = "game_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    room_id: str = Field(foreign_key="room_records.id", index=True)
    event_type: GameEventType = Field(index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
