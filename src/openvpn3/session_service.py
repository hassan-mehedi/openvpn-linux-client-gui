"""OpenVPN 3 session service adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from core.models import SessionDescriptor, SessionPhase, SessionTelemetrySample
from openvpn3.dbus_client import (
    SESSION_SERVICE_NAME,
    DBusClient,
    opaque_identifier,
)


SESSION_INTERFACE = "net.openvpn.v3.sessions"
SESSION_MANAGER_PATH = "/net/openvpn/v3/sessions"


class SessionService:
    def __init__(
        self,
        client: DBusClient,
        *,
        profile_resolver: Callable[[str], str],
        profile_id_from_path: Callable[[str], str | None] | None = None,
    ) -> None:
        self._client = client
        self._profile_resolver = profile_resolver
        self._profile_id_from_path = profile_id_from_path
        self._session_paths: dict[str, str] = {}

    def create_session(self, profile_id: str) -> SessionDescriptor:
        profile_path = self._profile_resolver(profile_id)
        response = self._client.call_method(
            service=SESSION_SERVICE_NAME,
            object_path=SESSION_MANAGER_PATH,
            interface=SESSION_INTERFACE,
            method="NewTunnel",
            signature="o",
            params=(profile_path,),
        )
        return self._descriptor_from_path(str(response), profile_id=profile_id)

    def prepare_session(self, session_id: str) -> SessionDescriptor:
        self._invoke_session_method(session_id, "Ready")
        return self.get_session_status(session_id)

    def connect(self, session_id: str) -> SessionDescriptor:
        self._invoke_session_method(session_id, "Connect")
        return self.get_session_status(session_id)

    def disconnect(self, session_id: str) -> SessionDescriptor:
        descriptor = self.get_session_status(session_id)
        self._invoke_session_method(session_id, "Disconnect")
        self._session_paths.pop(session_id, None)
        return SessionDescriptor(
            id=session_id,
            profile_id=descriptor.profile_id,
            state=SessionPhase.IDLE,
            status_message="Disconnected",
            requires_input=False,
            created_at=descriptor.created_at,
            updated_at=datetime.now(timezone.utc),
        )

    def pause(self, session_id: str) -> SessionDescriptor:
        self._invoke_session_method(session_id, "Pause", signature="s", params=("User request",))
        return self.get_session_status(session_id)

    def resume(self, session_id: str) -> SessionDescriptor:
        self._invoke_session_method(session_id, "Resume")
        return self.get_session_status(session_id)

    def restart(self, session_id: str) -> SessionDescriptor:
        self._invoke_session_method(session_id, "Restart")
        return self.get_session_status(session_id)

    def get_session_status(self, session_id: str) -> SessionDescriptor:
        return self._descriptor_from_path(self.resolve_object_path(session_id), session_id=session_id)

    def get_session_telemetry(self, session_id: str) -> SessionTelemetrySample:
        object_path = self.resolve_object_path(session_id)
        properties = self._client.get_all_properties(
            service=SESSION_SERVICE_NAME,
            object_path=object_path,
            interface=SESSION_INTERFACE,
        )
        statistics = _statistics_mapping(properties)
        bytes_in = _pick_int(
            properties,
            "bytes_in",
            "bytes_received",
            "received_bytes",
            "rx_bytes",
            "session_bytes_in",
            fallback=statistics,
            fallback_keys=("BYTES_IN", "TUN_BYTES_IN"),
        )
        bytes_out = _pick_int(
            properties,
            "bytes_out",
            "bytes_sent",
            "sent_bytes",
            "tx_bytes",
            "session_bytes_out",
            fallback=statistics,
            fallback_keys=("BYTES_OUT", "TUN_BYTES_OUT"),
        )
        packets_in = _pick_int(
            properties,
            "packets_in",
            "packets_received",
            "received_packets",
            "rx_packets",
            fallback=statistics,
            fallback_keys=("PACKETS_IN", "TUN_PACKETS_IN"),
        )
        packets_out = _pick_int(
            properties,
            "packets_out",
            "packets_sent",
            "sent_packets",
            "tx_packets",
            fallback=statistics,
            fallback_keys=("PACKETS_OUT", "TUN_PACKETS_OUT"),
        )
        latency_ms = _pick_float(
            properties,
            "latency_ms",
            "server_latency_ms",
            "ping_time_ms",
            "rtt_ms",
        )
        last_packet_received_at = _pick_timestamp(
            properties,
            "last_packet_received",
            "last_packet_received_at",
            "rx_last_packet",
        )
        last_packet_sent_at = _pick_timestamp(
            properties,
            "last_packet_sent",
            "last_packet_sent_at",
            "tx_last_packet",
        )
        available = any(
            value is not None
            for value in (
                bytes_in,
                bytes_out,
                packets_in,
                packets_out,
                latency_ms,
                last_packet_received_at,
                last_packet_sent_at,
            )
        )
        return SessionTelemetrySample(
            session_id=session_id,
            bytes_in=bytes_in,
            bytes_out=bytes_out,
            packets_in=packets_in,
            packets_out=packets_out,
            latency_ms=latency_ms,
            last_packet_received_at=last_packet_received_at,
            last_packet_sent_at=last_packet_sent_at,
            updated_at=datetime.now(timezone.utc),
            available=available,
            detail=_telemetry_detail(
                available=available,
                statistics=statistics,
                latency_ms=latency_ms,
                last_packet_received_at=last_packet_received_at,
                last_packet_sent_at=last_packet_sent_at,
            ),
        )

    def list_sessions(self) -> tuple[SessionDescriptor, ...]:
        payload = self._client.call_method(
            service=SESSION_SERVICE_NAME,
            object_path=SESSION_MANAGER_PATH,
            interface=SESSION_INTERFACE,
            method="FetchAvailableSessions",
        ) or []
        return tuple(self._descriptor_from_path(str(path)) for path in payload)

    def subscribe_to_updates(
        self, session_id: str, callback: Callable[[SessionDescriptor], None]
    ) -> Callable[[], None]:
        object_path = self.resolve_object_path(session_id)
        last_known = self.get_session_status(session_id)

        def wrapped(_payload: Any) -> None:
            try:
                callback(self.get_session_status(session_id))
            except Exception:
                callback(
                    SessionDescriptor(
                        id=session_id,
                        profile_id=last_known.profile_id,
                        state=SessionPhase.IDLE,
                        status_message="Disconnected",
                        requires_input=False,
                        created_at=last_known.created_at,
                    )
                )

        return self._client.subscribe_signal(
            service=SESSION_SERVICE_NAME,
            object_path=object_path,
            interface=SESSION_INTERFACE,
            signal_name="StatusChange",
            callback=wrapped,
        )

    def resolve_object_path(self, session_id: str) -> str:
        try:
            return self._session_paths[session_id]
        except KeyError as exc:
            raise KeyError(f"Unknown session identifier: {session_id}") from exc

    def _invoke_session_method(
        self,
        session_id: str,
        method: str,
        *,
        signature: str | None = None,
        params: Any | None = None,
    ) -> Any:
        object_path = self.resolve_object_path(session_id)
        return self._client.call_method(
            service=SESSION_SERVICE_NAME,
            object_path=object_path,
            interface=SESSION_INTERFACE,
            method=method,
            signature=signature,
            params=params,
        )

    def _descriptor_from_path(
        self,
        object_path: str,
        *,
        profile_id: str | None = None,
        session_id: str | None = None,
    ) -> SessionDescriptor:
        mapped_session_id = session_id or opaque_identifier("session", object_path)
        self._session_paths[mapped_session_id] = object_path
        properties = self._client.get_all_properties(
            service=SESSION_SERVICE_NAME,
            object_path=object_path,
            interface=SESSION_INTERFACE,
        )
        status_major, status_minor, status_message = properties.get("status", (0, 0, ""))
        config_path = str(properties.get("config_path", ""))
        return SessionDescriptor(
            id=mapped_session_id,
            profile_id=profile_id
            or self._resolve_profile_id_from_path(config_path)
            or str(properties.get("config_name", "")),
            state=_map_status_to_phase(int(status_major), int(status_minor)),
            status_message=str(status_message),
            requires_input=bool(self._requires_input(object_path, int(status_minor))),
            created_at=_parse_timestamp(properties.get("session_created"))
            or datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def _resolve_profile_id_from_path(self, config_path: str) -> str | None:
        if not config_path or self._profile_id_from_path is None:
            return None
        return self._profile_id_from_path(config_path)

    def _requires_input(self, object_path: str, status_minor: int) -> bool:
        if status_minor in {20, 21, 22}:
            return True
        queue_groups = self._client.call_method(
            service=SESSION_SERVICE_NAME,
            object_path=object_path,
            interface=SESSION_INTERFACE,
            method="UserInputQueueGetTypeGroup",
        )
        return bool(queue_groups)


def _parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return datetime.fromisoformat(str(value))


def _pick_value(
    properties: dict[str, Any],
    *keys: str,
    fallback: dict[str, Any] | None = None,
    fallback_keys: tuple[str, ...] = (),
) -> Any:
    for key in keys:
        if key in properties and properties[key] not in (None, ""):
            return properties[key]
    if fallback:
        for key in fallback_keys:
            if key in fallback and fallback[key] not in (None, ""):
                return fallback[key]
    return None


def _pick_int(
    properties: dict[str, Any],
    *keys: str,
    fallback: dict[str, Any] | None = None,
    fallback_keys: tuple[str, ...] = (),
) -> int | None:
    value = _pick_value(
        properties,
        *keys,
        fallback=fallback,
        fallback_keys=fallback_keys,
    )
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pick_float(properties: dict[str, Any], *keys: str) -> float | None:
    value = _pick_value(properties, *keys)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_timestamp(properties: dict[str, Any], *keys: str) -> datetime | None:
    value = _pick_value(properties, *keys)
    if value is None:
        return None
    try:
        return _parse_timestamp(value)
    except (TypeError, ValueError):
        return None


def _statistics_mapping(properties: dict[str, Any]) -> dict[str, Any]:
    raw = properties.get("statistics")
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items()}


def _telemetry_detail(
    *,
    available: bool,
    statistics: dict[str, Any],
    latency_ms: float | None,
    last_packet_received_at: datetime | None,
    last_packet_sent_at: datetime | None,
) -> str | None:
    if not available:
        return "Session telemetry is not exposed by the backend."
    if statistics and (
        latency_ms is None
        and last_packet_received_at is None
        and last_packet_sent_at is None
    ):
        return (
            "Traffic counters are available from the backend. "
            "Latency and packet-age timestamps are not exposed for this session."
        )
    return None


def _map_status_to_phase(status_major: int, status_minor: int) -> SessionPhase:
    if status_minor in {17}:
        return SessionPhase.SESSION_CREATED
    if status_minor in {4, 20, 21, 22}:
        return SessionPhase.WAITING_FOR_INPUT
    if status_minor in {2}:
        return SessionPhase.READY
    if status_minor in {5, 6, 15}:
        return SessionPhase.CONNECTING
    if status_minor in {7}:
        return SessionPhase.CONNECTED
    if status_minor in {13, 14}:
        return SessionPhase.PAUSED
    if status_minor in {12}:
        return SessionPhase.RECONNECTING
    if status_minor in {8, 16, 18, 19, 28, 29}:
        return SessionPhase.DISCONNECTING
    if status_minor in {9}:
        return SessionPhase.IDLE
    if status_minor in {1, 3, 10, 11}:
        return SessionPhase.ERROR
    if status_major == 0:
        return SessionPhase.IDLE
    return SessionPhase.READY
