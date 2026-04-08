from datetime import datetime, timedelta, timezone

from core.models import SessionDescriptor, SessionPhase, SessionTelemetrySample
from core.telemetry import SessionTelemetryService


class FakeTelemetryBackend:
    def __init__(self, samples: list[SessionTelemetrySample]) -> None:
        self._samples = list(samples)

    def get_session_telemetry(self, session_id: str) -> SessionTelemetrySample:
        sample = self._samples.pop(0)
        assert sample.session_id == session_id
        return sample


def test_telemetry_service_calculates_rates_and_history() -> None:
    now = datetime.now(timezone.utc)
    backend = FakeTelemetryBackend(
        [
            SessionTelemetrySample(
                session_id="session-1",
                bytes_in=1024,
                bytes_out=2048,
                packets_in=10,
                packets_out=12,
                updated_at=now,
                available=True,
            ),
            SessionTelemetrySample(
                session_id="session-1",
                bytes_in=3072,
                bytes_out=4096,
                packets_in=30,
                packets_out=24,
                updated_at=now + timedelta(seconds=2),
                available=True,
            ),
        ]
    )
    service = SessionTelemetryService(backend)
    session = SessionDescriptor(
        id="session-1",
        profile_id="profile-1",
        state=SessionPhase.CONNECTED,
    )

    first = service.snapshot(session)
    second = service.snapshot(session)

    assert first is not None
    assert first.rx_rate_bps is None
    assert second is not None
    assert second.rx_rate_bps == 1024.0
    assert second.tx_rate_bps == 1024.0
    assert len(second.history) == 2


def test_telemetry_service_keeps_unavailable_sample_detail() -> None:
    backend = FakeTelemetryBackend(
        [
            SessionTelemetrySample(
                session_id="session-1",
                updated_at=datetime.now(timezone.utc),
                available=False,
                detail="Session telemetry is not exposed by the backend.",
            )
        ]
    )
    service = SessionTelemetryService(backend)
    session = SessionDescriptor(
        id="session-1",
        profile_id="profile-1",
        state=SessionPhase.CONNECTING,
    )

    snapshot = service.snapshot(session)

    assert snapshot is not None
    assert snapshot.sample.available is False
    assert snapshot.sample.detail == "Session telemetry is not exposed by the backend."
