from core.events import SessionEvent
from core.models import SessionPhase
from core.state_machine import SessionStateMachine


def test_session_state_machine_challenge_loop() -> None:
    machine = SessionStateMachine()

    machine.apply(SessionEvent.SELECT_PROFILE, profile_id="profile-1")
    machine.apply(SessionEvent.CREATE_SESSION, session_id="session-1")
    machine.apply(SessionEvent.REQUIRE_INPUT)
    machine.apply(SessionEvent.MARK_READY)
    machine.apply(SessionEvent.REQUEST_CONNECT)
    machine.apply(SessionEvent.MARK_CONNECTED)

    assert machine.state is SessionPhase.CONNECTED
