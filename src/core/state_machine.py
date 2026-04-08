"""Connection lifecycle state machine."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.events import SessionEvent, TransitionRecord
from core.models import SessionPhase


class InvalidStateTransitionError(ValueError):
    """Raised when a transition is not allowed from the current state."""


@dataclass(slots=True)
class SessionStateMachine:
    state: SessionPhase = SessionPhase.IDLE
    selected_profile_id: str | None = None
    active_session_id: str | None = None
    last_error: str | None = None
    history: list[TransitionRecord] = field(default_factory=list)

    _TRANSITIONS: dict[tuple[SessionPhase, SessionEvent], SessionPhase] = field(
        init=False,
        repr=False,
        default_factory=lambda: {
            (SessionPhase.IDLE, SessionEvent.SELECT_PROFILE): SessionPhase.PROFILE_SELECTED,
            (
                SessionPhase.PROFILE_SELECTED,
                SessionEvent.CREATE_SESSION,
            ): SessionPhase.SESSION_CREATED,
            (
                SessionPhase.SESSION_CREATED,
                SessionEvent.REQUIRE_INPUT,
            ): SessionPhase.WAITING_FOR_INPUT,
            (
                SessionPhase.READY,
                SessionEvent.REQUIRE_INPUT,
            ): SessionPhase.WAITING_FOR_INPUT,
            (
                SessionPhase.CONNECTING,
                SessionEvent.REQUIRE_INPUT,
            ): SessionPhase.WAITING_FOR_INPUT,
            (
                SessionPhase.CONNECTED,
                SessionEvent.REQUIRE_INPUT,
            ): SessionPhase.WAITING_FOR_INPUT,
            (
                SessionPhase.PAUSED,
                SessionEvent.REQUIRE_INPUT,
            ): SessionPhase.WAITING_FOR_INPUT,
            (
                SessionPhase.RECONNECTING,
                SessionEvent.REQUIRE_INPUT,
            ): SessionPhase.WAITING_FOR_INPUT,
            (SessionPhase.SESSION_CREATED, SessionEvent.MARK_READY): SessionPhase.READY,
            (
                SessionPhase.WAITING_FOR_INPUT,
                SessionEvent.MARK_READY,
            ): SessionPhase.READY,
            (
                SessionPhase.SESSION_CREATED,
                SessionEvent.MARK_CONNECTED,
            ): SessionPhase.CONNECTED,
            (
                SessionPhase.CONNECTING,
                SessionEvent.MARK_READY,
            ): SessionPhase.READY,
            (
                SessionPhase.RECONNECTING,
                SessionEvent.MARK_READY,
            ): SessionPhase.READY,
            (SessionPhase.READY, SessionEvent.REQUEST_CONNECT): SessionPhase.CONNECTING,
            (
                SessionPhase.CONNECTING,
                SessionEvent.MARK_CONNECTED,
            ): SessionPhase.CONNECTED,
            (
                SessionPhase.PAUSED,
                SessionEvent.MARK_CONNECTED,
            ): SessionPhase.CONNECTED,
            (
                SessionPhase.CONNECTING,
                SessionEvent.MARK_RECONNECTING,
            ): SessionPhase.RECONNECTING,
            (
                SessionPhase.CONNECTED,
                SessionEvent.MARK_RECONNECTING,
            ): SessionPhase.RECONNECTING,
            (
                SessionPhase.RECONNECTING,
                SessionEvent.MARK_CONNECTED,
            ): SessionPhase.CONNECTED,
            (
                SessionPhase.CONNECTED,
                SessionEvent.REQUEST_PAUSE,
            ): SessionPhase.PAUSED,
            (
                SessionPhase.CONNECTED,
                SessionEvent.MARK_PAUSED,
            ): SessionPhase.PAUSED,
            (
                SessionPhase.SESSION_CREATED,
                SessionEvent.MARK_PAUSED,
            ): SessionPhase.PAUSED,
            (
                SessionPhase.PAUSED,
                SessionEvent.REQUEST_RESUME,
            ): SessionPhase.CONNECTING,
            (
                SessionPhase.SESSION_CREATED,
                SessionEvent.MARK_RECONNECTING,
            ): SessionPhase.RECONNECTING,
            (
                SessionPhase.WAITING_FOR_INPUT,
                SessionEvent.REQUEST_DISCONNECT,
            ): SessionPhase.DISCONNECTING,
            (
                SessionPhase.SESSION_CREATED,
                SessionEvent.REQUEST_DISCONNECT,
            ): SessionPhase.DISCONNECTING,
            (
                SessionPhase.CONNECTING,
                SessionEvent.REQUEST_DISCONNECT,
            ): SessionPhase.DISCONNECTING,
            (
                SessionPhase.RECONNECTING,
                SessionEvent.REQUEST_DISCONNECT,
            ): SessionPhase.DISCONNECTING,
            (
                SessionPhase.CONNECTED,
                SessionEvent.REQUEST_DISCONNECT,
            ): SessionPhase.DISCONNECTING,
            (
                SessionPhase.PAUSED,
                SessionEvent.REQUEST_DISCONNECT,
            ): SessionPhase.DISCONNECTING,
            (
                SessionPhase.READY,
                SessionEvent.REQUEST_DISCONNECT,
            ): SessionPhase.DISCONNECTING,
            (
                SessionPhase.DISCONNECTING,
                SessionEvent.MARK_DISCONNECTED,
            ): SessionPhase.IDLE,
            (
                SessionPhase.SESSION_CREATED,
                SessionEvent.MARK_DISCONNECTED,
            ): SessionPhase.IDLE,
            (
                SessionPhase.WAITING_FOR_INPUT,
                SessionEvent.MARK_DISCONNECTED,
            ): SessionPhase.IDLE,
            (
                SessionPhase.READY,
                SessionEvent.MARK_DISCONNECTED,
            ): SessionPhase.IDLE,
            (
                SessionPhase.CONNECTING,
                SessionEvent.MARK_DISCONNECTED,
            ): SessionPhase.IDLE,
            (
                SessionPhase.CONNECTED,
                SessionEvent.MARK_DISCONNECTED,
            ): SessionPhase.IDLE,
            (
                SessionPhase.PAUSED,
                SessionEvent.MARK_DISCONNECTED,
            ): SessionPhase.IDLE,
            (
                SessionPhase.RECONNECTING,
                SessionEvent.MARK_DISCONNECTED,
            ): SessionPhase.IDLE,
            (SessionPhase.ERROR, SessionEvent.RESET): SessionPhase.IDLE,
        },
    )

    def apply(
        self,
        event: SessionEvent,
        *,
        profile_id: str | None = None,
        session_id: str | None = None,
        reason: str | None = None,
    ) -> TransitionRecord:
        if event == SessionEvent.FAIL:
            previous_state = self.state
            self.state = SessionPhase.ERROR
            self.last_error = reason or "Unknown error"
            record = TransitionRecord(previous_state, event, self.state, reason)
            self.history.append(record)
            return record

        transition_key = (self.state, event)
        if transition_key not in self._TRANSITIONS:
            raise InvalidStateTransitionError(
                f"Cannot apply {event.value!r} while in state {self.state.value!r}."
            )

        previous_state = self.state
        self.state = self._TRANSITIONS[transition_key]

        if profile_id is not None:
            self.selected_profile_id = profile_id
        if session_id is not None:
            self.active_session_id = session_id

        if self.state is SessionPhase.IDLE:
            self.active_session_id = None
            self.last_error = None

        record = TransitionRecord(previous_state, event, self.state, reason)
        self.history.append(record)
        return record
