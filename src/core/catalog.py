"""Profile catalog and onboarding coordination."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Protocol

from core.models import ImportPreview, ImportSource, Profile
from core.onboarding import OnboardingService
from core.settings import default_config_dir


_UNSET = object()


class ProfileBackend(Protocol):
    def list_profiles(self) -> tuple[Profile, ...]:
        """Return known profiles."""

    def delete_profile(self, profile_id: str) -> None:
        """Delete a profile."""


class ProxyBackend(Protocol):
    def get_proxy(self, proxy_id: str) -> object | None:
        """Return a saved proxy by identifier."""


@dataclass(slots=True, frozen=True)
class ProfileCatalogSnapshot:
    profiles: tuple[Profile, ...]
    search: str = ""


class ProfileCatalogService:
    """Application-facing profile list and import service."""

    def __init__(
        self,
        backend: ProfileBackend,
        onboarding: OnboardingService,
        *,
        config_dir: Path | None = None,
        proxy_backend: ProxyBackend | None = None,
    ) -> None:
        self._backend = backend
        self._onboarding = onboarding
        self._config_dir = config_dir or default_config_dir()
        self._profile_overrides_path = self._config_dir / "profiles.json"
        self._proxy_backend = proxy_backend

    def list_profiles(self, search: str = "") -> ProfileCatalogSnapshot:
        normalized = search.strip().lower()
        profiles = [replace(profile) for profile in self._backend.list_profiles()]
        overrides = self._load_profile_overrides()

        for profile in profiles:
            override = overrides.get(profile.id)
            if override:
                if override.get("name"):
                    profile.name = str(override["name"])
                if "assigned_proxy_id" in override:
                    profile.assigned_proxy_id = override.get("assigned_proxy_id")

        if normalized:
            profiles = [
                item
                for item in profiles
                if normalized in item.name.lower()
                or normalized in item.id.lower()
                or normalized in item.source.value.lower()
            ]

        profiles.sort(
            key=lambda item: (
                item.last_used or item.imported_at,
                item.name.lower(),
            ),
            reverse=True,
        )
        return ProfileCatalogSnapshot(profiles=tuple(profiles), search=search)

    def get_profile(self, profile_id: str) -> Profile | None:
        for profile in self.list_profiles().profiles:
            if profile.id == profile_id:
                return profile
        return None

    def preview_file_import(
        self,
        path: Path,
        *,
        source: ImportSource = ImportSource.FILE,
    ) -> ImportPreview:
        return self._onboarding.prepare_file_import(path, source=source)

    def preview_url_import(self, url: str) -> ImportPreview:
        return self._onboarding.prepare_url_import(url)

    def preview_token_url_import(self, token_url: str) -> ImportPreview:
        return self._onboarding.prepare_token_url_import(token_url)

    def import_file(
        self,
        path: Path,
        *,
        source: ImportSource = ImportSource.FILE,
        profile_name: str | None = None,
    ) -> Profile:
        profile = self._onboarding.import_file(path, source=source, profile_name=profile_name)
        if profile_name:
            self.rename_profile(profile.id, profile_name)
        return profile

    def import_url(self, url: str, *, profile_name: str | None = None) -> Profile:
        profile = self._onboarding.import_url(url, profile_name=profile_name)
        if profile_name:
            self.rename_profile(profile.id, profile_name)
        return profile

    def import_token_url(self, token_url: str, *, profile_name: str | None = None) -> Profile:
        profile = self._onboarding.import_token_url(token_url, profile_name=profile_name)
        if profile_name:
            self.rename_profile(profile.id, profile_name)
        return profile

    def rename_profile(self, profile_id: str, profile_name: str) -> None:
        normalized = profile_name.strip()
        if not normalized:
            raise ValueError("Profile name cannot be empty.")
        self._update_profile_override(profile_id, name=normalized)

    def assign_proxy(self, profile_id: str, proxy_id: str | None) -> None:
        normalized = proxy_id.strip() if proxy_id else None
        if normalized and self._proxy_backend is not None:
            if self._proxy_backend.get_proxy(normalized) is None:
                raise KeyError(f"Unknown proxy: {normalized}")
        self._update_profile_override(profile_id, assigned_proxy_id=normalized or None)

    def clear_proxy_assignments(self, proxy_id: str) -> None:
        overrides = self._load_profile_overrides()
        changed = False
        for profile_id, values in list(overrides.items()):
            if values.get("assigned_proxy_id") != proxy_id:
                continue
            changed = True
            values.pop("assigned_proxy_id", None)
            if not values:
                overrides.pop(profile_id, None)
        if changed:
            self._write_profile_overrides(overrides)

    def delete_profile(self, profile_id: str) -> None:
        self._backend.delete_profile(profile_id)
        overrides = self._load_profile_overrides()
        if profile_id in overrides:
            overrides.pop(profile_id, None)
            self._write_profile_overrides(overrides)

    def _load_profile_overrides(self) -> dict[str, dict[str, str | None]]:
        if not self._profile_overrides_path.exists():
            return {}
        payload = json.loads(self._profile_overrides_path.read_text(encoding="utf-8"))
        overrides: dict[str, dict[str, str | None]] = {}
        for profile_id, raw_value in payload.items():
            normalized_id = str(profile_id)
            if isinstance(raw_value, str):
                name = raw_value.strip()
                if name:
                    overrides[normalized_id] = {"name": name}
                continue
            if not isinstance(raw_value, dict):
                continue
            values: dict[str, str | None] = {}
            raw_name = raw_value.get("name")
            if isinstance(raw_name, str) and raw_name.strip():
                values["name"] = raw_name.strip()
            raw_proxy_id = raw_value.get("assigned_proxy_id")
            if raw_proxy_id is None:
                if "assigned_proxy_id" in raw_value:
                    values["assigned_proxy_id"] = None
            elif isinstance(raw_proxy_id, str) and raw_proxy_id.strip():
                values["assigned_proxy_id"] = raw_proxy_id.strip()
            if values:
                overrides[normalized_id] = values
        return overrides

    def _write_profile_overrides(self, overrides: dict[str, dict[str, str | None]]) -> None:
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._profile_overrides_path.write_text(
            json.dumps(overrides, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _update_profile_override(
        self,
        profile_id: str,
        *,
        name: str | None | object = _UNSET,
        assigned_proxy_id: str | None | object = _UNSET,
    ) -> None:
        overrides = self._load_profile_overrides()
        current = dict(overrides.get(profile_id, {}))
        if name is not _UNSET:
            if name:
                current["name"] = str(name)
            else:
                current.pop("name", None)
        if assigned_proxy_id is not _UNSET:
            if assigned_proxy_id:
                current["assigned_proxy_id"] = str(assigned_proxy_id)
            else:
                current.pop("assigned_proxy_id", None)
        if current:
            overrides[profile_id] = current
        else:
            overrides.pop(profile_id, None)
        self._write_profile_overrides(overrides)
