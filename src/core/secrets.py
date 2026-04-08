"""Secret storage boundary."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Protocol

from core.models import (
    AttentionFieldType,
    AttentionRequest,
    ProxyCredentials,
    SavedCredentialState,
)

try:
    import gi

    gi.require_version("Secret", "1")

    from gi.repository import Secret
except (ImportError, ValueError):  # pragma: no cover - depends on system libs
    Secret = None


_PROFILE_PASSWORD_SCHEMA = "net.openvpn.v3linux.profile-password"
_PROXY_CREDENTIAL_SCHEMA = "net.openvpn.v3linux.proxy-credentials"


class SecretStoreUnavailableError(RuntimeError):
    """Raised when a secure secret store is not available."""


class SecretStore(Protocol):
    def available(self) -> bool:
        """Return whether secure secret storage can be used."""

    def store_profile_password(self, profile_id: str, password: str) -> None:
        """Persist a profile password in a secure backend."""

    def load_profile_password(self, profile_id: str) -> str | None:
        """Load a profile password from the secure backend."""

    def delete_profile_password(self, profile_id: str) -> None:
        """Delete a stored profile password."""

    def store_proxy_credentials(self, key: str, credentials: ProxyCredentials) -> None:
        """Persist proxy credentials in a secure backend."""

    def load_proxy_credentials(self, key: str) -> ProxyCredentials | None:
        """Load proxy credentials from the secure backend."""

    def delete_proxy_credentials(self, key: str) -> None:
        """Delete proxy credentials from the secure backend."""


@dataclass(slots=True)
class MemorySecretStore:
    """In-memory store for tests and isolated local flows."""

    _proxy_storage: dict[str, ProxyCredentials] | None = None
    _profile_passwords: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self._proxy_storage is None:
            self._proxy_storage = {}
        if self._profile_passwords is None:
            self._profile_passwords = {}

    def available(self) -> bool:
        return True

    def store_profile_password(self, profile_id: str, password: str) -> None:
        self._profile_passwords[profile_id] = password

    def load_profile_password(self, profile_id: str) -> str | None:
        return self._profile_passwords.get(profile_id)

    def delete_profile_password(self, profile_id: str) -> None:
        self._profile_passwords.pop(profile_id, None)

    def store_proxy_credentials(self, key: str, credentials: ProxyCredentials) -> None:
        self._proxy_storage[key] = credentials

    def load_proxy_credentials(self, key: str) -> ProxyCredentials | None:
        return self._proxy_storage.get(key)

    def delete_proxy_credentials(self, key: str) -> None:
        self._proxy_storage.pop(key, None)


class UnavailableSecretStore:
    """Explicit failure mode for environments without libsecret integration."""

    def available(self) -> bool:
        return False

    def store_profile_password(self, profile_id: str, password: str) -> None:
        raise SecretStoreUnavailableError("Secure secret storage is not configured.")

    def load_profile_password(self, profile_id: str) -> str | None:
        raise SecretStoreUnavailableError("Secure secret storage is not configured.")

    def delete_profile_password(self, profile_id: str) -> None:
        raise SecretStoreUnavailableError("Secure secret storage is not configured.")

    def store_proxy_credentials(self, key: str, credentials: ProxyCredentials) -> None:
        raise SecretStoreUnavailableError("Secure secret storage is not configured.")

    def load_proxy_credentials(self, key: str) -> ProxyCredentials | None:
        raise SecretStoreUnavailableError("Secure secret storage is not configured.")

    def delete_proxy_credentials(self, key: str) -> None:
        raise SecretStoreUnavailableError("Secure secret storage is not configured.")


class LibsecretStore:
    """libsecret-backed secure storage for profile passwords and proxy credentials."""

    def __init__(self, *, app_name: str = "openvpn3-client-linux") -> None:
        self._app_name = app_name

    def available(self) -> bool:
        return Secret is not None

    def store_profile_password(self, profile_id: str, password: str) -> None:
        self._store_secret(
            schema_name=_PROFILE_PASSWORD_SCHEMA,
            attributes={
                "app": self._app_name,
                "kind": "profile-password",
                "id": profile_id,
            },
            label=f"{self._app_name} profile password for {profile_id}",
            secret_value=password,
        )

    def load_profile_password(self, profile_id: str) -> str | None:
        return self._lookup_secret(
            schema_name=_PROFILE_PASSWORD_SCHEMA,
            attributes={
                "app": self._app_name,
                "kind": "profile-password",
                "id": profile_id,
            },
        )

    def delete_profile_password(self, profile_id: str) -> None:
        self._clear_secret(
            schema_name=_PROFILE_PASSWORD_SCHEMA,
            attributes={
                "app": self._app_name,
                "kind": "profile-password",
                "id": profile_id,
            },
        )

    def store_proxy_credentials(self, key: str, credentials: ProxyCredentials) -> None:
        self._store_secret(
            schema_name=_PROXY_CREDENTIAL_SCHEMA,
            attributes={
                "app": self._app_name,
                "kind": "proxy-credentials",
                "id": key,
            },
            label=f"{self._app_name} proxy credentials for {key}",
            secret_value=json.dumps(
                {
                    "username": credentials.username,
                    "password": credentials.password,
                }
            ),
        )

    def load_proxy_credentials(self, key: str) -> ProxyCredentials | None:
        secret_value = self._lookup_secret(
            schema_name=_PROXY_CREDENTIAL_SCHEMA,
            attributes={
                "app": self._app_name,
                "kind": "proxy-credentials",
                "id": key,
            },
        )
        if secret_value is None:
            return None
        payload = json.loads(secret_value)
        return ProxyCredentials(
            username=str(payload["username"]),
            password=str(payload["password"]),
        )

    def delete_proxy_credentials(self, key: str) -> None:
        self._clear_secret(
            schema_name=_PROXY_CREDENTIAL_SCHEMA,
            attributes={
                "app": self._app_name,
                "kind": "proxy-credentials",
                "id": key,
            },
        )

    def _store_secret(
        self,
        *,
        schema_name: str,
        attributes: dict[str, str],
        label: str,
        secret_value: str,
    ) -> None:
        schema = self._schema(schema_name)
        Secret.password_store_sync(
            schema,
            attributes,
            Secret.COLLECTION_DEFAULT,
            label,
            secret_value,
            None,
        )

    def _lookup_secret(
        self,
        *,
        schema_name: str,
        attributes: dict[str, str],
    ) -> str | None:
        schema = self._schema(schema_name)
        return Secret.password_lookup_sync(schema, attributes, None)

    def _clear_secret(
        self,
        *,
        schema_name: str,
        attributes: dict[str, str],
    ) -> None:
        schema = self._schema(schema_name)
        Secret.password_clear_sync(schema, attributes, None)

    def _schema(self, schema_name: str):
        if Secret is None:
            raise SecretStoreUnavailableError("Secure secret storage is not configured.")
        return Secret.Schema.new(
            schema_name,
            Secret.SchemaFlags.NONE,
            {
                "app": Secret.SchemaAttributeType.STRING,
                "kind": Secret.SchemaAttributeType.STRING,
                "id": Secret.SchemaAttributeType.STRING,
            },
        )


class ProfileSecretsService:
    """Application-facing secure profile password storage."""

    def __init__(self, secret_store: SecretStore) -> None:
        self._secret_store = secret_store

    def secure_storage_available(self) -> bool:
        return self._secret_store.available()

    def saved_state(self, profile_id: str) -> SavedCredentialState:
        return SavedCredentialState(
            profile_id=profile_id,
            password_saved=self.load_password(profile_id) is not None,
        )

    def save_password(self, profile_id: str, password: str) -> SavedCredentialState:
        normalized = password.strip()
        if not normalized:
            raise ValueError("Saved password cannot be empty.")
        self._secret_store.store_profile_password(profile_id, normalized)
        return SavedCredentialState(profile_id=profile_id, password_saved=True)

    def load_password(self, profile_id: str) -> str | None:
        try:
            return self._secret_store.load_profile_password(profile_id)
        except SecretStoreUnavailableError:
            return None

    def clear_password(self, profile_id: str) -> SavedCredentialState:
        self._secret_store.delete_profile_password(profile_id)
        return SavedCredentialState(profile_id=profile_id, password_saved=False)


def create_secret_store() -> SecretStore:
    if Secret is None:
        return UnavailableSecretStore()
    return LibsecretStore()


def saved_password_request_id(
    requests: tuple[AttentionRequest, ...],
) -> str | None:
    matches = [request for request in requests if _is_saved_password_request(request)]
    if len(matches) != 1:
        return None
    return matches[0].field_id


def _is_saved_password_request(request: AttentionRequest) -> bool:
    if request.field_type is AttentionFieldType.PASSPHRASE:
        return True
    if request.field_type is not AttentionFieldType.SECRET:
        return False
    label = request.label.lower()
    return "password" in label or "passphrase" in label
