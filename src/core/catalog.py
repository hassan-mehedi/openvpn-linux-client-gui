"""Profile catalog and onboarding coordination."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Protocol

from core.models import ImportPreview, ImportSource, Profile
from core.onboarding import OnboardingService
from core.settings import default_config_dir


class ProfileBackend(Protocol):
    def list_profiles(self) -> tuple[Profile, ...]:
        """Return known profiles."""

    def delete_profile(self, profile_id: str) -> None:
        """Delete a profile."""


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
    ) -> None:
        self._backend = backend
        self._onboarding = onboarding
        self._config_dir = config_dir or default_config_dir()
        self._profile_overrides_path = self._config_dir / "profiles.json"

    def list_profiles(self, search: str = "") -> ProfileCatalogSnapshot:
        normalized = search.strip().lower()
        profiles = list(self._backend.list_profiles())
        overrides = self._load_profile_overrides()

        for profile in profiles:
            override = overrides.get(profile.id)
            if override:
                profile.name = override

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
        overrides = self._load_profile_overrides()
        overrides[profile_id] = normalized
        self._write_profile_overrides(overrides)

    def delete_profile(self, profile_id: str) -> None:
        self._backend.delete_profile(profile_id)
        overrides = self._load_profile_overrides()
        if profile_id in overrides:
            overrides.pop(profile_id, None)
            self._write_profile_overrides(overrides)

    def _load_profile_overrides(self) -> dict[str, str]:
        if not self._profile_overrides_path.exists():
            return {}
        payload = json.loads(self._profile_overrides_path.read_text(encoding="utf-8"))
        return {
            str(profile_id): str(profile_name).strip()
            for profile_id, profile_name in payload.items()
            if str(profile_name).strip()
        }

    def _write_profile_overrides(self, overrides: dict[str, str]) -> None:
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._profile_overrides_path.write_text(
            json.dumps(overrides, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
