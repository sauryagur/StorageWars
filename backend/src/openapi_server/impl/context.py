from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionContext:
    room_id: str
    room_code: str
    player_id: str
    session_token_hash: str


current_session: ContextVar[SessionContext] = ContextVar("current_session")
current_admin: ContextVar[bool] = ContextVar("current_admin", default=False)
client_ip: ContextVar[str] = ContextVar("client_ip", default="unknown")
