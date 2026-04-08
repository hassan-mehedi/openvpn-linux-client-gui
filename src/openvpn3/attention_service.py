"""OpenVPN 3 attention and challenge handling adapter."""

from __future__ import annotations

from typing import Any, Callable

from core.models import AttentionFieldType, AttentionRequest
from openvpn3.dbus_client import DBusClient, SESSION_SERVICE_NAME


ATTENTION_INTERFACE = "net.openvpn.v3.attention"
SESSION_INTERFACE = "net.openvpn.v3.sessions"


class AttentionService:
    def __init__(
        self,
        client: DBusClient,
        *,
        session_resolver: Callable[[str], str],
    ) -> None:
        self._client = client
        self._session_resolver = session_resolver

    def get_attention_requests(self, session_id: str) -> tuple[AttentionRequest, ...]:
        object_path = self._session_resolver(session_id)
        groups = self._client.call_method(
            service=SESSION_SERVICE_NAME,
            object_path=object_path,
            interface=SESSION_INTERFACE,
            method="UserInputQueueGetTypeGroup",
        ) or []
        requests: list[AttentionRequest] = []
        for qtype, qgroup in groups:
            queue_ids = self._client.call_method(
                service=SESSION_SERVICE_NAME,
                object_path=object_path,
                interface=SESSION_INTERFACE,
                method="UserInputQueueCheck",
                signature="uu",
                params=(qtype, qgroup),
            ) or []
            for queue_id in queue_ids:
                payload = self._client.call_method(
                    service=SESSION_SERVICE_NAME,
                    object_path=object_path,
                    interface=SESSION_INTERFACE,
                    method="UserInputQueueFetch",
                    signature="uuu",
                    params=(qtype, qgroup, queue_id),
                )
                requests.append(self._map_request(session_id, payload))
        return tuple(requests)

    def provide_user_input(self, session_id: str, field_id: str, value: str) -> None:
        object_path = self._session_resolver(session_id)
        qtype, qgroup, queue_id = (int(part) for part in field_id.split(":", maxsplit=2))
        self._client.call_method(
            service=SESSION_SERVICE_NAME,
            object_path=object_path,
            interface=SESSION_INTERFACE,
            method="UserInputProvide",
            signature="uuus",
            params=(qtype, qgroup, queue_id, value),
        )

    def _map_request(self, session_id: str, payload: tuple[Any, ...]) -> AttentionRequest:
        qtype, qgroup, queue_id, variable_name, label, masked = payload
        return AttentionRequest(
            session_id=session_id,
            field_id=f"{int(qtype)}:{int(qgroup)}:{int(queue_id)}",
            label=str(label or variable_name),
            field_type=_map_attention_field_type(int(qgroup), bool(masked)),
            secret=bool(masked),
        )


def _map_attention_field_type(queue_group: int, masked: bool) -> AttentionFieldType:
    if queue_group == 1:
        return AttentionFieldType.SECRET if masked else AttentionFieldType.TEXT
    if queue_group in {4, 5, 6}:
        return AttentionFieldType.OTP
    if queue_group == 3:
        return AttentionFieldType.PASSPHRASE
    return AttentionFieldType.SECRET if masked else AttentionFieldType.TEXT
