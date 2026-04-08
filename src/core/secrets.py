"""Secret storage boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.models import ProxyCredentials


class SecretStoreUnavailableError(RuntimeError):
    """Raised when a secure secret store is not available."""


class SecretStore(Protocol):
    def store_proxy_credentials(self, key: str, credentials: ProxyCredentials) -> None:
        """Persist proxy credentials in a secure backend."""

    def load_proxy_credentials(self, key: str) -> ProxyCredentials | None:
        """Load proxy credentials from the secure backend."""

    def delete_proxy_credentials(self, key: str) -> None:
        """Delete proxy credentials from the secure backend."""


@dataclass(slots=True)
class MemorySecretStore:
    """In-memory store for tests and isolated local flows."""

    _storage: dict[str, ProxyCredentials] | None = None

    def __post_init__(self) -> None:
        if self._storage is None:
            self._storage = {}

    def store_proxy_credentials(self, key: str, credentials: ProxyCredentials) -> None:
        self._storage[key] = credentials

    def load_proxy_credentials(self, key: str) -> ProxyCredentials | None:
        return self._storage.get(key)

    def delete_proxy_credentials(self, key: str) -> None:
        self._storage.pop(key, None)


class UnavailableSecretStore:
    """Explicit failure mode for environments without libsecret integration."""

    def store_proxy_credentials(self, key: str, credentials: ProxyCredentials) -> None:
        raise SecretStoreUnavailableError("Secure secret storage is not configured.")

    def load_proxy_credentials(self, key: str) -> ProxyCredentials | None:
        raise SecretStoreUnavailableError("Secure secret storage is not configured.")

    def delete_proxy_credentials(self, key: str) -> None:
        raise SecretStoreUnavailableError("Secure secret storage is not configured.")

