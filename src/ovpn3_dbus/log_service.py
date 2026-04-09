"""OpenVPN 3 log service adapter."""

from __future__ import annotations

from collections import deque
from typing import Callable

from ovpn3_dbus.dbus_client import DBusClient, SESSION_SERVICE_NAME


LOG_INTERFACE = "net.openvpn.v3.log"
SESSION_INTERFACE = "net.openvpn.v3.sessions"
_MAX_BUFFERED_LOGS = 200


class LogService:
    def __init__(
        self,
        client: DBusClient,
        *,
        session_resolver: Callable[[str], str],
    ) -> None:
        self._client = client
        self._session_resolver = session_resolver
        self._recent_by_path: dict[str, deque[str]] = {}

    def recent_logs(self, session_id: str | None = None, limit: int = 200) -> tuple[str, ...]:
        if session_id is None:
            lines: list[str] = []
            for buffer in self._recent_by_path.values():
                lines.extend(buffer)
            return tuple(lines[-limit:])
        object_path = self._session_resolver(session_id)
        payload = self._client.get_property(
            service="net.openvpn.v3.sessions",
            object_path=object_path,
            interface="net.openvpn.v3.sessions",
            name="last_log",
        ) or {}
        message = _extract_log_message(payload)
        if message:
            self._append_log(object_path, message)
        return tuple(self._recent_by_path.get(object_path, ()))[:limit]

    def subscribe_logs(
        self,
        session_id: str,
        callback: Callable[[str], None],
    ) -> Callable[[], None]:
        object_path = self._session_resolver(session_id)

        def wrapped(payload: object) -> None:
            message = _extract_log_message(payload)
            if not message:
                return
            self._append_log(object_path, message)
            callback(message)

        return self._client.subscribe_signal(
            service=SESSION_SERVICE_NAME,
            object_path=object_path,
            interface=SESSION_INTERFACE,
            signal_name="Log",
            callback=wrapped,
        )

    def _append_log(self, object_path: str, message: str) -> None:
        buffer = self._recent_by_path.setdefault(
            object_path,
            deque(maxlen=_MAX_BUFFERED_LOGS),
        )
        if message in buffer:
            return
        buffer.append(message)


def _extract_log_message(payload: object) -> str:
    if isinstance(payload, dict):
        for key in ("log_message", "message", "msg"):
            value = payload.get(key)
            if value:
                return str(value)
        return ""
    if isinstance(payload, tuple):
        for item in reversed(payload):
            if isinstance(item, str) and item.strip():
                return item
            if isinstance(item, dict):
                nested = _extract_log_message(item)
                if nested:
                    return nested
        return ""
    if isinstance(payload, str):
        return payload
    return str(payload).strip()
