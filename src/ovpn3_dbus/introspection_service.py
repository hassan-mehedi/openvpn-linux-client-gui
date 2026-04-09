"""OpenVPN 3 D-Bus surface validation via live introspection."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable
from xml.etree import ElementTree

from core.models import DBusInterfaceValidation, DBusValidationReport, DiagnosticStatus
from ovpn3_dbus.dbus_client import (
    BACKEND_SERVICE_NAME,
    CONFIGURATION_SERVICE_NAME,
    LOG_SERVICE_NAME,
    NETCFG_SERVICE_NAME,
    SESSION_SERVICE_NAME,
    DBusClient,
)


CONFIGURATION_INTERFACE = "net.openvpn.v3.configuration"
CONFIGURATION_MANAGER_PATH = "/net/openvpn/v3/configuration"
SESSION_INTERFACE = "net.openvpn.v3.sessions"
SESSION_MANAGER_PATH = "/net/openvpn/v3/sessions"
BACKEND_INTERFACE = "net.openvpn.v3.backends"
BACKEND_MANAGER_PATH = "/net/openvpn/v3/backends"
LOG_INTERFACE = "net.openvpn.v3.log"
LOG_MANAGER_PATH = "/net/openvpn/v3/log"
NETCFG_INTERFACE = "net.openvpn.v3.netcfg"
NETCFG_MANAGER_PATH = "/net/openvpn/v3/netcfg"


@dataclass(slots=True, frozen=True)
class _InterfaceExpectation:
    label: str
    service: str
    object_path: str
    interface: str
    required_methods: tuple[str, ...] = ()
    required_properties: tuple[str, ...] = ()
    required_signals: tuple[str, ...] = ()
    missing_detail: str | None = None


@dataclass(slots=True, frozen=True)
class _ParsedInterface:
    methods: tuple[str, ...]
    properties: tuple[str, ...]
    signals: tuple[str, ...]


class IntrospectionService:
    """Validate the current adapter assumptions against live D-Bus metadata."""

    def __init__(
        self,
        client: DBusClient,
        *,
        list_profile_paths: Callable[[], tuple[str, ...]] | None = None,
        list_session_paths: Callable[[], tuple[str, ...]] | None = None,
        introspection_attempts: int = 2,
        introspection_retry_delay: float = 0.1,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._client = client
        self._list_profile_paths = list_profile_paths or self._fetch_profile_paths
        self._list_session_paths = list_session_paths or self._fetch_session_paths
        self._introspection_attempts = max(1, introspection_attempts)
        self._introspection_retry_delay = max(0.0, introspection_retry_delay)
        self._sleep = sleep or time.sleep

    def validate_surface(self) -> DBusValidationReport:
        interfaces = tuple(self._validate_expectation(item) for item in self._expectations())
        if any(item.status is DiagnosticStatus.FAIL for item in interfaces):
            status = DiagnosticStatus.FAIL
        elif any(item.status is DiagnosticStatus.WARN for item in interfaces):
            status = DiagnosticStatus.WARN
        elif any(item.status is DiagnosticStatus.PASS for item in interfaces):
            status = DiagnosticStatus.PASS
        else:
            status = DiagnosticStatus.INFO

        failed = [item.label for item in interfaces if item.status is DiagnosticStatus.FAIL]
        warned = [item.label for item in interfaces if item.status is DiagnosticStatus.WARN]
        if status is DiagnosticStatus.FAIL:
            summary = "Live D-Bus validation found mismatches: " + ", ".join(failed)
        elif status is DiagnosticStatus.WARN:
            summary = "Live D-Bus validation is incomplete: " + ", ".join(warned)
        elif status is DiagnosticStatus.PASS:
            summary = "Live D-Bus validation matched the current adapter surface."
        else:
            summary = "No live D-Bus interfaces were available for validation."
        return DBusValidationReport(status=status, summary=summary, interfaces=interfaces)

    def _expectations(self) -> tuple[_InterfaceExpectation, ...]:
        profile_paths = self._safe_paths(self._list_profile_paths)
        session_paths = self._safe_paths(self._list_session_paths)
        profile_path = profile_paths[0] if profile_paths else ""
        session_path = session_paths[0] if session_paths else ""
        return (
            _InterfaceExpectation(
                label="Configuration manager",
                service=CONFIGURATION_SERVICE_NAME,
                object_path=CONFIGURATION_MANAGER_PATH,
                interface=CONFIGURATION_INTERFACE,
                required_methods=("FetchAvailableConfigs", "Import", "LookupConfigName"),
            ),
            _InterfaceExpectation(
                label="Configuration profile object",
                service=CONFIGURATION_SERVICE_NAME,
                object_path=profile_path,
                interface=CONFIGURATION_INTERFACE,
                required_methods=(
                    "Fetch",
                    "FetchJSON",
                    "Remove",
                    "SetOption",
                    "SetOverride",
                    "UnsetOverride",
                    "Validate",
                ),
                required_properties=(
                    "name",
                    "import_timestamp",
                    "last_used_timestamp",
                    "persistent",
                    "valid",
                    "readonly",
                    "locked_down",
                    "used_count",
                    "dco",
                ),
                missing_detail=(
                    "No imported profiles were available, so a live configuration object could not be introspected."
                ),
            ),
            _InterfaceExpectation(
                label="Session manager",
                service=SESSION_SERVICE_NAME,
                object_path=SESSION_MANAGER_PATH,
                interface=SESSION_INTERFACE,
                required_methods=(
                    "NewTunnel",
                    "FetchAvailableSessions",
                    "FetchManagedInterfaces",
                    "LookupConfigName",
                    "LookupInterface",
                ),
            ),
            _InterfaceExpectation(
                label="Session object",
                service=SESSION_SERVICE_NAME,
                object_path=session_path,
                interface=SESSION_INTERFACE,
                required_methods=(
                    "Ready",
                    "Connect",
                    "Disconnect",
                    "Pause",
                    "Resume",
                    "Restart",
                    "UserInputQueueGetTypeGroup",
                    "UserInputQueueCheck",
                    "UserInputQueueFetch",
                    "UserInputProvide",
                ),
                required_properties=(
                    "status",
                    "config_path",
                    "config_name",
                    "session_created",
                ),
                required_signals=("AttentionRequired", "StatusChange", "Log"),
                missing_detail=(
                    "No live sessions were available, so a session object could not be introspected."
                ),
            ),
            _InterfaceExpectation(
                label="Log manager",
                service=LOG_SERVICE_NAME,
                object_path=LOG_MANAGER_PATH,
                interface=LOG_INTERFACE,
            ),
            _InterfaceExpectation(
                label="Backend manager",
                service=BACKEND_SERVICE_NAME,
                object_path=BACKEND_MANAGER_PATH,
                interface=BACKEND_INTERFACE,
            ),
            _InterfaceExpectation(
                label="NetCfg manager",
                service=NETCFG_SERVICE_NAME,
                object_path=NETCFG_MANAGER_PATH,
                interface=NETCFG_INTERFACE,
            ),
        )

    def _validate_expectation(self, expectation: _InterfaceExpectation) -> DBusInterfaceValidation:
        if not expectation.object_path:
            return DBusInterfaceValidation(
                label=expectation.label,
                service=expectation.service,
                object_path="",
                interface=expectation.interface,
                status=DiagnosticStatus.WARN,
                detail=expectation.missing_detail or "No object path was available for validation.",
            )
        failure_detail = "The expected interface was not present in the introspection data."
        parsed: _ParsedInterface | None = None
        for attempt in range(self._introspection_attempts):
            try:
                xml_payload = self._client.introspect(
                    service=expectation.service,
                    object_path=expectation.object_path,
                )
            except Exception as exc:
                failure_detail = f"Introspection failed: {exc}"
                if attempt + 1 < self._introspection_attempts:
                    self._sleep(self._introspection_retry_delay)
                    continue
                return DBusInterfaceValidation(
                    label=expectation.label,
                    service=expectation.service,
                    object_path=expectation.object_path,
                    interface=expectation.interface,
                    status=DiagnosticStatus.FAIL,
                    detail=failure_detail,
                )

            try:
                parsed = _parse_interface(xml_payload, expectation.interface)
            except Exception as exc:
                return DBusInterfaceValidation(
                    label=expectation.label,
                    service=expectation.service,
                    object_path=expectation.object_path,
                    interface=expectation.interface,
                    status=DiagnosticStatus.FAIL,
                    detail=f"Failed to parse introspection XML: {exc}",
                )
            if parsed is not None:
                break
            if attempt + 1 < self._introspection_attempts:
                self._sleep(self._introspection_retry_delay)

        if parsed is None:
            return DBusInterfaceValidation(
                label=expectation.label,
                service=expectation.service,
                object_path=expectation.object_path,
                interface=expectation.interface,
                status=DiagnosticStatus.FAIL,
                detail=failure_detail,
            )

        missing_methods = tuple(
            name for name in expectation.required_methods if name not in parsed.methods
        )
        missing_properties = tuple(
            name for name in expectation.required_properties if name not in parsed.properties
        )
        missing_signals = tuple(
            name for name in expectation.required_signals if name not in parsed.signals
        )
        missing: list[str] = []
        if missing_methods:
            missing.append("methods: " + ", ".join(missing_methods))
        if missing_properties:
            missing.append("properties: " + ", ".join(missing_properties))
        if missing_signals:
            missing.append("signals: " + ", ".join(missing_signals))
        detail = (
            "Validated against live introspection data."
            if not missing
            else "Missing expected " + "; ".join(missing)
        )
        return DBusInterfaceValidation(
            label=expectation.label,
            service=expectation.service,
            object_path=expectation.object_path,
            interface=expectation.interface,
            status=DiagnosticStatus.PASS if not missing else DiagnosticStatus.FAIL,
            detail=detail,
            methods=parsed.methods,
            properties=parsed.properties,
            signals=parsed.signals,
            missing_methods=missing_methods,
            missing_properties=missing_properties,
            missing_signals=missing_signals,
        )

    def _fetch_profile_paths(self) -> tuple[str, ...]:
        payload = self._client.call_method(
            service=CONFIGURATION_SERVICE_NAME,
            object_path=CONFIGURATION_MANAGER_PATH,
            interface=CONFIGURATION_INTERFACE,
            method="FetchAvailableConfigs",
        ) or []
        return tuple(str(item) for item in payload)

    def _fetch_session_paths(self) -> tuple[str, ...]:
        payload = self._client.call_method(
            service=SESSION_SERVICE_NAME,
            object_path=SESSION_MANAGER_PATH,
            interface=SESSION_INTERFACE,
            method="FetchAvailableSessions",
        ) or []
        return tuple(str(item) for item in payload)

    @staticmethod
    def _safe_paths(loader: Callable[[], tuple[str, ...]]) -> tuple[str, ...]:
        try:
            return loader()
        except Exception:
            return ()


def _parse_interface(xml_payload: str, interface_name: str) -> _ParsedInterface | None:
    root = ElementTree.fromstring(xml_payload)
    for interface in root.findall("interface"):
        if interface.get("name") != interface_name:
            continue
        methods = tuple(
            sorted(
                child.get("name", "")
                for child in interface.findall("method")
                if child.get("name")
            )
        )
        properties = tuple(
            sorted(
                child.get("name", "")
                for child in interface.findall("property")
                if child.get("name")
            )
        )
        signals = tuple(
            sorted(
                child.get("name", "")
                for child in interface.findall("signal")
                if child.get("name")
            )
        )
        return _ParsedInterface(
            methods=methods,
            properties=properties,
            signals=signals,
        )
    return None
