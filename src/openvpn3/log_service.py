"""OpenVPN 3 log service adapter."""

from __future__ import annotations

from typing import Callable

from openvpn3.dbus_client import DBusClient, LOG_SERVICE_NAME


LOG_INTERFACE = "net.openvpn.v3.log"


class LogService:
    def __init__(
        self,
        client: DBusClient,
        *,
        session_resolver: Callable[[str], str],
    ) -> None:
        self._client = client
        self._session_resolver = session_resolver

    def recent_logs(self, session_id: str | None = None, limit: int = 200) -> tuple[str, ...]:
        if session_id is None:
            return ()
        object_path = self._session_resolver(session_id)
        payload = self._client.get_property(
            service="net.openvpn.v3.sessions",
            object_path=object_path,
            interface="net.openvpn.v3.sessions",
            name="last_log",
        ) or {}
        message = str(payload.get("log_message", ""))
        if not message:
            return ()
        return (message,)[:limit]
