from core.events import SessionEvent
from core.models import SessionPhase
from core.state_machine import InvalidStateTransitionError, SessionStateMachine


def test_session_state_machine_happy_path() -> None:
    machine = SessionStateMachine()

    machine.apply(SessionEvent.SELECT_PROFILE, profile_id="profile-1")
    machine.apply(SessionEvent.CREATE_SESSION, session_id="session-1")
    machine.apply(SessionEvent.MARK_READY)
    machine.apply(SessionEvent.REQUEST_CONNECT)
    machine.apply(SessionEvent.MARK_CONNECTED)
    machine.apply(SessionEvent.REQUEST_DISCONNECT)
    machine.apply(SessionEvent.MARK_DISCONNECTED)

    assert machine.state is SessionPhase.IDLE
    assert machine.selected_profile_id == "profile-1"
    assert machine.active_session_id is None


def test_session_state_machine_rejects_invalid_transition() -> None:
    machine = SessionStateMachine()

    try:
        machine.apply(SessionEvent.REQUEST_CONNECT)
    except InvalidStateTransitionError as exc:
        assert "request_connect" in str(exc)
    else:
        raise AssertionError("Expected InvalidStateTransitionError")


def test_session_state_machine_fail_transitions_to_error() -> None:
    machine = SessionStateMachine()

    machine.apply(SessionEvent.FAIL, reason="Authentication failed")

    assert machine.state is SessionPhase.ERROR
    assert machine.last_error == "Authentication failed"

