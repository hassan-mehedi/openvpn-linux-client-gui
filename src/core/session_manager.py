"""Application-facing session lifecycle coordinator."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Protocol

from core.events import SessionEvent
from core.models import AttentionRequest, SessionDescriptor, SessionPhase
from core.secrets import saved_password_request_id
from core.state_machine import SessionStateMachine


class SessionBackend(Protocol):
    def list_sessions(self) -> tuple[SessionDescriptor, ...]:
        """Return known sessions."""

    def create_session(self, profile_id: str) -> SessionDescriptor:
        """Create a session for a profile."""

    def prepare_session(self, session_id: str) -> SessionDescriptor:
        """Prepare a session before connect."""

    def connect(self, session_id: str) -> SessionDescriptor:
        """Connect a session."""

    def disconnect(self, session_id: str) -> SessionDescriptor:
        """Disconnect a session."""

    def pause(self, session_id: str) -> SessionDescriptor:
        """Pause a session."""

    def resume(self, session_id: str) -> SessionDescriptor:
        """Resume a paused session."""

    def restart(self, session_id: str) -> SessionDescriptor:
        """Restart a session."""

    def get_session_status(self, session_id: str) -> SessionDescriptor:
        """Return the current session status."""

    def subscribe_to_updates(
        self,
        session_id: str,
        callback: Callable[[SessionDescriptor], None],
    ) -> Callable[[], None]:
        """Subscribe to session status updates."""


class AttentionBackend(Protocol):
    def get_attention_requests(self, session_id: str) -> tuple[AttentionRequest, ...]:
        """Return current attention requests."""

    def provide_user_input(self, session_id: str, field_id: str, value: str) -> None:
        """Submit input for a challenge field."""


class ProfileCredentialBackend(Protocol):
    def load_password(self, profile_id: str) -> str | None:
        """Load a saved password for a profile."""


class ConnectionPreparationBackend(Protocol):
    def prepare_profile(self, profile_id: str) -> None:
        """Apply runtime profile settings before session creation."""


@dataclass(slots=True, frozen=True)
class SessionSnapshot:
    state: SessionPhase
    selected_profile_id: str | None
    active_session: SessionDescriptor | None
    attention_requests: tuple[AttentionRequest, ...]
    last_error: str | None


class SessionLifecycleService:
    """Coordinates adapter calls through the formal state machine."""

    def __init__(
        self,
        session_backend: SessionBackend,
        attention_backend: AttentionBackend,
        *,
        profile_credentials: ProfileCredentialBackend | None = None,
        connection_preparation: ConnectionPreparationBackend | None = None,
        state_machine: SessionStateMachine | None = None,
    ) -> None:
        self._session_backend = session_backend
        self._attention_backend = attention_backend
        self._profile_credentials = profile_credentials
        self._connection_preparation = connection_preparation
        self._state_machine = state_machine or SessionStateMachine()
        self._active_session: SessionDescriptor | None = None
        self._attention_requests: tuple[AttentionRequest, ...] = ()
        self._auto_submitted_saved_fields: set[tuple[str, str]] = set()

    def snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            state=self._state_machine.state,
            selected_profile_id=self._state_machine.selected_profile_id,
            active_session=self._active_session,
            attention_requests=self._attention_requests,
            last_error=self._state_machine.last_error,
        )

    def select_profile(self, profile_id: str) -> SessionSnapshot:
        if (
            self._state_machine.selected_profile_id != profile_id
            or self._state_machine.state is SessionPhase.IDLE
        ):
            self._state_machine.apply(SessionEvent.SELECT_PROFILE, profile_id=profile_id)
        return self.snapshot()

    def prepare_connection(self, profile_id: str) -> SessionSnapshot:
        if self._state_machine.state is SessionPhase.ERROR:
            self._state_machine.apply(SessionEvent.RESET)
            self._active_session = None
            self._attention_requests = ()
            self._auto_submitted_saved_fields.clear()
        self.select_profile(profile_id)
        try:
            if self._connection_preparation is not None:
                self._connection_preparation.prepare_profile(profile_id)
        except Exception as exc:
            self._state_machine.apply(SessionEvent.FAIL, reason=str(exc))
            raise
        try:
            session = self._session_backend.create_session(profile_id)
        except Exception as exc:
            restored = self.restore_existing_session(profile_id)
            if restored.active_session is not None:
                return restored
            self._state_machine.apply(SessionEvent.FAIL, reason=str(exc))
            raise exc
        self._active_session = session
        self._auto_submitted_saved_fields.clear()
        self._state_machine.apply(
            SessionEvent.CREATE_SESSION,
            session_id=session.id,
        )
        prepared = self._session_backend.prepare_session(session.id)
        self._apply_backend_session(prepared)
        return self.snapshot()

    def connect(self, profile_id: str | None = None) -> SessionSnapshot:
        if self._active_session is not None and self._state_machine.state in {
            SessionPhase.CONNECTED,
            SessionPhase.CONNECTING,
            SessionPhase.RECONNECTING,
        }:
            if profile_id is None or self._state_machine.selected_profile_id == profile_id:
                return self.snapshot()
        if self._active_session is None:
            if profile_id is None:
                raise ValueError("profile_id is required when no active session exists.")
            self.prepare_connection(profile_id)
        elif profile_id is not None and self._state_machine.selected_profile_id != profile_id:
            self.prepare_connection(profile_id)

        if self._attention_requests:
            return self.snapshot()

        self._mark_ready_if_needed()
        self._state_machine.apply(SessionEvent.REQUEST_CONNECT)
        assert self._active_session is not None
        self._apply_backend_session(self._session_backend.connect(self._active_session.id))
        return self.snapshot()

    def submit_attention_input(self, field_id: str, value: str) -> SessionSnapshot:
        return self.submit_attention_inputs({field_id: value})

    def submit_attention_inputs(self, values: dict[str, str]) -> SessionSnapshot:
        if self._active_session is None:
            raise ValueError("No active session is waiting for input.")

        for request in self._attention_requests:
            try:
                value = values[request.field_id].strip()
            except KeyError as exc:
                raise ValueError(f"Missing input for {request.label}.") from exc
            if not value:
                raise ValueError(f"Input for {request.label} cannot be empty.")
            self._attention_backend.provide_user_input(
                self._active_session.id,
                request.field_id,
                value,
            )
        prepared = self._session_backend.prepare_session(self._active_session.id)
        self._apply_backend_session(prepared)
        return self.snapshot()

    def disconnect(self) -> SessionSnapshot:
        if self._active_session is None:
            return self.snapshot()

        current_state = self._state_machine.state
        if current_state in {
            SessionPhase.CONNECTED,
            SessionPhase.PAUSED,
            SessionPhase.READY,
        }:
            self._state_machine.apply(SessionEvent.REQUEST_DISCONNECT)
        disconnected = self._session_backend.disconnect(self._active_session.id)
        self._apply_backend_session(disconnected)
        if disconnected.state in {SessionPhase.IDLE, SessionPhase.DISCONNECTING}:
            self._active_session = None
        return self.snapshot()

    def pause(self) -> SessionSnapshot:
        if self._active_session is None:
            return self.snapshot()
        self._state_machine.apply(SessionEvent.REQUEST_PAUSE)
        self._apply_backend_session(self._session_backend.pause(self._active_session.id))
        return self.snapshot()

    def resume(self) -> SessionSnapshot:
        if self._active_session is None:
            return self.snapshot()
        self._state_machine.apply(SessionEvent.REQUEST_RESUME)
        resumed = self._session_backend.resume(self._active_session.id)
        self._apply_backend_session(resumed)
        return self.snapshot()

    def restart(self) -> SessionSnapshot:
        if self._active_session is None:
            return self.snapshot()
        restarted = self._session_backend.restart(self._active_session.id)
        self._apply_backend_session(restarted)
        return self.snapshot()

    def refresh_status(self) -> SessionSnapshot:
        if self._active_session is None:
            return self.restore_existing_session()
        self._apply_backend_session(
            self._session_backend.get_session_status(self._active_session.id)
        )
        if self._state_machine.state is SessionPhase.IDLE:
            self._active_session = None
        return self.snapshot()

    def restore_existing_session(
        self,
        profile_id: str | None = None,
    ) -> SessionSnapshot:
        if self._active_session is not None and (
            profile_id is None or self._active_session.profile_id == profile_id
        ):
            return self.snapshot()

        sessions = self._session_backend.list_sessions()
        candidates = [
            session
            for session in sessions
            if session.state is not SessionPhase.IDLE
            and (profile_id is None or session.profile_id == profile_id)
        ]
        if not candidates:
            return self.snapshot()

        session = candidates[0]
        if self._state_machine.state is SessionPhase.ERROR:
            self._state_machine.apply(SessionEvent.RESET)
        if self._state_machine.state is SessionPhase.IDLE:
            self._state_machine.apply(
                SessionEvent.SELECT_PROFILE,
                profile_id=session.profile_id,
            )
            self._state_machine.apply(
                SessionEvent.CREATE_SESSION,
                session_id=session.id,
            )
        self._apply_backend_session(session)
        return self.snapshot()

    def watch_active_session(
        self,
        callback: Callable[[SessionSnapshot], None],
    ) -> Callable[[], None]:
        if self._active_session is None:
            return lambda: None
        session_id = self._active_session.id

        def on_update(session: SessionDescriptor) -> None:
            if self._active_session is None or self._active_session.id != session.id:
                return
            self._apply_backend_session(session)
            if self._state_machine.state is SessionPhase.IDLE:
                self._active_session = None
            callback(self.snapshot())

        return self._session_backend.subscribe_to_updates(session_id, on_update)

    def _collect_attention(
        self, session: SessionDescriptor
    ) -> tuple[AttentionRequest, ...]:
        if not session.requires_input:
            return ()
        return self._attention_backend.get_attention_requests(session.id)

    def _mark_ready_if_needed(self) -> None:
        if self._state_machine.state in {
            SessionPhase.SESSION_CREATED,
            SessionPhase.WAITING_FOR_INPUT,
        }:
            self._state_machine.apply(SessionEvent.MARK_READY)

    def _apply_backend_session(self, session: SessionDescriptor) -> None:
        previous_session_id = self._active_session.id if self._active_session is not None else None
        self._active_session = session
        if previous_session_id != session.id:
            self._auto_submitted_saved_fields.clear()
        self._attention_requests = self._prefill_saved_password(self._collect_attention(session))
        self._sync_state(session)
        if self._state_machine.state is SessionPhase.IDLE:
            self._attention_requests = ()
            self._auto_submitted_saved_fields.clear()
            return
        self._maybe_apply_saved_password()

    def _sync_state(self, session: SessionDescriptor) -> None:
        current = self._state_machine.state
        if session.state is SessionPhase.ERROR:
            self._state_machine.apply(
                SessionEvent.FAIL,
                reason=session.status_message or "Connection failed.",
            )
            return
        if session.state is SessionPhase.WAITING_FOR_INPUT:
            if current in {
                SessionPhase.SESSION_CREATED,
                SessionPhase.READY,
                SessionPhase.CONNECTING,
                SessionPhase.CONNECTED,
                SessionPhase.PAUSED,
                SessionPhase.RECONNECTING,
            }:
                self._state_machine.apply(SessionEvent.REQUIRE_INPUT)
            return
        if session.state is SessionPhase.READY:
            if current in {
                SessionPhase.SESSION_CREATED,
                SessionPhase.WAITING_FOR_INPUT,
                SessionPhase.CONNECTING,
                SessionPhase.RECONNECTING,
            }:
                self._state_machine.apply(SessionEvent.MARK_READY)
            return
        if session.state is SessionPhase.CONNECTED:
            if current in {
                SessionPhase.SESSION_CREATED,
                SessionPhase.CONNECTING,
                SessionPhase.PAUSED,
                SessionPhase.RECONNECTING,
                SessionPhase.READY,
            }:
                self._state_machine.apply(SessionEvent.MARK_CONNECTED)
            return
        if session.state is SessionPhase.PAUSED:
            if current in {SessionPhase.SESSION_CREATED, SessionPhase.CONNECTED}:
                self._state_machine.apply(SessionEvent.MARK_PAUSED)
            return
        if session.state is SessionPhase.RECONNECTING:
            if current in {
                SessionPhase.SESSION_CREATED,
                SessionPhase.CONNECTING,
                SessionPhase.CONNECTED,
                SessionPhase.READY,
            }:
                self._state_machine.apply(SessionEvent.MARK_RECONNECTING)
            return
        if session.state in {SessionPhase.DISCONNECTING, SessionPhase.IDLE}:
            if current is SessionPhase.IDLE:
                return
            if current is not SessionPhase.DISCONNECTING:
                self._state_machine.apply(SessionEvent.REQUEST_DISCONNECT)
            self._state_machine.apply(SessionEvent.MARK_DISCONNECTED)

    def _prefill_saved_password(
        self,
        requests: tuple[AttentionRequest, ...],
    ) -> tuple[AttentionRequest, ...]:
        if self._active_session is None or self._profile_credentials is None:
            return requests
        field_id = saved_password_request_id(requests)
        if field_id is None:
            return requests
        if (self._active_session.id, field_id) in self._auto_submitted_saved_fields:
            return requests
        saved_password = self._profile_credentials.load_password(self._active_session.profile_id)
        if not saved_password:
            return requests
        return tuple(
            replace(request, value=saved_password)
            if request.field_id == field_id
            else request
            for request in requests
        )

    def _maybe_apply_saved_password(self) -> bool:
        if self._active_session is None or not self._attention_requests:
            return False
        field_id = saved_password_request_id(self._attention_requests)
        if field_id is None:
            return False
        if (self._active_session.id, field_id) in self._auto_submitted_saved_fields:
            return False
        request = next(
            (item for item in self._attention_requests if item.field_id == field_id),
            None,
        )
        if request is None or not request.value:
            return False

        self._attention_backend.provide_user_input(
            self._active_session.id,
            field_id,
            request.value,
        )
        self._auto_submitted_saved_fields.add((self._active_session.id, field_id))
        prepared = self._session_backend.prepare_session(self._active_session.id)
        self._apply_backend_session(prepared)
        return True
