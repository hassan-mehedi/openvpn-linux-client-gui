"""OpenVPN 3 configuration service adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import urlopen

from core.models import (
    AppSettings,
    ConnectionProtocol,
    ImportSource,
    Profile,
    ProxyCredentials,
    ProxyDefinition,
)
from openvpn3.dbus_client import (
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
        if settings.protocol is ConnectionProtocol.AUTO:
            self.unset_override(profile_id, "proto-override")
        else:
            self.set_override(profile_id, "proto-override", settings.protocol.value)
        self.set_override(
            profile_id,
            "dns-fallback-google",
            settings.google_dns_fallback,
        )
        self.set_property(profile_id, "dco", settings.dco)

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
        self._client.call_method(
            service=CONFIGURATION_SERVICE_NAME,
            object_path=profile_path,
            interface=CONFIGURATION_INTERFACE,
            method="UnsetOverride",
            signature="s",
            params=(name,),
        )

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
