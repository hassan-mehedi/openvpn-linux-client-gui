"""OpenVPN 3 configuration service adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit
from urllib.request import urlopen

from core.models import (
    AppSettings,
    ConnectionProtocol,
    ImportSource,
    Profile,
    ProxyCredentials,
    ProxyDefinition,
    SecurityLevel,
)
from ovpn3_dbus.dbus_client import (
    CONFIGURATION_SERVICE_NAME,
    DBUS_PROPERTIES_INTERFACE,
    DBusClient,
    opaque_identifier,
)


CONFIGURATION_INTERFACE = "net.openvpn.v3.configuration"
CONFIGURATION_MANAGER_PATH = "/net/openvpn/v3/configuration"
_PROXY_OVERRIDE_KEYS = (
    "proxy-host",
    "proxy-port",
    "proxy-username",
    "proxy-password",
    "proxy-auth-cleartext",
)
_TLS_MIN_OVERRIDE = "tls-version-min"
_TLS13_MIN_VERSION = "1.3"


@dataclass(slots=True, frozen=True)
class ConnectionSettingIssue:
    key: str
    label: str
    reason: str


class UnsupportedConnectionSettingsError(ValueError):
    def __init__(self, issues: tuple[ConnectionSettingIssue, ...]) -> None:
        self.issues = issues
        summary = ", ".join(issue.label for issue in issues)
        super().__init__(
            "OpenVPN 3 Linux cannot enforce these saved connection settings yet: "
            f"{summary}. Reset them to their defaults before connecting."
        )


class ConfigurationService:
    def __init__(self, client: DBusClient) -> None:
        self._client = client
        self._profile_paths: dict[str, str] = {}
        self._profile_ids_by_path: dict[str, str] = {}

    def list_profiles(self) -> tuple[Profile, ...]:
        payload = self._client.call_method(
            service=CONFIGURATION_SERVICE_NAME,
            object_path=CONFIGURATION_MANAGER_PATH,
            interface=CONFIGURATION_INTERFACE,
            method="FetchAvailableConfigs",
        ) or []
        return tuple(self._profile_from_path(item) for item in payload)

    def import_profile_from_bytes(
        self, name: str, payload: bytes, *, source: ImportSource
    ) -> Profile:
        response = self._client.call_method(
            service=CONFIGURATION_SERVICE_NAME,
            object_path=CONFIGURATION_MANAGER_PATH,
            interface=CONFIGURATION_INTERFACE,
            method="Import",
            signature="ssbb",
            params=(name, payload.decode("utf-8"), False, True),
        )
        profile = self._profile_from_path(str(response))
        profile.source = source
        return profile

    def import_profile_from_url(
        self,
        url: str,
        *,
        source: ImportSource,
        name: str | None = None,
    ) -> Profile:
        with urlopen(url) as response:
            payload = response.read()
        profile_name = name or Path(urlsplit(url).path).name or "remote-profile.ovpn"
        profile = self.import_profile_from_bytes(profile_name, payload, source=source)
        profile.metadata["canonical_url"] = url
        return profile

    def delete_profile(self, profile_id: str) -> None:
        profile_path = self.resolve_object_path(profile_id)
        self._client.call_method(
            service=CONFIGURATION_SERVICE_NAME,
            object_path=profile_path,
            interface=CONFIGURATION_INTERFACE,
            method="Remove",
        )
        self._profile_paths.pop(profile_id, None)
        self._profile_ids_by_path.pop(profile_path, None)

    def apply_connection_settings(self, profile_id: str, settings: AppSettings) -> None:
        # `connection_timeout` is enforced by the core session lifecycle.
        # The verified configuration D-Bus surface does not expose an equivalent
        # saved override we can apply here.
        self._apply_setting(
            profile_id,
            ConnectionSettingIssue(
                key="protocol",
                label="Protocol selection",
                reason="The backend rejected the requested protocol override.",
            ),
            lambda: self.unset_override(profile_id, "proto-override")
            if settings.protocol is ConnectionProtocol.AUTO
            else self.set_override(profile_id, "proto-override", settings.protocol.value),
        )
        self._apply_setting(
            profile_id,
            ConnectionSettingIssue(
                key="google_dns_fallback",
                label="Google DNS fallback",
                reason="The backend rejected the requested DNS fallback policy.",
            ),
            lambda: self.set_override(
                profile_id,
                "dns-fallback-google",
                settings.google_dns_fallback,
            ),
        )
        self._apply_setting(
            profile_id,
            ConnectionSettingIssue(
                key="seamless_tunnel",
                label="Seamless tunnel",
                reason="The backend rejected the requested persistent tunnel policy.",
            ),
            lambda: self.set_override(profile_id, "persist-tun", settings.seamless_tunnel),
        )
        self._apply_setting(
            profile_id,
            ConnectionSettingIssue(
                key="enforce_tls13",
                label="TLS 1.3 enforcement",
                reason="The backend rejected the requested minimum TLS version.",
            ),
            lambda: self._apply_tls_policy(profile_id, settings.enforce_tls13),
        )
        self._apply_setting(
            profile_id,
            ConnectionSettingIssue(
                key="security_level",
                label="Security level",
                reason="The backend rejected the requested strict security policy.",
            ),
            lambda: self._apply_security_level(profile_id, settings.security_level),
        )
        self._apply_setting(
            profile_id,
            ConnectionSettingIssue(
                key="block_ipv6",
                label="Block IPv6",
                reason="The backend rejected the requested IPv6 tunnel policy.",
            ),
            lambda: self._apply_ipv6_policy(profile_id, settings.block_ipv6),
        )
        self._apply_setting(
            profile_id,
            ConnectionSettingIssue(
                key="local_dns",
                label="Local DNS handling",
                reason="The backend rejected the requested DNS query scope.",
            ),
            lambda: self._apply_dns_scope(profile_id, settings.local_dns),
        )
        self._apply_setting(
            profile_id,
            ConnectionSettingIssue(
                key="dco",
                label="Data Channel Offload",
                reason="The backend rejected the requested DCO setting.",
            ),
            lambda: self.set_property(profile_id, "dco", settings.dco),
        )

    def apply_proxy_assignment(
        self,
        profile_id: str,
        proxy: ProxyDefinition | None,
        credentials: ProxyCredentials | None,
    ) -> None:
        if proxy is None:
            self.clear_proxy_assignment(profile_id)
            return

        self.set_override(profile_id, "proxy-host", proxy.host)
        self.set_override(profile_id, "proxy-port", proxy.port)
        if credentials is None:
            self.unset_override(profile_id, "proxy-username")
            self.unset_override(profile_id, "proxy-password")
            self.unset_override(profile_id, "proxy-auth-cleartext")
            return

        self.set_override(profile_id, "proxy-username", credentials.username)
        self.set_override(profile_id, "proxy-password", credentials.password)
        self.set_override(profile_id, "proxy-auth-cleartext", True)

    def clear_proxy_assignment(self, profile_id: str) -> None:
        for key in _PROXY_OVERRIDE_KEYS:
            self.unset_override(profile_id, key)

    def set_override(self, profile_id: str, name: str, value: Any) -> None:
        profile_path = self.resolve_object_path(profile_id)
        self._client.call_method(
            service=CONFIGURATION_SERVICE_NAME,
            object_path=profile_path,
            interface=CONFIGURATION_INTERFACE,
            method="SetOverride",
            signature="sv",
            params=(name, value),
        )

    def unset_override(self, profile_id: str, name: str) -> None:
        profile_path = self.resolve_object_path(profile_id)
        try:
            self._client.call_method(
                service=CONFIGURATION_SERVICE_NAME,
                object_path=profile_path,
                interface=CONFIGURATION_INTERFACE,
                method="UnsetOverride",
                signature="s",
                params=(name,),
            )
        except Exception as exc:
            if _is_missing_override_error(exc, name):
                return
            raise

    def set_property(self, profile_id: str, name: str, value: Any) -> None:
        profile_path = self.resolve_object_path(profile_id)
        self._client.call_method(
            service=CONFIGURATION_SERVICE_NAME,
            object_path=profile_path,
            interface=DBUS_PROPERTIES_INTERFACE,
            method="Set",
            signature="ssv",
            params=(CONFIGURATION_INTERFACE, name, value),
        )

    def _apply_setting(
        self,
        profile_id: str,
        issue: ConnectionSettingIssue,
        action: Callable[[], None],
    ) -> None:
        try:
            action()
        except UnsupportedConnectionSettingsError:
            raise
        except Exception as exc:
            detail = str(exc).strip()
            reason = issue.reason
            if detail:
                reason = f"{reason} Backend reported: {detail}"
            raise UnsupportedConnectionSettingsError(
                (ConnectionSettingIssue(issue.key, issue.label, reason),)
            ) from exc

    def _apply_security_level(
        self,
        profile_id: str,
        level: SecurityLevel,
    ) -> None:
        if level is SecurityLevel.STRICT:
            self.set_override(profile_id, "enable-legacy-algorithms", False)
            self.set_override(profile_id, "allow-compression", "no")
            return
        self.unset_override(profile_id, "enable-legacy-algorithms")
        self.unset_override(profile_id, "allow-compression")

    def _apply_tls_policy(self, profile_id: str, enforce_tls13: bool) -> None:
        if enforce_tls13:
            self.set_override(profile_id, _TLS_MIN_OVERRIDE, _TLS13_MIN_VERSION)
            return
        self.unset_override(profile_id, _TLS_MIN_OVERRIDE)

    def _apply_ipv6_policy(self, profile_id: str, block_ipv6: bool) -> None:
        if block_ipv6:
            self.set_override(profile_id, "ipv6", "no")
            return
        self.unset_override(profile_id, "ipv6")

    def _apply_dns_scope(self, profile_id: str, local_dns_enabled: bool) -> None:
        if local_dns_enabled:
            self.unset_override(profile_id, "dns-scope")
            return
        self.set_override(profile_id, "dns-scope", "global")

    def resolve_object_path(self, profile_id: str) -> str:
        try:
            return self._profile_paths[profile_id]
        except KeyError as exc:
            raise KeyError(f"Unknown profile identifier: {profile_id}") from exc

    def resolve_profile_id(self, object_path: str) -> str | None:
        return self._profile_ids_by_path.get(object_path)

    def _profile_from_path(self, object_path: str) -> Profile:
        payload = self._client.get_all_properties(
            service=CONFIGURATION_SERVICE_NAME,
            object_path=object_path,
            interface=CONFIGURATION_INTERFACE,
        )
        profile_id = opaque_identifier("profile", object_path)
        self._profile_paths[profile_id] = object_path
        self._profile_ids_by_path[object_path] = profile_id
        imported_at = _parse_timestamp(payload.get("import_timestamp"))
        last_used = _parse_timestamp(payload.get("last_used_timestamp"))
        metadata = {
            "persistent": bool(payload.get("persistent", False)),
            "valid": bool(payload.get("valid", False)),
            "readonly": bool(payload.get("readonly", False)),
            "locked_down": bool(payload.get("locked_down", False)),
            "used_count": int(payload.get("used_count", 0)),
            "tags": tuple(payload.get("tags", ())),
        }
        return Profile(
            id=profile_id,
            name=str(payload.get("name", profile_id)),
            source=ImportSource.FILE,
            imported_at=imported_at,
            last_used=last_used,
            metadata=metadata,
            capabilities=(),
        )


def _parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return datetime.fromisoformat(str(value))


def _is_missing_override_error(exc: Exception, name: str) -> bool:
    message = str(exc)
    if f"Override '{name}' has not been set" in message:
        return True
    dbus_name = getattr(exc, "get_dbus_name", lambda: "")()
    return "net.openvpn.gdbuspp" in str(dbus_name) and "has not been set" in message
