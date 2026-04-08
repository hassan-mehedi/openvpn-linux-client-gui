from collections.abc import Callable
from typing import Any

from core.models import ImportSource, SessionPhase
from openvpn3.configuration_service import ConfigurationService
from openvpn3.dbus_client import DBusClient
from openvpn3.session_service import SessionService


class FakeDBusException(Exception):
    def __init__(self, message: str, *, dbus_name: str = "") -> None:
        super().__init__(message)
        self._dbus_name = dbus_name

    def get_dbus_name(self) -> str:
        return self._dbus_name


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.config_props = {
            "/net/openvpn/v3/configuration/profile1": {
                "name": "Demo",
                "import_timestamp": 1,
                "last_used_timestamp": 2,
                "persistent": True,
                "valid": True,
                "readonly": False,
                "locked_down": False,
                "used_count": 1,
                "tags": [],
            }
        }
        self.session_props = {
            "/net/openvpn/v3/sessions/session1": {
                "config_name": "Demo",
                "config_path": "/net/openvpn/v3/configuration/profile1",
                "session_created": 3,
                "status": (3, 17, "Session created"),
            }
        }

    def call(
        self,
        *,
        bus_name: str,
        object_path: str,
        interface: str,
        method: str,
        params: Any | None = None,
        signature: str | None = None,
    ) -> Any:
        self.calls.append(
            {
                "bus_name": bus_name,
                "object_path": object_path,
                "interface": interface,
                "method": method,
                "params": params,
                "signature": signature,
            }
        )
        if method == "FetchAvailableConfigs":
            return ["/net/openvpn/v3/configuration/profile1"]
        if method == "GetAll" and object_path in self.config_props:
            return self.config_props[object_path]
        if method == "NewTunnel":
            return "/net/openvpn/v3/sessions/session1"
        if method == "GetAll" and object_path in self.session_props:
            return self.session_props[object_path]
        if method == "Ready":
            self.session_props[object_path]["status"] = (2, 2, "Configuration ready")
            return None
        if method == "Connect":
            self.session_props[object_path]["status"] = (2, 7, "Connected")
            return None
        if method == "UserInputQueueGetTypeGroup":
            return []
        return None

    def subscribe(
        self,
        *,
        bus_name: str,
        object_path: str,
        interface: str,
        signal_name: str,
        callback: Callable[[Any], None],
    ) -> Callable[[], None]:
        return lambda: None


def test_configuration_service_maps_profiles_to_opaque_ids() -> None:
    client = DBusClient(FakeTransport())
    service = ConfigurationService(client)

    profiles = service.list_profiles()

    assert profiles[0].id.startswith("profile-")
    assert profiles[0].source is ImportSource.FILE
    assert service.resolve_object_path(profiles[0].id) == "/net/openvpn/v3/configuration/profile1"


def test_session_service_creates_and_tracks_sessions() -> None:
    transport = FakeTransport()
    configuration = ConfigurationService(DBusClient(transport))
    profiles = configuration.list_profiles()
    session_service = SessionService(
        DBusClient(transport),
        profile_resolver=lambda _profile_id: "/net/openvpn/v3/configuration/profile1",
        profile_id_from_path=configuration.resolve_profile_id,
    )

    session = session_service.create_session(profiles[0].id)
    prepared = session_service.prepare_session(session.id)
    connected = session_service.connect(session.id)

    assert session.state is SessionPhase.SESSION_CREATED
    assert prepared.state is SessionPhase.READY
    assert connected.state is SessionPhase.CONNECTED


def test_dbus_client_retries_activation_race() -> None:
    class FlakyTransport:
        def __init__(self) -> None:
            self.calls = 0

        def call(
            self,
            *,
            bus_name: str,
            object_path: str,
            interface: str,
            method: str,
            params: Any | None = None,
            signature: str | None = None,
        ) -> Any:
            self.calls += 1
            if self.calls == 1:
                raise FakeDBusException(
                    'Object does not exist at path "/net/openvpn/v3/configuration"',
                    dbus_name="org.freedesktop.DBus.Error.UnknownMethod",
                )
            return ["/net/openvpn/v3/configuration/profile1"]

        def subscribe(
            self,
            *,
            bus_name: str,
            object_path: str,
            interface: str,
            signal_name: str,
            callback: Callable[[Any], None],
        ) -> Callable[[], None]:
            return lambda: None

    transport = FlakyTransport()
    client = DBusClient(transport, activation_retry_delay=0)

    payload = client.call_method(
        service="net.openvpn.v3.configuration",
        object_path="/net/openvpn/v3/configuration",
        interface="net.openvpn.v3.configuration",
        method="FetchAvailableConfigs",
    )

    assert payload == ["/net/openvpn/v3/configuration/profile1"]
    assert transport.calls == 2
