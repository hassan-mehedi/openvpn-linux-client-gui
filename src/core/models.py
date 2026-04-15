"""Typed application models shared across the app."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core._compat import StrEnum


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class ParityLabel(StrEnum):
    DIRECT = "parity-direct"
    LINUX_ADAPTED = "parity-linux-adapted"
    LATER = "parity-later"


class ImportSource(StrEnum):
    FILE = "file"
    DRAG_AND_DROP = "drag-and-drop"
    URL = "url"
    TOKEN_URL = "token-url"


class SessionPhase(StrEnum):
    IDLE = "idle"
    PROFILE_SELECTED = "profile_selected"
    SESSION_CREATED = "session_created"
    WAITING_FOR_INPUT = "waiting_for_input"
    READY = "ready"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    PAUSED = "paused"
    RECONNECTING = "reconnecting"
    DISCONNECTING = "disconnecting"
    ERROR = "error"


class AttentionFieldType(StrEnum):
    TEXT = "text"
    SECRET = "secret"
    OTP = "otp"
    PASSPHRASE = "passphrase"


class ConnectionProtocol(StrEnum):
    AUTO = "auto"
    UDP = "udp"
    TCP = "tcp"


class LaunchBehavior(StrEnum):
    NONE = "none"
    START_APP = "start-app"
    CONNECT_LATEST = "connect-latest"
    RESTORE_CONNECTION = "restore-connection"


class ThemeMode(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class SecurityLevel(StrEnum):
    STANDARD = "standard"
    STRICT = "strict"


class ProxyType(StrEnum):
    HTTP = "http"
    SOCKS5 = "socks5"


class DiagnosticStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    INFO = "info"


@dataclass(slots=True, frozen=True)
class CapabilityState:
    key: str
    available: bool
    reason: str | None = None


@dataclass(slots=True)
class Profile:
    id: str
    name: str
    source: ImportSource
    imported_at: datetime = field(default_factory=utc_now)
    parity: ParityLabel = ParityLabel.DIRECT
    last_used: datetime | None = None
    assigned_proxy_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    capabilities: tuple[CapabilityState, ...] = ()


@dataclass(slots=True)
class SessionDescriptor:
    id: str
    profile_id: str
    state: SessionPhase
    status_message: str = ""
    requires_input: bool = False
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True, frozen=True)
class SessionTelemetrySample:
    session_id: str
    bytes_in: int | None = None
    bytes_out: int | None = None
    packets_in: int | None = None
    packets_out: int | None = None
    latency_ms: float | None = None
    last_packet_received_at: datetime | None = None
    last_packet_sent_at: datetime | None = None
    updated_at: datetime = field(default_factory=utc_now)
    available: bool = False
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class SessionTelemetryPoint:
    captured_at: datetime
    rx_rate_bps: float
    tx_rate_bps: float


@dataclass(slots=True, frozen=True)
class SessionTelemetrySnapshot:
    sample: SessionTelemetrySample
    rx_rate_bps: float | None = None
    tx_rate_bps: float | None = None
    history: tuple[SessionTelemetryPoint, ...] = ()


@dataclass(slots=True, frozen=True)
class AttentionRequest:
    session_id: str
    field_id: str
    label: str
    field_type: AttentionFieldType
    secret: bool = False
    value: str | None = None


@dataclass(slots=True, frozen=True)
class ProxyCredentials:
    username: str
    password: str


@dataclass(slots=True)
class ProxyDefinition:
    id: str
    name: str
    type: ProxyType
    host: str
    port: int
    credential_ref: str | None = None
    enabled: bool = True


@dataclass(slots=True)
class AppSettings:
    protocol: ConnectionProtocol = ConnectionProtocol.AUTO
    connection_timeout: int = 30
    launch_behavior: LaunchBehavior = LaunchBehavior.NONE
    seamless_tunnel: bool = False
    theme: ThemeMode = ThemeMode.SYSTEM
    close_to_tray: bool = False
    security_level: SecurityLevel = SecurityLevel.STANDARD
    enforce_tls13: bool = False
    dco: bool = False
    block_ipv6: bool = False
    google_dns_fallback: bool = False
    local_dns: bool = True
    disconnect_confirmation: bool = True

    def to_mapping(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol.value,
            "connection_timeout": self.connection_timeout,
            "launch_behavior": self.launch_behavior.value,
            "seamless_tunnel": self.seamless_tunnel,
            "theme": self.theme.value,
            "close_to_tray": self.close_to_tray,
            "security_level": self.security_level.value,
            "enforce_tls13": self.enforce_tls13,
            "dco": self.dco,
            "block_ipv6": self.block_ipv6,
            "google_dns_fallback": self.google_dns_fallback,
            "local_dns": self.local_dns,
            "disconnect_confirmation": self.disconnect_confirmation,
        }

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "AppSettings":
        return cls(
            protocol=ConnectionProtocol(data.get("protocol", ConnectionProtocol.AUTO)),
            connection_timeout=int(data.get("connection_timeout", 30)),
            launch_behavior=LaunchBehavior(
                data.get("launch_behavior", LaunchBehavior.NONE)
            ),
            seamless_tunnel=bool(data.get("seamless_tunnel", False)),
            theme=ThemeMode(data.get("theme", ThemeMode.SYSTEM)),
            close_to_tray=bool(data.get("close_to_tray", False)),
            security_level=SecurityLevel(
                data.get("security_level", SecurityLevel.STANDARD)
            ),
            enforce_tls13=bool(data.get("enforce_tls13", False)),
            dco=bool(data.get("dco", False)),
            block_ipv6=bool(data.get("block_ipv6", False)),
            google_dns_fallback=bool(data.get("google_dns_fallback", False)),
            local_dns=bool(data.get("local_dns", True)),
            disconnect_confirmation=bool(data.get("disconnect_confirmation", True)),
        )


@dataclass(slots=True, frozen=True)
class ImportProfileDetails:
    profile_name: str
    server_hostname: str | None = None
    username: str | None = None
    server_locked: bool = False
    username_locked: bool = False
    auth_requires_password: bool = False


@dataclass(slots=True, frozen=True)
class ImportPreview:
    name: str
    source: ImportSource
    canonical_location: str | None
    redacted_location: str | None
    content_hash: str | None = None
    duplicate_profile_id: str | None = None
    duplicate_profile_name: str | None = None
    duplicate_reason: str | None = None
    warnings: tuple[str, ...] = ()
    details: ImportProfileDetails | None = None


@dataclass(slots=True)
class SavedCredentialState:
    profile_id: str
    password_saved: bool = False


@dataclass(slots=True, frozen=True)
class DiagnosticCheck:
    key: str
    label: str
    status: DiagnosticStatus
    detail: str

@dataclass(slots=True, frozen=True)
class DiagnosticWorkflowStep:
    title: str
    detail: str


@dataclass(slots=True, frozen=True)
class DiagnosticWorkflow:
    key: str
    label: str
    status: DiagnosticStatus
    summary: str
    steps: tuple[DiagnosticWorkflowStep, ...]


@dataclass(slots=True, frozen=True)
class DBusInterfaceValidation:
    label: str
    service: str
    object_path: str
    interface: str
    status: DiagnosticStatus
    detail: str
    methods: tuple[str, ...] = ()
    properties: tuple[str, ...] = ()
    signals: tuple[str, ...] = ()
    missing_methods: tuple[str, ...] = ()
    missing_properties: tuple[str, ...] = ()
    missing_signals: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class DBusValidationReport:
    status: DiagnosticStatus
    summary: str
    interfaces: tuple[DBusInterfaceValidation, ...]
    validated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True, frozen=True)
class DiagnosticsSnapshot:
    app_version: str
    os_release: str
    kernel: str
    desktop_environment: str
    reachable_services: dict[str, bool]
    capabilities: tuple[CapabilityState, ...]
    environment_checks: tuple[DiagnosticCheck, ...]
    troubleshooting_items: tuple[DiagnosticCheck, ...]
    guided_workflows: tuple[DiagnosticWorkflow, ...]
    recent_logs: tuple[str, ...]
    profiles: tuple[Profile, ...]
    settings: AppSettings
    dbus_validation: DBusValidationReport | None = None
