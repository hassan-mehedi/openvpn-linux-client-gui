import pytest

from core.models import (
    AppSettings,
    AttentionFieldType,
    AttentionRequest,
    SessionDescriptor,
    SessionPhase,
)
from core.session_manager import SessionLifecycleService
from core.secrets import MemorySecretStore, ProfileSecretsService


class FakeSessionBackend:
    def __init__(self, *, requires_input: bool = False) -> None:
        self.requires_input = requires_input
        self.created = 0
        self.connect_state = SessionPhase.CONNECTED
        self.status_state = SessionPhase.CONNECTED
        self.subscriber = None
        self.sessions: list[SessionDescriptor] = []
        self.disconnect_calls: list[str] = []

    def list_sessions(self) -> tuple[SessionDescriptor, ...]:
        return tuple(self.sessions)

    def create_session(self, profile_id: str) -> SessionDescriptor:
        self.created += 1
        return SessionDescriptor(
            id=f"session-{self.created}",
            profile_id=profile_id,
            state=SessionPhase.SESSION_CREATED,
        )

    def prepare_session(self, session_id: str) -> SessionDescriptor:
        return SessionDescriptor(
            id=session_id,
            profile_id="profile-1",
            state=SessionPhase.WAITING_FOR_INPUT if self.requires_input else SessionPhase.READY,
            requires_input=self.requires_input,
        )

    def connect(self, session_id: str) -> SessionDescriptor:
        return SessionDescriptor(
            id=session_id,
            profile_id="profile-1",
            state=self.connect_state,
        )

    def disconnect(self, session_id: str) -> SessionDescriptor:
        self.disconnect_calls.append(session_id)
        return SessionDescriptor(
            id=session_id,
            profile_id="profile-1",
            state=SessionPhase.IDLE,
        )

    def pause(self, session_id: str) -> SessionDescriptor:
        return SessionDescriptor(
            id=session_id,
            profile_id="profile-1",
            state=SessionPhase.PAUSED,
        )

    def resume(self, session_id: str) -> SessionDescriptor:
        return SessionDescriptor(
            id=session_id,
            profile_id="profile-1",
            state=SessionPhase.CONNECTED,
        )

    def restart(self, session_id: str) -> SessionDescriptor:
        return SessionDescriptor(
            id=session_id,
            profile_id="profile-1",
            state=SessionPhase.READY,
        )

    def get_session_status(self, session_id: str) -> SessionDescriptor:
        return SessionDescriptor(
            id=session_id,
            profile_id="profile-1",
            state=self.status_state,
        )

    def subscribe_to_updates(self, session_id: str, callback):
        self.subscriber = callback
        return lambda: None


class FakeAttentionBackend:
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


class FakeConnectionPreparationBackend:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.prepared_profile_ids: list[str] = []

    def prepare_profile(self, profile_id: str) -> None:
        if self.error is not None:
            raise self.error
        self.prepared_profile_ids.append(profile_id)


class FakeSettingsBackend:
    def __init__(self, timeout: int) -> None:
        self.timeout = timeout

    def load(self) -> AppSettings:
        return AppSettings(connection_timeout=self.timeout)


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class FakePasswordAttentionBackend(FakeAttentionBackend):
    def __init__(
        self,
        session_backend: FakeSessionBackend,
        *,
        accept_saved_input: bool,
    ) -> None:
        super().__init__()
        self._session_backend = session_backend
        self._accept_saved_input = accept_saved_input

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
        super().provide_user_input(session_id, field_id, value)
        if self._accept_saved_input:
            self._session_backend.requires_input = False


def test_session_lifecycle_connects_without_attention() -> None:
    service = SessionLifecycleService(FakeSessionBackend(), FakeAttentionBackend())

    snapshot = service.connect("profile-1")

    assert snapshot.state is SessionPhase.CONNECTED
    assert snapshot.active_session is not None
    assert snapshot.active_session.profile_id == "profile-1"


def test_session_lifecycle_prepares_profile_before_creating_session() -> None:
    connection_preparation = FakeConnectionPreparationBackend()
    service = SessionLifecycleService(
        FakeSessionBackend(),
        FakeAttentionBackend(),
        connection_preparation=connection_preparation,
    )

    snapshot = service.prepare_connection("profile-1")

    assert connection_preparation.prepared_profile_ids == ["profile-1"]
    assert snapshot.active_session is not None
    assert snapshot.active_session.id == "session-1"


def test_session_lifecycle_marks_error_when_profile_preparation_fails() -> None:
    service = SessionLifecycleService(
        FakeSessionBackend(),
        FakeAttentionBackend(),
        connection_preparation=FakeConnectionPreparationBackend(
            error=RuntimeError("Assigned proxy is missing.")
        ),
    )

    with pytest.raises(RuntimeError, match="Assigned proxy is missing."):
        service.prepare_connection("profile-1")

    snapshot = service.snapshot()
    assert snapshot.state is SessionPhase.ERROR
    assert snapshot.last_error == "Assigned proxy is missing."


def test_session_lifecycle_can_retry_after_profile_preparation_error() -> None:
    connection_preparation = FakeConnectionPreparationBackend(
        error=RuntimeError("Assigned proxy is missing.")
    )
    service = SessionLifecycleService(
        FakeSessionBackend(),
        FakeAttentionBackend(),
        connection_preparation=connection_preparation,
    )

    with pytest.raises(RuntimeError, match="Assigned proxy is missing."):
        service.prepare_connection("profile-1")

    connection_preparation.error = None
    snapshot = service.prepare_connection("profile-1")

    assert snapshot.state is SessionPhase.READY
    assert connection_preparation.prepared_profile_ids == ["profile-1"]


def test_session_lifecycle_can_reset_error_state_without_losing_selection() -> None:
    service = SessionLifecycleService(
        FakeSessionBackend(),
        FakeAttentionBackend(),
        connection_preparation=FakeConnectionPreparationBackend(
            error=RuntimeError("Assigned proxy is missing.")
        ),
    )

    with pytest.raises(RuntimeError, match="Assigned proxy is missing."):
        service.prepare_connection("profile-1")

    reset = service.reset_error()

    assert reset.state is SessionPhase.IDLE
    assert reset.active_session is None
    assert reset.last_error is None
    assert reset.selected_profile_id == "profile-1"


def test_session_lifecycle_waits_for_input_and_resumes() -> None:
    session_backend = FakeSessionBackend(requires_input=True)
    attention_backend = FakeAttentionBackend()
    service = SessionLifecycleService(session_backend, attention_backend)

    waiting = service.prepare_connection("profile-1")

    assert waiting.state is SessionPhase.WAITING_FOR_INPUT
    assert waiting.attention_requests[0].field_id == "otp"

    session_backend.requires_input = False
    ready = service.submit_attention_input("otp", "123456")

    assert attention_backend.submissions == [("session-1", "otp", "123456")]
    assert ready.state is SessionPhase.READY


def test_session_lifecycle_batches_required_inputs() -> None:
    session_backend = FakeSessionBackend(requires_input=True)
    attention_backend = FakeAttentionBackend()
    service = SessionLifecycleService(session_backend, attention_backend)

    service.prepare_connection("profile-1")

    ready = service.submit_attention_inputs({"otp": "654321"})

    assert ready.state is SessionPhase.WAITING_FOR_INPUT
    session_backend.requires_input = False
    ready = service.submit_attention_inputs({"otp": "654321"})

    assert ready.state is SessionPhase.READY


def test_session_lifecycle_refreshes_backend_state() -> None:
    session_backend = FakeSessionBackend()
    service = SessionLifecycleService(session_backend, FakeAttentionBackend())

    service.connect("profile-1")
    session_backend.status_state = SessionPhase.RECONNECTING

    snapshot = service.refresh_status()

    assert snapshot.state is SessionPhase.RECONNECTING


def test_session_lifecycle_enforces_connection_timeout_budget() -> None:
    session_backend = FakeSessionBackend()
    session_backend.connect_state = SessionPhase.CONNECTING
    session_backend.status_state = SessionPhase.CONNECTING
    session_backend.sessions = [
        SessionDescriptor(
            id="session-1",
            profile_id="profile-1",
            state=SessionPhase.CONNECTING,
        )
    ]
    clock = FakeClock(now=100.0)
    service = SessionLifecycleService(
        session_backend,
        FakeAttentionBackend(),
        settings_backend=FakeSettingsBackend(timeout=5),
        monotonic_now=clock,
    )

    connecting = service.connect("profile-1")
    assert connecting.state is SessionPhase.CONNECTING

    clock.now = 106.0
    timed_out = service.refresh_status()

    assert timed_out.state is SessionPhase.ERROR
    assert timed_out.active_session is None
    assert timed_out.last_error == "Connection timed out after 5 seconds."
    assert session_backend.disconnect_calls == ["session-1"]
    assert service.restore_existing_session("profile-1").state is SessionPhase.ERROR


def test_session_lifecycle_pauses_timeout_while_waiting_for_input() -> None:
    session_backend = FakeSessionBackend()
    session_backend.connect_state = SessionPhase.WAITING_FOR_INPUT
    session_backend.status_state = SessionPhase.WAITING_FOR_INPUT
    clock = FakeClock(now=10.0)
    service = SessionLifecycleService(
        session_backend,
        FakeAttentionBackend(),
        settings_backend=FakeSettingsBackend(timeout=5),
        monotonic_now=clock,
    )

    waiting = service.connect("profile-1")
    assert waiting.state is SessionPhase.WAITING_FOR_INPUT

    clock.now = 20.0
    refreshed = service.refresh_status()

    assert refreshed.state is SessionPhase.WAITING_FOR_INPUT
    assert refreshed.last_error is None
    assert session_backend.disconnect_calls == []


def test_session_lifecycle_enforces_connection_timeout_during_reconnect() -> None:
    session_backend = FakeSessionBackend()
    session_backend.sessions = [
        SessionDescriptor(
            id="session-1",
            profile_id="profile-1",
            state=SessionPhase.CONNECTED,
        )
    ]
    clock = FakeClock(now=50.0)
    service = SessionLifecycleService(
        session_backend,
        FakeAttentionBackend(),
        settings_backend=FakeSettingsBackend(timeout=5),
        monotonic_now=clock,
    )

    connected = service.restore_existing_session("profile-1")
    assert connected.state is SessionPhase.CONNECTED

    session_backend.status_state = SessionPhase.RECONNECTING
    reconnecting = service.refresh_status()
    assert reconnecting.state is SessionPhase.RECONNECTING

    clock.now = 56.0
    timed_out = service.refresh_status()

    assert timed_out.state is SessionPhase.ERROR
    assert timed_out.active_session is None
    assert timed_out.last_error == "Connection timed out after 5 seconds."
    assert session_backend.disconnect_calls == ["session-1"]


def test_session_lifecycle_watches_active_session_updates() -> None:
    session_backend = FakeSessionBackend()
    service = SessionLifecycleService(session_backend, FakeAttentionBackend())
    service.connect("profile-1")

    snapshots = []
    service.watch_active_session(snapshots.append)

    assert session_backend.subscriber is not None
    session_backend.subscriber(
        SessionDescriptor(
            id="session-1",
            profile_id="profile-1",
            state=SessionPhase.CONNECTED,
            status_message="Connected",
        )
    )

    assert snapshots[-1].state is SessionPhase.CONNECTED


def test_session_lifecycle_restores_existing_session() -> None:
    session_backend = FakeSessionBackend()
    session_backend.sessions = [
        SessionDescriptor(
            id="session-existing",
            profile_id="profile-1",
            state=SessionPhase.CONNECTED,
            status_message="Connected",
        )
    ]
    service = SessionLifecycleService(session_backend, FakeAttentionBackend())

    snapshot = service.restore_existing_session("profile-1")

    assert snapshot.state is SessionPhase.CONNECTED
    assert snapshot.active_session is not None
    assert snapshot.active_session.id == "session-existing"


def test_session_lifecycle_auto_submits_saved_password_and_advances() -> None:
    session_backend = FakeSessionBackend(requires_input=True)
    attention_backend = FakePasswordAttentionBackend(
        session_backend,
        accept_saved_input=True,
    )
    profile_secrets = ProfileSecretsService(MemorySecretStore())
    profile_secrets.save_password("profile-1", "secret")
    service = SessionLifecycleService(
        session_backend,
        attention_backend,
        profile_credentials=profile_secrets,
    )

    snapshot = service.prepare_connection("profile-1")

    assert attention_backend.submissions == [("session-1", "password", "secret")]
    assert snapshot.state is SessionPhase.READY
    assert snapshot.attention_requests == ()


def test_session_lifecycle_saved_password_attempts_only_once_per_session() -> None:
    session_backend = FakeSessionBackend(requires_input=True)
    attention_backend = FakePasswordAttentionBackend(
        session_backend,
        accept_saved_input=False,
    )
    profile_secrets = ProfileSecretsService(MemorySecretStore())
    profile_secrets.save_password("profile-1", "secret")
    service = SessionLifecycleService(
        session_backend,
        attention_backend,
        profile_credentials=profile_secrets,
    )

    first = service.prepare_connection("profile-1")
    service.watch_active_session(lambda _snapshot: None)
    assert session_backend.subscriber is not None
    session_backend.subscriber(
        SessionDescriptor(
            id="session-1",
            profile_id="profile-1",
            state=SessionPhase.WAITING_FOR_INPUT,
            requires_input=True,
        )
    )

    assert first.state is SessionPhase.WAITING_FOR_INPUT
    assert attention_backend.submissions == [("session-1", "password", "secret")]
