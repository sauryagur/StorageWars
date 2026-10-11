from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from openapi_server.impl.clock import Clock, get_clock


@dataclass
class _Subscriber:
    player_id: str
    queue: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=256)
    )


class EventBus:
    def __init__(
        self, room_id: str, clock: Clock | None = None, coalesce_ms: int = 500
    ) -> None:
        self.room_id = room_id
        self.clock = clock or get_clock()
        self.coalesce_seconds = coalesce_ms / 1000
        self._seq = 0
        self.history: list[dict[str, Any]] = []
        self._subscribers: set[int] = set()
        self._subscriber_objects: dict[int, _Subscriber] = {}
        self._pending: dict[str, tuple[str, dict[str, Any]]] = {}
        self._flush_task: asyncio.Task | None = None

    @property
    def seq(self) -> int:
        return self._seq

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def subscribe(self, player_id: str) -> asyncio.Queue[dict[str, Any]]:
        subscriber = _Subscriber(player_id)
        key = id(subscriber)
        self._subscriber_objects[key] = subscriber
        return subscriber.queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        for key, subscriber in tuple(self._subscriber_objects.items()):
            if subscriber.queue is queue:
                del self._subscriber_objects[key]

    def _event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        at = self.clock.now().isoformat()
        event = {"type": event_type, "seq": self.next_seq(), "at": at, **payload}
        self.history.append(event)
        return event

    def _deliver(self, event: dict[str, Any], player_id: str | None) -> None:
        for subscriber in tuple(self._subscriber_objects.values()):
            if player_id is None or subscriber.player_id == player_id:
                if subscriber.queue.full():
                    try:
                        subscriber.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                subscriber.queue.put_nowait(event)

    def publish_room(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = self._event(event_type, payload)
        self._deliver(event, None)
        return event

    def publish_player(
        self, player_id: str, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        event = self._event(event_type, payload)
        self._deliver(event, player_id)
        return event

    def coalesce(self, key: str, event_type: str, payload: dict[str, Any]) -> None:
        if event_type not in {
            "author_progress",
            "guess_progress",
            "vote_progress",
            "votekick_progress",
        }:
            raise ValueError("only progress events may be coalesced")
        self._pending[key] = (event_type, payload)
        if self._flush_task is not None and not self._flush_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pending, self._pending = self._pending, {}
            for pending_type, pending_payload in pending.values():
                self.publish_room(pending_type, pending_payload)
            return
        self._flush_task = loop.create_task(self._flush_later())

    async def _flush_later(self) -> None:
        await asyncio.sleep(self.coalesce_seconds)
        pending, self._pending = self._pending, {}
        for event_type, payload in pending.values():
            self.publish_room(event_type, payload)
