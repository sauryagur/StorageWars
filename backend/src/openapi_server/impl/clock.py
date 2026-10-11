from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    async def sleep_until(self, deadline: datetime) -> None: ...


class SystemClock:
    def __init__(self, scale: float = 1.0) -> None:
        if scale <= 0:
            raise ValueError("scale must be positive")
        self._origin = datetime.now(timezone.utc)
        self._started = time.monotonic()
        self._scale = scale

    def now(self) -> datetime:
        return self._origin + timedelta(
            seconds=(time.monotonic() - self._started) * self._scale
        )

    async def sleep_until(self, deadline: datetime) -> None:
        delay = max(0.0, (deadline - self.now()).total_seconds() / self._scale)
        await asyncio.sleep(delay)


class FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime.now(timezone.utc)
        if self._now.tzinfo is None:
            raise ValueError("FakeClock start must be timezone-aware")
        self._waiters: list[
            tuple[datetime, asyncio.Future[None], asyncio.AbstractEventLoop]
        ] = []

    def now(self) -> datetime:
        return self._now

    async def sleep_until(self, deadline: datetime) -> None:
        if deadline <= self._now:
            return
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        item = (deadline, future, loop)
        self._waiters.append(item)
        try:
            await future
        finally:
            try:
                self._waiters.remove(item)
            except ValueError:
                # Cleanup is idempotent across concurrent cancellation and advance.
                pass

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("cannot move clock backwards")
        self._now += timedelta(seconds=seconds)
        for deadline, future, loop in tuple(self._waiters):
            if deadline <= self._now:
                loop.call_soon_threadsafe(self._resolve, future)

    @staticmethod
    def _resolve(future: asyncio.Future[None]) -> None:
        if not future.done():
            future.set_result(None)


_clock: Clock | None = None


def get_clock() -> Clock:
    global _clock
    if _clock is None:
        from openapi_server.impl.config import settings

        _clock = SystemClock(settings.time_scale)
    return _clock


def set_clock(clock: Clock | None) -> None:
    global _clock
    _clock = clock
