"""Runtime preparation for profile connections."""

from __future__ import annotations

from typing import Protocol

from core.models import AppSettings, Profile, ProxyCredentials, ProxyDefinition


class ConnectionPreparationError(ValueError):
    """Raised when a profile cannot be prepared for connection."""


class SettingsBackend(Protocol):
    def load(self) -> AppSettings:
        """Return the current application settings."""


class ProfileCatalogBackend(Protocol):
    def get_profile(self, profile_id: str) -> Profile | None:
        """Return a profile with local overrides applied."""


class ProxyBackend(Protocol):
    def get_proxy(self, proxy_id: str) -> ProxyDefinition | None:
        """Return a saved proxy definition."""

    def load_proxy_credentials(self, proxy_id: str) -> ProxyCredentials | None:
        """Return stored credentials for a proxy when available."""


class ConfigurationBackend(Protocol):
    def apply_connection_settings(self, profile_id: str, settings: AppSettings) -> None:
        """Apply supported runtime settings to a profile."""

    def apply_proxy_assignment(
        self,
        profile_id: str,
        proxy: ProxyDefinition | None,
        credentials: ProxyCredentials | None,
    ) -> None:
        """Apply or clear the proxy assignment for a profile."""


class ConnectionPreparationService:
    """Applies runtime settings and proxy assignments before session creation."""

    def __init__(
        self,
        settings_backend: SettingsBackend,
        profile_catalog: ProfileCatalogBackend,
        proxy_backend: ProxyBackend,
        configuration_backend: ConfigurationBackend,
    ) -> None:
        self._settings_backend = settings_backend
        self._profile_catalog = profile_catalog
        self._proxy_backend = proxy_backend
        self._configuration_backend = configuration_backend

    def prepare_profile(self, profile_id: str) -> None:
        profile = self._profile_catalog.get_profile(profile_id)
        if profile is None:
            raise ConnectionPreparationError(f"Unknown profile: {profile_id}")

        self._configuration_backend.apply_connection_settings(
            profile_id,
            self._settings_backend.load(),
        )

        if not profile.assigned_proxy_id:
            self._configuration_backend.apply_proxy_assignment(profile_id, None, None)
            return

        proxy = self._proxy_backend.get_proxy(profile.assigned_proxy_id)
        if proxy is None:
            raise ConnectionPreparationError(
                f"Assigned proxy is missing for profile {profile.name}."
            )
        if not proxy.enabled:
            raise ConnectionPreparationError(
                f"Assigned proxy {proxy.name} is disabled for profile {profile.name}."
            )

        credentials = self._proxy_backend.load_proxy_credentials(proxy.id)
        if proxy.credential_ref and credentials is None:
            raise ConnectionPreparationError(
                f"Stored credentials are unavailable for proxy {proxy.name}."
            )

        self._configuration_backend.apply_proxy_assignment(
            profile_id,
            proxy,
            credentials,
        )
