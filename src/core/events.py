"""Domain events shared by stateful core services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.models import SessionPhase


class SessionEvent(StrEnum):
    SELECT_PROFILE = "select_profile"
    CREATE_SESSION = "create_session"
    REQUIRE_INPUT = "require_input"
    MARK_READY = "mark_ready"
    REQUEST_CONNECT = "request_connect"
    MARK_CONNECTED = "mark_connected"
    REQUEST_PAUSE = "request_pause"
    MARK_PAUSED = "mark_paused"
    REQUEST_RESUME = "request_resume"
    MARK_RECONNECTING = "mark_reconnecting"
    REQUEST_DISCONNECT = "request_disconnect"
    MARK_DISCONNECTED = "mark_disconnected"
    FAIL = "fail"
    RESET = "reset"


@dataclass(slots=True, frozen=True)
class TransitionRecord:
    previous_state: SessionPhase
    event: SessionEvent
    new_state: SessionPhase
    reason: str | None = None

