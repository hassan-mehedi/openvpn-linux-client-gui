"""Session telemetry aggregation and rate calculation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from core.models import (
    SessionDescriptor,
    SessionTelemetryPoint,
    SessionTelemetrySample,
    SessionTelemetrySnapshot,
)


class SessionTelemetryBackend(Protocol):
    def get_session_telemetry(self, session_id: str) -> SessionTelemetrySample:
        """Return the latest cumulative telemetry for a session."""


@dataclass(slots=True)
class _TelemetryState:
    previous: SessionTelemetrySample | None = None
    history: deque[SessionTelemetryPoint] | None = None

    def __post_init__(self) -> None:
        if self.history is None:
            self.history = deque(maxlen=30)


class SessionTelemetryService:
    """Application-facing session telemetry cache and history builder."""

    def __init__(
        self,
        backend: SessionTelemetryBackend,
        *,
        history_limit: int = 30,
    ) -> None:
        self._backend = backend
        self._history_limit = history_limit
        self._states: dict[str, _TelemetryState] = {}

    def snapshot(
        self,
        session: SessionDescriptor | None,
    ) -> SessionTelemetrySnapshot | None:
        if session is None:
            return None

        sample = self._backend.get_session_telemetry(session.id)
        state = self._states.get(session.id)
        if state is None:
            state = _TelemetryState(history=deque(maxlen=self._history_limit))
            self._states[session.id] = state

        rx_rate_bps, tx_rate_bps = _calculate_rates(state.previous, sample)
        if rx_rate_bps is not None or tx_rate_bps is not None:
            state.history.append(
                SessionTelemetryPoint(
                    captured_at=sample.updated_at,
                    rx_rate_bps=rx_rate_bps or 0.0,
                    tx_rate_bps=tx_rate_bps or 0.0,
                )
            )
        elif not state.history:
            state.history.append(
                SessionTelemetryPoint(
                    captured_at=sample.updated_at,
                    rx_rate_bps=0.0,
                    tx_rate_bps=0.0,
                )
            )

        state.previous = sample
        return SessionTelemetrySnapshot(
            sample=sample,
            rx_rate_bps=rx_rate_bps,
            tx_rate_bps=tx_rate_bps,
            history=tuple(state.history),
        )

    def clear_session(self, session_id: str) -> None:
        self._states.pop(session_id, None)


def _calculate_rates(
    previous: SessionTelemetrySample | None,
    current: SessionTelemetrySample,
) -> tuple[float | None, float | None]:
    if previous is None:
        return None, None
    delta_seconds = max(
        0.0,
        (current.updated_at - previous.updated_at).total_seconds(),
    )
    if delta_seconds <= 0:
        return None, None
    return (
        _rate(previous.bytes_in, current.bytes_in, delta_seconds),
        _rate(previous.bytes_out, current.bytes_out, delta_seconds),
    )


def _rate(previous: int | None, current: int | None, delta_seconds: float) -> float | None:
    if previous is None or current is None:
        return None
    if current < previous:
        return None
    return (current - previous) / delta_seconds
