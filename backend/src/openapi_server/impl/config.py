from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = (
        "postgresql+psycopg://impulsebuy:impulsebuy@localhost:5432/impulsebuy"
    )
    admin_token: str = ""
    session_token_bytes: int = 32
    image_url_secret: str = ""
    public_base_url: str = "http://localhost:3000"
    image_url_ttl_seconds: int = 300
    cors_allow_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    author_seconds: float = 60
    card_cap_seconds: float = 20
    min_dwell_seconds: float = 3
    drip_bullets_seconds: float = 5
    drip_rating_seconds: float = 10
    slide_seconds: float = 12
    vote_seconds: float = 30
    votekick_seconds: float = 30
    rejoin_grace_seconds: float = 120
    seat_claim_seconds: float = 60
    room_ttl_seconds: float = 1800
    heartbeat_seconds: float = 15
    progress_coalesce_ms: int = 500
    # Game-time multiplier. Durations below are divided by it, so 0.1 runs
    # every phase 10x slower in real time. Timestamps stay real wall time.
    time_scale: float = 1.0
    seed_fixtures: bool = False
    media_root: str = "media"


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def get_settings() -> Settings:
    scale = _float("TIME_SCALE", 1.0)
    if scale <= 0:
        raise ValueError("TIME_SCALE must be positive")

    def seconds(name: str, default: float) -> float:
        """Real seconds a game-time duration lasts with this TIME_SCALE."""
        return _float(name, default) / scale

    return Settings(
        database_url=os.getenv("DATABASE_URL", Settings.database_url),
        admin_token=os.getenv("ADMIN_TOKEN", ""),
        session_token_bytes=_int("SESSION_TOKEN_BYTES", 32),
        image_url_secret=os.getenv("IMAGE_URL_SECRET", ""),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://localhost:3000").rstrip(
            "/"
        ),
        image_url_ttl_seconds=max(
            1, int(round(seconds("IMAGE_URL_TTL_SECONDS", 300)))
        ),
        cors_allow_origins=tuple(
            x.strip()
            for x in os.getenv(
                "CORS_ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if x.strip()
        ),
        author_seconds=seconds("AUTHOR_SECONDS", 60),
        card_cap_seconds=seconds("CARD_CAP_SECONDS", 20),
        min_dwell_seconds=seconds("MIN_DWELL_SECONDS", 3),
        drip_bullets_seconds=seconds("DRIP_BULLETS_SECONDS", 5),
        drip_rating_seconds=seconds("DRIP_RATING_SECONDS", 10),
        slide_seconds=seconds("SLIDE_SECONDS", 12),
        vote_seconds=seconds("VOTE_SECONDS", 30),
        votekick_seconds=seconds("VOTEKICK_SECONDS", 30),
        rejoin_grace_seconds=seconds("REJOIN_GRACE_SECONDS", 120),
        seat_claim_seconds=seconds("SEAT_CLAIM_SECONDS", 60),
        room_ttl_seconds=seconds("ROOM_TTL_SECONDS", 1800),
        heartbeat_seconds=_float("HEARTBEAT_SECONDS", 15),
        progress_coalesce_ms=_int("PROGRESS_COALESCE_MS", 500),
        time_scale=scale,
        seed_fixtures=os.getenv("SEED_FIXTURES", "0") == "1",
        media_root=os.getenv("MEDIA_ROOT", "media"),
    )


settings = get_settings()
