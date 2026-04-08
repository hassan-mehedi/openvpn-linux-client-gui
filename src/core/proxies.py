"""Proxy management subsystem."""

from __future__ import annotations

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
        return tuple(
            ProxyDefinition(
                id=item["id"],
                name=item["name"],
                type=ProxyType(item["type"]),
                host=item["host"],
                port=int(item["port"]),
                credential_ref=item.get("credential_ref"),
                enabled=bool(item.get("enabled", True)),
            )
            for item in payload
        )

    def save_proxy(
        self,
        proxy: ProxyDefinition,
        *,
        credentials: ProxyCredentials | None = None,
    ) -> ProxyDefinition:
        self.validate(proxy)

        existing = {item.id: item for item in self.list_proxies()}
        if not proxy.id:
            proxy.id = f"proxy-{uuid.uuid4().hex[:12]}"

        if credentials is not None:
            credential_ref = proxy.credential_ref or f"proxy:{proxy.id}"
            self._secret_store.store_proxy_credentials(credential_ref, credentials)
            proxy.credential_ref = credential_ref

        existing[proxy.id] = proxy
        self._write(tuple(existing.values()))
        return proxy

    def delete_proxy(self, proxy_id: str) -> None:
        existing = {item.id: item for item in self.list_proxies()}
        proxy = existing.pop(proxy_id, None)
        if proxy is None:
            return

        if proxy.credential_ref:
            self._secret_store.delete_proxy_credentials(proxy.credential_ref)
        self._write(tuple(existing.values()))

    def validate(self, proxy: ProxyDefinition) -> None:
        if not proxy.name.strip():
            raise ProxyValidationError("Proxy name is required.")
        if not proxy.host.strip():
            raise ProxyValidationError("Proxy host is required.")
        if not 1 <= proxy.port <= 65535:
            raise ProxyValidationError("Proxy port must be between 1 and 65535.")

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
