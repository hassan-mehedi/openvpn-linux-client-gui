from core.models import AttentionFieldType, AttentionRequest, SessionDescriptor, SessionPhase
from core.session_manager import SessionLifecycleService


class FakeSessionBackend:
    def __init__(self, *, requires_input: bool = False) -> None:
        self.requires_input = requires_input
        self.created = 0
        self.status_state = SessionPhase.CONNECTED
        self.subscriber = None
        self.sessions: list[SessionDescriptor] = []

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
            state=SessionPhase.CONNECTED,
        )

    def disconnect(self, session_id: str) -> SessionDescriptor:
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


def test_session_lifecycle_connects_without_attention() -> None:
    service = SessionLifecycleService(FakeSessionBackend(), FakeAttentionBackend())

    snapshot = service.connect("profile-1")

    assert snapshot.state is SessionPhase.CONNECTED
    assert snapshot.active_session is not None
    assert snapshot.active_session.profile_id == "profile-1"


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
