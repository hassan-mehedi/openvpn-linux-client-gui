"""Integration tests for SessionLifecycleService with fake backends.

These tests exercise the full lifecycle of a session, coordinating
SessionLifecycleService with fake implementations of every backend protocol.
Fake backends are self-contained here — do not import from unit tests.
"""

from __future__ import annotations

from typing import Callable

import pytest

from core.models import (
    AttentionFieldType,
    AttentionRequest,
    SessionDescriptor,
    SessionPhase,
)
from core.secrets import MemorySecretStore, ProfileSecretsService
from core.session_manager import SessionLifecycleService


# ---------------------------------------------------------------------------
# Self-contained fake backends
# ---------------------------------------------------------------------------


class FakeSessionBackend:
    """Minimal configurable session backend for integration tests."""

    def __init__(
        self,
        *,
        profile_id: str = "profile-1",
        requires_input: bool = False,
        connect_state: SessionPhase = SessionPhase.CONNECTED,
        prepare_state_after_submit: SessionPhase = SessionPhase.READY,
    ) -> None:
        self.profile_id = profile_id
        self.requires_input = requires_input
        self.connect_state = connect_state
        self.prepare_state_after_submit = prepare_state_after_submit

        self._created_count = 0
        self.sessions: list[SessionDescriptor] = []
        self.disconnect_calls: list[str] = []
        self.pause_calls: list[str] = []
        self.resume_calls: list[str] = []
        self.restart_calls: list[str] = []
        self._subscriber: Callable[[SessionDescriptor], None] | None = None

    # --- SessionBackend protocol ---

    def list_sessions(self) -> tuple[SessionDescriptor, ...]:
        return tuple(self.sessions)

    def create_session(self, profile_id: str) -> SessionDescriptor:
        self._created_count += 1
        return SessionDescriptor(
            id=f"session-{self._created_count}",
            profile_id=profile_id,
            state=SessionPhase.SESSION_CREATED,
        )

    def prepare_session(self, session_id: str) -> SessionDescriptor:
        state = (
            SessionPhase.WAITING_FOR_INPUT
            if self.requires_input
            else self.prepare_state_after_submit
        )
        return SessionDescriptor(
            id=session_id,
            profile_id=self.profile_id,
            state=state,
            requires_input=self.requires_input,
        )

    def connect(self, session_id: str) -> SessionDescriptor:
        return SessionDescriptor(
            id=session_id,
            profile_id=self.profile_id,
            state=self.connect_state,
        )

    def disconnect(self, session_id: str) -> SessionDescriptor:
        self.disconnect_calls.append(session_id)
        return SessionDescriptor(
            id=session_id,
            profile_id=self.profile_id,
            state=SessionPhase.IDLE,
        )

    def pause(self, session_id: str) -> SessionDescriptor:
        self.pause_calls.append(session_id)
        return SessionDescriptor(
            id=session_id,
            profile_id=self.profile_id,
            state=SessionPhase.PAUSED,
        )

    def resume(self, session_id: str) -> SessionDescriptor:
        self.resume_calls.append(session_id)
        return SessionDescriptor(
            id=session_id,
            profile_id=self.profile_id,
            state=SessionPhase.CONNECTED,
        )

    def restart(self, session_id: str) -> SessionDescriptor:
        self.restart_calls.append(session_id)
        return SessionDescriptor(
            id=session_id,
            profile_id=self.profile_id,
            state=SessionPhase.CONNECTING,
        )

    def get_session_status(self, session_id: str) -> SessionDescriptor:
        return SessionDescriptor(
            id=session_id,
            profile_id=self.profile_id,
            state=self.connect_state,
        )

    def subscribe_to_updates(
        self,
        session_id: str,
        callback: Callable[[SessionDescriptor], None],
    ) -> Callable[[], None]:
        self._subscriber = callback
        return lambda: None

    # --- helpers ---

    def push_update(self, session_id: str, state: SessionPhase) -> None:
        """Simulate a backend-initiated status change."""
        if self._subscriber is not None:
            self._subscriber(
                SessionDescriptor(
                    id=session_id,
                    profile_id=self.profile_id,
                    state=state,
                )
            )


class FakeAttentionBackend:
    """Returns an OTP challenge; records every submission."""

    def __init__(self) -> None:
        self.submissions: list[tuple[str, str, str]] = []

    def get_attention_requests(self, session_id: str) -> tuple[AttentionRequest, ...]:
        return (
            AttentionRequest(
                session_id=session_id,
                field_id="otp",
                label="One-time code",
                field_type=AttentionFieldType.OTP,
                secret=True,
            ),
        )

    def provide_user_input(self, session_id: str, field_id: str, value: str) -> None:
        self.submissions.append((session_id, field_id, value))


class FakePasswordAttentionBackend:
    """Returns a single password challenge; optionally accepts saved input."""

    def __init__(
        self,
        session_backend: FakeSessionBackend,
        *,
        accept_saved_input: bool = True,
    ) -> None:
        self._session_backend = session_backend
        self._accept_saved_input = accept_saved_input
        self.submissions: list[tuple[str, str, str]] = []

    def get_attention_requests(self, session_id: str) -> tuple[AttentionRequest, ...]:
        return (
            AttentionRequest(
                session_id=session_id,
                field_id="password",
                label="Password",
                field_type=AttentionFieldType.SECRET,
                secret=True,
            ),
        )

    def provide_user_input(self, session_id: str, field_id: str, value: str) -> None:
        self.submissions.append((session_id, field_id, value))
        if self._accept_saved_input:
            # After the saved password is submitted the session no longer
            # needs input, so prepare_session will return READY next time.
            self._session_backend.requires_input = False


class FakeAppStateBackend:
    """Records calls to record_connected_profile."""

    def __init__(self) -> None:
        self.recorded_profiles: list[str] = []

    def record_connected_profile(self, profile_id: str) -> None:
        self.recorded_profiles.append(profile_id)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_service(
    session_backend: FakeSessionBackend,
    attention_backend: FakeAttentionBackend | FakePasswordAttentionBackend,
    *,
    app_state: FakeAppStateBackend | None = None,
    profile_credentials=None,
) -> SessionLifecycleService:
    return SessionLifecycleService(
        session_backend,
        attention_backend,
        app_state=app_state,
        profile_credentials=profile_credentials,
    )


# ---------------------------------------------------------------------------
# Test 1 – Full connect → pause → resume → disconnect cycle
# ---------------------------------------------------------------------------


def test_full_connect_pause_resume_disconnect_cycle() -> None:
    """Exercise the happy-path lifecycle without any attention prompts."""
    session_backend = FakeSessionBackend()
    attention_backend = FakeAttentionBackend()
    service = _make_service(session_backend, attention_backend)

    # connect
    connected = service.connect("profile-1")
    assert connected.state is SessionPhase.CONNECTED
    assert connected.active_session is not None
    session_id = connected.active_session.id

    # pause
    paused = service.pause()
    assert paused.state is SessionPhase.PAUSED
    assert session_backend.pause_calls == [session_id]

    # resume
    resumed = service.resume()
    assert resumed.state is SessionPhase.CONNECTED
    assert session_backend.resume_calls == [session_id]

    # disconnect
    disconnected = service.disconnect()
    assert disconnected.state is SessionPhase.IDLE
    assert disconnected.active_session is None
    assert session_backend.disconnect_calls == [session_id]


# ---------------------------------------------------------------------------
# Test 2 – Connect with OTP challenge → submit input → connect succeeds
# ---------------------------------------------------------------------------


def test_connect_with_otp_challenge_submit_and_succeed() -> None:
    """
    When the backend reports WAITING_FOR_INPUT during prepare, the service
    should expose the attention request and block connect.  After the OTP is
    submitted and the backend clears the requirement, calling connect() again
    should complete successfully.
    """
    session_backend = FakeSessionBackend(requires_input=True)
    attention_backend = FakeAttentionBackend()
    service = _make_service(session_backend, attention_backend)

    # First connect attempt – prepare_session returns WAITING_FOR_INPUT
    waiting = service.connect("profile-1")
    assert waiting.state is SessionPhase.WAITING_FOR_INPUT
    assert len(waiting.attention_requests) == 1
    assert waiting.attention_requests[0].field_id == "otp"

    # Backend accepts the OTP; next prepare returns READY
    session_backend.requires_input = False
    ready = service.submit_attention_input("otp", "987654")

    assert attention_backend.submissions == [
        (waiting.active_session.id, "otp", "987654")
    ]
    assert ready.state is SessionPhase.READY

    # Now connect can proceed
    connected = service.connect()
    assert connected.state is SessionPhase.CONNECTED
    assert connected.attention_requests == ()


# ---------------------------------------------------------------------------
# Test 3 – Connect records last profile via AppStateBackend
# ---------------------------------------------------------------------------


def test_connect_records_last_profile_via_app_state_backend() -> None:
    """
    SessionLifecycleService must call app_state.record_connected_profile()
    with the correct profile id after a successful connection.
    """
    session_backend = FakeSessionBackend(profile_id="profile-42")
    attention_backend = FakeAttentionBackend()
    app_state = FakeAppStateBackend()
    service = _make_service(session_backend, attention_backend, app_state=app_state)

    snapshot = service.connect("profile-42")

    assert snapshot.state is SessionPhase.CONNECTED
    assert app_state.recorded_profiles == ["profile-42"]


def test_connect_does_not_record_profile_when_connection_fails() -> None:
    """
    If the backend returns a non-CONNECTED state (e.g. CONNECTING), the profile
    should NOT be recorded because the connection is not yet established.
    """
    session_backend = FakeSessionBackend(
        connect_state=SessionPhase.CONNECTING,
        prepare_state_after_submit=SessionPhase.READY,
    )
    attention_backend = FakeAttentionBackend()
    app_state = FakeAppStateBackend()
    service = _make_service(session_backend, attention_backend, app_state=app_state)

    snapshot = service.connect("profile-1")

    assert snapshot.state is SessionPhase.CONNECTING
    assert app_state.recorded_profiles == []


# ---------------------------------------------------------------------------
# Test 4 – Saved password auto-submitted
# ---------------------------------------------------------------------------


def test_saved_password_auto_submitted_on_single_password_prompt() -> None:
    """
    When a single password-style attention request is detected and a saved
    password is present, SessionLifecycleService should auto-submit it
    without requiring explicit user input.
    """
    session_backend = FakeSessionBackend(
        requires_input=True,
        prepare_state_after_submit=SessionPhase.READY,
    )
    attention_backend = FakePasswordAttentionBackend(
        session_backend, accept_saved_input=True
    )
    profile_secrets = ProfileSecretsService(MemorySecretStore())
    profile_secrets.save_password("profile-1", "s3cr3t")
    service = _make_service(
        session_backend,
        attention_backend,
        profile_credentials=profile_secrets,
    )

    snapshot = service.prepare_connection("profile-1")

    # The saved password must have been auto-submitted once.
    assert attention_backend.submissions == [("session-1", "password", "s3cr3t")]
    # After auto-submission the session should be READY without manual input.
    assert snapshot.state is SessionPhase.READY
    # No pending attention requests should remain.
    assert snapshot.attention_requests == ()


def test_saved_password_not_auto_submitted_when_no_password_saved() -> None:
    """
    When there is no saved password the service must NOT call provide_user_input
    and must leave the session in WAITING_FOR_INPUT.
    """
    session_backend = FakeSessionBackend(requires_input=True)
    attention_backend = FakePasswordAttentionBackend(
        session_backend, accept_saved_input=False
    )
    # No password saved.
    profile_secrets = ProfileSecretsService(MemorySecretStore())
    service = _make_service(
        session_backend,
        attention_backend,
        profile_credentials=profile_secrets,
    )

    snapshot = service.prepare_connection("profile-1")

    assert attention_backend.submissions == []
    assert snapshot.state is SessionPhase.WAITING_FOR_INPUT


def test_saved_password_attempted_only_once_per_session() -> None:
    """
    The service must not re-submit the saved password if the backend still
    demands input after the first attempt (wrong password scenario).
    """
    session_backend = FakeSessionBackend(requires_input=True)
    # accept_saved_input=False → backend keeps requiring input after submission
    attention_backend = FakePasswordAttentionBackend(
        session_backend, accept_saved_input=False
    )
    profile_secrets = ProfileSecretsService(MemorySecretStore())
    profile_secrets.save_password("profile-1", "wrong-password")
    service = _make_service(
        session_backend,
        attention_backend,
        profile_credentials=profile_secrets,
    )

    first = service.prepare_connection("profile-1")
    assert first.state is SessionPhase.WAITING_FOR_INPUT

    # Simulate backend pushing another WAITING_FOR_INPUT update.
    service.watch_active_session(lambda _s: None)
    assert session_backend._subscriber is not None
    session_backend._subscriber(
        SessionDescriptor(
            id="session-1",
            profile_id="profile-1",
            state=SessionPhase.WAITING_FOR_INPUT,
            requires_input=True,
        )
    )

    # The password must have been submitted exactly once (not twice).
    assert len(attention_backend.submissions) == 1
    assert attention_backend.submissions[0] == ("session-1", "password", "wrong-password")


# ---------------------------------------------------------------------------
# Test 5 – Restart cycle
# ---------------------------------------------------------------------------


def test_restart_cycle_connect_then_restart() -> None:
    """
    After a successful connection, calling restart() should invoke the backend's
    restart method.  The state machine stays within the CONNECTED/RECONNECTING
    graph; the exact resulting phase depends on what _sync_state can map from
    the backend descriptor, so we only assert the invariants that must hold.
    """
    # Configure the backend so that restart() returns RECONNECTING, which IS
    # a valid transition from CONNECTED in the state machine.
    session_backend = FakeSessionBackend()
    # Override restart to return RECONNECTING
    _orig_restart = session_backend.restart

    def _reconnecting_restart(session_id: str) -> SessionDescriptor:
        session_backend.restart_calls.append(session_id)
        return SessionDescriptor(
            id=session_id,
            profile_id=session_backend.profile_id,
            state=SessionPhase.RECONNECTING,
        )

    session_backend.restart = _reconnecting_restart  # type: ignore[method-assign]

    attention_backend = FakeAttentionBackend()
    service = _make_service(session_backend, attention_backend)

    connected = service.connect("profile-1")
    assert connected.state is SessionPhase.CONNECTED
    session_id = connected.active_session.id

    restarted = service.restart()

    assert restarted.active_session is not None
    assert restarted.active_session.id == session_id
    assert session_backend.restart_calls == [session_id]
    # CONNECTED → RECONNECTING is a valid state-machine transition
    assert restarted.state is SessionPhase.RECONNECTING


def test_restart_does_nothing_without_active_session() -> None:
    """restart() on an idle service must be a no-op."""
    session_backend = FakeSessionBackend()
    attention_backend = FakeAttentionBackend()
    service = _make_service(session_backend, attention_backend)

    snapshot = service.restart()

    assert snapshot.state is SessionPhase.IDLE
    assert snapshot.active_session is None
    assert session_backend.restart_calls == []


# ---------------------------------------------------------------------------
# Additional lifecycle edge-case tests
# ---------------------------------------------------------------------------


def test_disconnect_when_idle_is_a_noop() -> None:
    """disconnect() without an active session must not raise and stay IDLE."""
    service = _make_service(FakeSessionBackend(), FakeAttentionBackend())

    snapshot = service.disconnect()

    assert snapshot.state is SessionPhase.IDLE
    assert snapshot.active_session is None


def test_pause_and_resume_without_active_session_are_noops() -> None:
    """pause/resume without an active session must not raise."""
    service = _make_service(FakeSessionBackend(), FakeAttentionBackend())

    assert service.pause().state is SessionPhase.IDLE
    assert service.resume().state is SessionPhase.IDLE


def test_app_state_record_called_once_per_connect() -> None:
    """record_connected_profile is called exactly once per successful connect."""
    session_backend = FakeSessionBackend()
    attention_backend = FakeAttentionBackend()
    app_state = FakeAppStateBackend()
    service = _make_service(session_backend, attention_backend, app_state=app_state)

    service.connect("profile-1")
    # Already connected — a second connect("profile-1") is a no-op
    service.connect("profile-1")

    assert app_state.recorded_profiles == ["profile-1"]


def test_connect_different_profile_creates_new_session() -> None:
    """
    Connecting to a different profile after disconnecting should create
    a brand-new session and call record_connected_profile with the new id.

    Note: the state machine does not allow SELECT_PROFILE from CONNECTED, so
    the caller must first disconnect before connecting to a different profile.
    """
    session_backend = FakeSessionBackend()
    attention_backend = FakeAttentionBackend()
    app_state = FakeAppStateBackend()
    service = _make_service(session_backend, attention_backend, app_state=app_state)

    first = service.connect("profile-1")
    assert first.state is SessionPhase.CONNECTED

    # Disconnect before switching profile
    service.disconnect()

    # Switch backend to serve profile-2
    session_backend.profile_id = "profile-2"
    second = service.connect("profile-2")
    assert second.state is SessionPhase.CONNECTED
    assert second.active_session is not None
    assert second.active_session.profile_id == "profile-2"

    assert app_state.recorded_profiles == ["profile-1", "profile-2"]


def test_select_profile_then_connect_succeeds() -> None:
    """select_profile + connect should result in a CONNECTED snapshot."""
    session_backend = FakeSessionBackend()
    attention_backend = FakeAttentionBackend()
    service = _make_service(session_backend, attention_backend)

    service.select_profile("profile-1")
    snapshot = service.connect("profile-1")

    assert snapshot.state is SessionPhase.CONNECTED
    assert snapshot.selected_profile_id == "profile-1"


def test_error_reset_and_reconnect() -> None:
    """After an error the service can be reset and successfully reconnected."""
    from core.session_manager import SessionLifecycleService
    from core.state_machine import SessionStateMachine
    from core.events import SessionEvent

    # Force the service into ERROR via a session that reports ERROR state
    error_backend = FakeSessionBackend()
    attention_backend = FakeAttentionBackend()
    service = SessionLifecycleService(error_backend, attention_backend)

    # Manually push state machine into error
    service._state_machine.apply(SessionEvent.SELECT_PROFILE, profile_id="profile-1")
    service._state_machine.apply(SessionEvent.CREATE_SESSION, session_id="s-tmp")
    service._state_machine.apply(SessionEvent.MARK_READY)
    service._state_machine.apply(SessionEvent.REQUEST_CONNECT)
    service._state_machine.apply(SessionEvent.FAIL, reason="Simulated failure")

    assert service.snapshot().state is SessionPhase.ERROR

    reset = service.reset_error()
    assert reset.state is SessionPhase.IDLE
    assert reset.last_error is None

    reconnected = service.connect("profile-1")
    assert reconnected.state is SessionPhase.CONNECTED
