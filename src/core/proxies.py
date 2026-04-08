"""Proxy management subsystem."""

from __future__ import annotations

from dataclasses import replace
import json
import os
import uuid
from pathlib import Path

from core.models import ProxyCredentials, ProxyDefinition, ProxyType
from core.secrets import SecretStore


class ProxyValidationError(ValueError):
    """Raised when a proxy definition is invalid."""


def default_proxy_dir(app_name: str = "openvpn3-client-linux") -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / app_name


class ProxyService:
    def __init__(
        self,
        secret_store: SecretStore,
        *,
        config_dir: Path | None = None,
    ) -> None:
        self._secret_store = secret_store
        self._config_dir = config_dir or default_proxy_dir()
        self._proxy_path = self._config_dir / "proxies.json"

    def list_proxies(self) -> tuple[ProxyDefinition, ...]:
        if not self._proxy_path.exists():
            return ()

        payload = json.loads(self._proxy_path.read_text(encoding="utf-8"))
        proxies = tuple(
            self._normalize_proxy(
                ProxyDefinition(
                    id=item["id"],
                    name=item["name"],
                    type=ProxyType(item["type"]),
                    host=item["host"],
                    port=int(item["port"]),
                    credential_ref=item.get("credential_ref"),
                    enabled=bool(item.get("enabled", True)),
                )
            )
            for item in payload
        )
        return tuple(sorted(proxies, key=lambda item: (item.name.lower(), item.host.lower())))

    def secure_storage_available(self) -> bool:
        return self._secret_store.available()

    def get_proxy(self, proxy_id: str) -> ProxyDefinition | None:
        for proxy in self.list_proxies():
            if proxy.id == proxy_id:
                return proxy
        return None

    def load_proxy_credentials(self, proxy_id: str) -> ProxyCredentials | None:
        proxy = self.get_proxy(proxy_id)
        if proxy is None or not proxy.credential_ref:
            return None
        return self._secret_store.load_proxy_credentials(proxy.credential_ref)

    def save_proxy(
        self,
        proxy: ProxyDefinition,
        *,
        credentials: ProxyCredentials | None = None,
        clear_credentials: bool = False,
    ) -> ProxyDefinition:
        existing = {item.id: item for item in self.list_proxies()}
        current = existing.get(proxy.id)
        normalized = self._normalize_proxy(proxy)
        if not normalized.id:
            normalized.id = f"proxy-{uuid.uuid4().hex[:12]}"

        self.validate(normalized, existing=existing.values())

        if clear_credentials and current and current.credential_ref:
            self._secret_store.delete_proxy_credentials(current.credential_ref)
            normalized.credential_ref = None
        elif credentials is not None:
            normalized_credentials = self._normalize_credentials(credentials)
            self.validate_credentials(normalized_credentials)
            credential_ref = (
                normalized.credential_ref
                or (current.credential_ref if current is not None else None)
                or f"proxy:{normalized.id}"
            )
            self._secret_store.store_proxy_credentials(
                credential_ref,
                normalized_credentials,
            )
            normalized.credential_ref = credential_ref
        elif current is not None:
            normalized.credential_ref = current.credential_ref

        existing[normalized.id] = normalized
        self._write(tuple(existing.values()))
        return normalized

    def delete_proxy(self, proxy_id: str) -> None:
        existing = {item.id: item for item in self.list_proxies()}
        proxy = existing.pop(proxy_id, None)
        if proxy is None:
            return

        if proxy.credential_ref:
            self._secret_store.delete_proxy_credentials(proxy.credential_ref)
        self._write(tuple(existing.values()))

    def validate(
        self,
        proxy: ProxyDefinition,
        *,
        existing: tuple[ProxyDefinition, ...] | list[ProxyDefinition] | None = None,
    ) -> None:
        if not proxy.name.strip():
            raise ProxyValidationError("Proxy name is required.")
        if not proxy.host.strip():
            raise ProxyValidationError("Proxy host is required.")
        if not 1 <= proxy.port <= 65535:
            raise ProxyValidationError("Proxy port must be between 1 and 65535.")
        if existing is None:
            existing = self.list_proxies()
        duplicate = next(
            (
                item
                for item in existing
                if item.id != proxy.id and item.name.strip().lower() == proxy.name.strip().lower()
            ),
            None,
        )
        if duplicate is not None:
            raise ProxyValidationError("Proxy name must be unique.")

    def validate_credentials(self, credentials: ProxyCredentials) -> None:
        if not credentials.username.strip():
            raise ProxyValidationError("Proxy username is required when authentication is enabled.")
        if not credentials.password:
            raise ProxyValidationError("Proxy password is required when authentication is enabled.")

    def _write(self, proxies: tuple[ProxyDefinition, ...]) -> None:
        self._config_dir.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "id": item.id,
                "name": item.name,
                "type": item.type.value,
                "host": item.host,
                "port": item.port,
                "credential_ref": item.credential_ref,
                "enabled": item.enabled,
            }
            for item in proxies
        ]
        self._proxy_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def _normalize_proxy(self, proxy: ProxyDefinition) -> ProxyDefinition:
        return replace(
            proxy,
            name=proxy.name.strip(),
            host=proxy.host.strip(),
            enabled=bool(proxy.enabled),
        )

    def _normalize_credentials(self, credentials: ProxyCredentials) -> ProxyCredentials:
        return ProxyCredentials(
            username=credentials.username.strip(),
            password=credentials.password,
        )
