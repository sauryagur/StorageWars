from __future__ import annotations

import math
import time
from dataclasses import dataclass

from openapi_server.impl.errors import ApiError

DEFAULTS: dict[str, tuple[int, float]] = {
    "create_ip": (10, 60),
    "join_ip": (30, 60),
    "join_failed_code_ip": (10, 60),
    "ticket_session": (10, 60),
    "open_session": (30, 60),
    "submit_session": (10, 60),
    "misc_session": (30, 60),
}


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    def __init__(self, scopes: dict[str, tuple[int, float]] | None = None) -> None:
        self.scopes = dict(scopes or DEFAULTS)
        self._buckets: dict[tuple[str, str], _Bucket] = {}

    def check(self, scope: str, key: str, *, cost: float = 1.0) -> None:
        capacity, period = self.scopes[scope]
        now = time.monotonic()
        bucket_key = (scope, key)
        bucket = self._buckets.get(bucket_key)
        if bucket is None:
            bucket = _Bucket(float(capacity), now)
            self._buckets[bucket_key] = bucket
        bucket.tokens = min(
            float(capacity),
            bucket.tokens + (now - bucket.updated_at) * capacity / period,
        )
        bucket.updated_at = now
        if bucket.tokens >= cost:
            bucket.tokens -= cost
            return
        retry_after = max(1, math.ceil((cost - bucket.tokens) * period / capacity))
        raise ApiError(
            429,
            "RATE_LIMITED",
            "Too many requests.",
            headers={"Retry-After": str(retry_after)},
        )

    def reset(self) -> None:
        self._buckets.clear()


limiter = TokenBucketLimiter()


def check_rate_limit(scope: str, key: str) -> None:
    limiter.check(scope, key)
