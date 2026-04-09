from collections.abc import Callable
from typing import Any

import pytest

from core.models import (
    AppSettings,
    ConnectionProtocol,
    DiagnosticStatus,
    ImportSource,
    ProxyCredentials,
    ProxyDefinition,
    ProxyType,
    SecurityLevel,
    SessionPhase,
)
from openvpn3.configuration_service import (
    ConfigurationService,
    UnsupportedConnectionSettingsError,
)
from openvpn3.dbus_client import DBusClient
from openvpn3.introspection_service import IntrospectionService
from openvpn3.log_service import LogService
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
        self.subscriptions: list[dict[str, Any]] = []
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
        self.introspection_xml = {
            "/net/openvpn/v3/configuration": """
                <node>
                  <interface name="net.openvpn.v3.configuration">
                    <method name="FetchAvailableConfigs"/>
                    <method name="Import"/>
                    <method name="LookupConfigName"/>
                  </interface>
                </node>
            """,
            "/net/openvpn/v3/configuration/profile1": """
                <node>
                  <interface name="net.openvpn.v3.configuration">
                    <method name="Fetch"/>
                    <method name="FetchJSON"/>
                    <method name="Remove"/>
                    <method name="SetOption"/>
                    <method name="SetOverride"/>
                    <method name="UnsetOverride"/>
                    <method name="Validate"/>
                    <property name="name" type="s" access="read"/>
                    <property name="import_timestamp" type="t" access="read"/>
                    <property name="last_used_timestamp" type="t" access="read"/>
                    <property name="persistent" type="b" access="read"/>
                    <property name="valid" type="b" access="read"/>
                    <property name="readonly" type="b" access="read"/>
                    <property name="locked_down" type="b" access="read"/>
                    <property name="used_count" type="u" access="read"/>
                    <property name="dco" type="b" access="readwrite"/>
                  </interface>
                </node>
            """,
            "/net/openvpn/v3/sessions": """
                <node>
                  <interface name="net.openvpn.v3.sessions">
                    <method name="NewTunnel"/>
                    <method name="FetchAvailableSessions"/>
                    <method name="FetchManagedInterfaces"/>
                    <method name="LookupConfigName"/>
                    <method name="LookupInterface"/>
                  </interface>
                </node>
            """,
            "/net/openvpn/v3/sessions/session1": """
                <node>
                  <interface name="net.openvpn.v3.sessions">
                    <method name="Ready"/>
                    <method name="Connect"/>
                    <method name="Disconnect"/>
                    <method name="Pause"/>
                    <method name="Resume"/>
                    <method name="Restart"/>
                    <method name="UserInputQueueGetTypeGroup"/>
                    <method name="UserInputQueueCheck"/>
                    <method name="UserInputQueueFetch"/>
                    <method name="UserInputProvide"/>
                    <signal name="AttentionRequired"/>
                    <signal name="StatusChange"/>
                    <signal name="Log"/>
                    <property name="status" type="(uus)" access="read"/>
                    <property name="config_path" type="o" access="read"/>
                    <property name="config_name" type="s" access="read"/>
                    <property name="session_created" type="t" access="read"/>
                  </interface>
                </node>
            """,
            "/net/openvpn/v3/log": """
                <node>
                  <interface name="net.openvpn.v3.log"/>
                </node>
            """,
            "/net/openvpn/v3/backends": """
                <node>
                  <interface name="net.openvpn.v3.backends"/>
                </node>
            """,
            "/net/openvpn/v3/netcfg": """
                <node>
                  <interface name="net.openvpn.v3.netcfg"/>
                </node>
            """,
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
        if method == "FetchAvailableSessions":
            return ["/net/openvpn/v3/sessions/session1"]
        if method == "GetAll" and object_path in self.config_props:
            return self.config_props[object_path]
        if method == "NewTunnel":
            return "/net/openvpn/v3/sessions/session1"
        if method == "GetAll" and object_path in self.session_props:
            return self.session_props[object_path]
        if method == "Get" and object_path in self.session_props:
            interface_name, property_name = params
            if interface_name == "net.openvpn.v3.sessions":
                return self.session_props[object_path].get(property_name)
        if method == "Introspect" and object_path in self.introspection_xml:
            return self.introspection_xml[object_path]
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
        record = {
            "bus_name": bus_name,
            "object_path": object_path,
            "interface": interface,
            "signal_name": signal_name,
            "callback": callback,
        }
        self.subscriptions.append(record)
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


def test_configuration_service_applies_runtime_proxy_assignment() -> None:
    transport = FakeTransport()
    service = ConfigurationService(DBusClient(transport))
    profile = service.list_profiles()[0]

    service.apply_proxy_assignment(
        profile.id,
        ProxyDefinition(
            id="proxy-1",
            name="Office",
            type=ProxyType.HTTP,
            host="proxy.example.com",
            port=8080,
        ),
        ProxyCredentials(username="alice", password="secret"),
    )

    calls = [
        (call["method"], call["params"])
        for call in transport.calls
        if call["method"] in {"SetOverride", "UnsetOverride"}
    ]
    assert calls[-5:] == [
        ("SetOverride", ("proxy-host", "proxy.example.com")),
        ("SetOverride", ("proxy-port", 8080)),
        ("SetOverride", ("proxy-username", "alice")),
        ("SetOverride", ("proxy-password", "secret")),
        ("SetOverride", ("proxy-auth-cleartext", True)),
    ]


def test_configuration_service_clears_proxy_assignment() -> None:
    transport = FakeTransport()
    service = ConfigurationService(DBusClient(transport))
    profile = service.list_profiles()[0]

    service.apply_proxy_assignment(profile.id, None, None)

    calls = [
        (call["method"], call["params"])
        for call in transport.calls
        if call["method"] == "UnsetOverride"
    ]
    assert calls[-5:] == [
        ("UnsetOverride", ("proxy-host",)),
        ("UnsetOverride", ("proxy-port",)),
        ("UnsetOverride", ("proxy-username",)),
        ("UnsetOverride", ("proxy-password",)),
        ("UnsetOverride", ("proxy-auth-cleartext",)),
    ]


def test_configuration_service_applies_supported_runtime_settings() -> None:
    transport = FakeTransport()
    service = ConfigurationService(DBusClient(transport))
    profile = service.list_profiles()[0]

    service.apply_connection_settings(
        profile.id,
        AppSettings(
            protocol=ConnectionProtocol.TCP,
            seamless_tunnel=True,
            enforce_tls13=True,
            security_level=SecurityLevel.STRICT,
            block_ipv6=True,
            google_dns_fallback=True,
            local_dns=False,
            dco=True,
        ),
    )

    calls = [
        (call["method"], call["params"])
        for call in transport.calls
        if call["method"] in {"SetOverride", "Set"}
    ]
    assert calls[-9:] == [
        ("SetOverride", ("proto-override", "tcp")),
        ("SetOverride", ("dns-fallback-google", True)),
        ("SetOverride", ("persist-tun", True)),
        ("SetOverride", ("tls-version-min", "1.3")),
        ("SetOverride", ("enable-legacy-algorithms", False)),
        ("SetOverride", ("allow-compression", "no")),
        ("SetOverride", ("ipv6", "no")),
        ("SetOverride", ("dns-scope", "global")),
        ("Set", ("net.openvpn.v3.configuration", "dco", True)),
    ]


def test_configuration_service_ignores_missing_override_when_protocol_is_auto() -> None:
    transport = FakeTransport()
    service = ConfigurationService(DBusClient(transport))
    profile = service.list_profiles()[0]

    original_call = transport.call

    def call_with_missing_override(**kwargs):
        if kwargs["method"] == "UnsetOverride" and kwargs["params"] == ("proto-override",):
            raise FakeDBusException(
                "Override 'proto-override' has not been set",
                dbus_name="org.gtk.GDBus.UnmappedGError.Quark._net_2eopenvpn_2egdbuspp.Code36",
            )
        if kwargs["method"] == "UnsetOverride" and kwargs["params"] in {
            ("enable-legacy-algorithms",),
            ("allow-compression",),
            ("tls-version-min",),
            ("ipv6",),
            ("dns-scope",),
        }:
            raise FakeDBusException(
                f"Override '{kwargs['params'][0]}' has not been set",
                dbus_name="org.gtk.GDBus.UnmappedGError.Quark._net_2eopenvpn_2egdbuspp.Code36",
            )
        return original_call(**kwargs)

    transport.call = call_with_missing_override

    service.apply_connection_settings(
        profile.id,
        AppSettings(
            protocol=ConnectionProtocol.AUTO,
            seamless_tunnel=False,
            google_dns_fallback=False,
            dco=False,
        ),
    )

    calls = [
        (call["method"], call["params"])
        for call in transport.calls
        if call["method"] in {"UnsetOverride", "SetOverride", "Set"}
    ]
    assert calls[-3:] == [
        ("SetOverride", ("dns-fallback-google", False)),
        ("SetOverride", ("persist-tun", False)),
        ("Set", ("net.openvpn.v3.configuration", "dco", False)),
    ]


def test_configuration_service_keeps_connection_timeout_app_side() -> None:
    transport = FakeTransport()
    service = ConfigurationService(DBusClient(transport))
    profile = service.list_profiles()[0]

    service.apply_connection_settings(
        profile.id,
        AppSettings(connection_timeout=45),
    )

    runtime_calls = [
        call
        for call in transport.calls
        if call["method"] in {"SetOverride", "UnsetOverride", "Set"}
    ]
    assert runtime_calls
    assert all(call["params"] != ("connection_timeout", 45) for call in runtime_calls)


def test_introspection_service_validates_matching_surface() -> None:
    service = IntrospectionService(DBusClient(FakeTransport()))

    report = service.validate_surface()

    assert report.status is DiagnosticStatus.PASS
    assert all(item.status is DiagnosticStatus.PASS for item in report.interfaces)


def test_introspection_service_reports_missing_members() -> None:
    transport = FakeTransport()
    transport.introspection_xml["/net/openvpn/v3/sessions/session1"] = """
        <node>
          <interface name="net.openvpn.v3.sessions">
            <method name="Ready"/>
            <method name="Connect"/>
            <property name="status" type="(uus)" access="read"/>
            <signal name="StatusChange"/>
          </interface>
        </node>
    """
    service = IntrospectionService(DBusClient(transport))

    report = service.validate_surface()
    session_object = next(item for item in report.interfaces if item.label == "Session object")

    assert report.status.value == "fail"
    assert session_object.status.value == "fail"
    assert "Disconnect" in session_object.missing_methods
    assert "AttentionRequired" in session_object.missing_signals


def test_introspection_service_retries_transient_missing_backend_interface() -> None:
    transport = FakeTransport()
    backend_path = "/net/openvpn/v3/backends"
    transport.introspection_xml[backend_path] = """
        <node>
          <interface name="org.freedesktop.DBus.Introspectable">
            <method name="Introspect"/>
          </interface>
        </node>
    """
    original_call = transport.call
    backend_introspects = 0

    def call_with_backend_warmup(**kwargs):
        nonlocal backend_introspects
        if kwargs["method"] == "Introspect" and kwargs["object_path"] == backend_path:
            backend_introspects += 1
            if backend_introspects == 2:
                transport.introspection_xml[backend_path] = """
                    <node>
                      <interface name="net.openvpn.v3.backends">
                        <method name="StartClient"/>
                        <property name="version" type="s" access="read"/>
                        <signal name="Log"/>
                        <signal name="StatusChange"/>
                      </interface>
                    </node>
                """
        return original_call(**kwargs)

    transport.call = call_with_backend_warmup
    service = IntrospectionService(
        DBusClient(transport),
        introspection_retry_delay=0,
        sleep=lambda _seconds: None,
    )

    report = service.validate_surface()
    backend = next(item for item in report.interfaces if item.label == "Backend manager")

    assert report.status is DiagnosticStatus.PASS
    assert backend.status is DiagnosticStatus.PASS
    assert backend_introspects == 2


def test_configuration_service_wraps_backend_rejection_for_tls13_policy() -> None:
    transport = FakeTransport()
    service = ConfigurationService(DBusClient(transport))
    profile = service.list_profiles()[0]

    original_call = transport.call

    def rejecting_tls13(**kwargs):
        if kwargs["method"] == "SetOverride" and kwargs["params"] == (
            "tls-version-min",
            "1.3",
        ):
            raise RuntimeError("TLS 1.3 is unavailable on this OpenVPN backend")
        return original_call(**kwargs)

    transport.call = rejecting_tls13

    with pytest.raises(UnsupportedConnectionSettingsError) as excinfo:
        service.apply_connection_settings(
            profile.id,
            AppSettings(enforce_tls13=True),
        )

    message = str(excinfo.value)
    assert "TLS 1.3 enforcement" in message
    assert excinfo.value.issues[0].key == "enforce_tls13"
    assert "TLS 1.3 is unavailable" in excinfo.value.issues[0].reason


def test_configuration_service_wraps_backend_rejection_for_dns_scope() -> None:
    transport = FakeTransport()
    service = ConfigurationService(DBusClient(transport))
    profile = service.list_profiles()[0]

    original_call = transport.call

    def rejecting_dns_scope(**kwargs):
        if kwargs["method"] == "SetOverride" and kwargs["params"] == ("dns-scope", "global"):
            raise RuntimeError("dns-scope requires systemd-resolved support")
        return original_call(**kwargs)

    transport.call = rejecting_dns_scope

    with pytest.raises(UnsupportedConnectionSettingsError) as excinfo:
        service.apply_connection_settings(
            profile.id,
            AppSettings(local_dns=False),
        )

    message = str(excinfo.value)
    assert "Local DNS handling" in message
    assert excinfo.value.issues[0].key == "local_dns"
    assert "systemd-resolved support" in excinfo.value.issues[0].reason


def test_session_service_maps_best_effort_telemetry_properties() -> None:
    transport = FakeTransport()
    transport.session_props["/net/openvpn/v3/sessions/session1"].update(
        {
            "bytes_received": 4096,
            "bytes_sent": 2048,
            "packets_received": 64,
            "packets_sent": 48,
            "latency_ms": 25.0,
        }
    )
    configuration = ConfigurationService(DBusClient(transport))
    session_service = SessionService(
        DBusClient(transport),
        profile_resolver=lambda _profile_id: "/net/openvpn/v3/configuration/profile1",
        profile_id_from_path=configuration.resolve_profile_id,
    )

    session = session_service.create_session("profile-1")
    telemetry = session_service.get_session_telemetry(session.id)

    assert telemetry.available is True
    assert telemetry.bytes_in == 4096
    assert telemetry.bytes_out == 2048
    assert telemetry.packets_in == 64
    assert telemetry.packets_out == 48
    assert telemetry.latency_ms == 25.0


def test_log_service_replays_last_log_and_streams_live_entries() -> None:
    transport = FakeTransport()
    configuration = ConfigurationService(DBusClient(transport))
    profile = configuration.list_profiles()[0]
    session_service = SessionService(
        DBusClient(transport),
        profile_resolver=lambda _profile_id: "/net/openvpn/v3/configuration/profile1",
        profile_id_from_path=configuration.resolve_profile_id,
    )
    log_service = LogService(
        DBusClient(transport),
        session_resolver=session_service.resolve_object_path,
    )

    session = session_service.create_session(profile.id)
    transport.session_props["/net/openvpn/v3/sessions/session1"]["last_log"] = {
        "log_message": "Connected to server.",
    }

    assert log_service.recent_logs(session.id) == ("Connected to server.",)

    emitted: list[str] = []
    log_service.subscribe_logs(session.id, emitted.append)
    subscription = transport.subscriptions[-1]
    assert subscription["bus_name"] == "net.openvpn.v3.sessions"
    assert subscription["interface"] == "net.openvpn.v3.sessions"
    assert subscription["signal_name"] == "Log"
    subscription["callback"]({"log_message": "AUTH: Received control message"})

    assert emitted == ["AUTH: Received control message"]
    assert log_service.recent_logs(session.id) == (
        "Connected to server.",
        "AUTH: Received control message",
    )


def test_session_service_subscribes_to_status_changes_on_session_interface() -> None:
    transport = FakeTransport()
    configuration = ConfigurationService(DBusClient(transport))
    session_service = SessionService(
        DBusClient(transport),
        profile_resolver=lambda _profile_id: "/net/openvpn/v3/configuration/profile1",
        profile_id_from_path=configuration.resolve_profile_id,
    )

    session = session_service.create_session("profile-1")
    session_service.subscribe_to_updates(session.id, lambda _session: None)

    subscription = transport.subscriptions[-1]
    assert subscription["bus_name"] == "net.openvpn.v3.sessions"
    assert subscription["interface"] == "net.openvpn.v3.sessions"
    assert subscription["signal_name"] == "StatusChange"


def test_session_service_maps_statistics_dictionary_telemetry() -> None:
    transport = FakeTransport()
    transport.session_props["/net/openvpn/v3/sessions/session1"]["statistics"] = {
        "BYTES_IN": 32267,
        "BYTES_OUT": 83816,
        "PACKETS_IN": 726,
        "PACKETS_OUT": 1087,
        "TUN_BYTES_IN": 42818,
        "TUN_BYTES_OUT": 96,
        "TUN_PACKETS_IN": 426,
        "TUN_PACKETS_OUT": 2,
    }
    configuration = ConfigurationService(DBusClient(transport))
    session_service = SessionService(
        DBusClient(transport),
        profile_resolver=lambda _profile_id: "/net/openvpn/v3/configuration/profile1",
        profile_id_from_path=configuration.resolve_profile_id,
    )

    session = session_service.create_session("profile-1")
    telemetry = session_service.get_session_telemetry(session.id)

    assert telemetry.available is True
    assert telemetry.bytes_in == 32267
    assert telemetry.bytes_out == 83816
    assert telemetry.packets_in == 726
    assert telemetry.packets_out == 1087
    assert (
        telemetry.detail
        == "Traffic counters are available from the backend. Latency and packet-age timestamps are not exposed for this session."
    )


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
