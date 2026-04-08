"""Application settings persistence."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from core.models import AppSettings


class SettingsValidationError(ValueError):
    """Raised when settings values do not meet domain constraints."""


def default_config_dir(app_name: str = "openvpn3-client-linux") -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / app_name


class SettingsService:
    def __init__(self, config_dir: Path | None = None) -> None:
        self._config_dir = config_dir or default_config_dir()
        self._settings_path = self._config_dir / "settings.json"

    @property
    def settings_path(self) -> Path:
        return self._settings_path

    def load(self) -> AppSettings:
        if not self._settings_path.exists():
            return AppSettings()

        payload = json.loads(self._settings_path.read_text(encoding="utf-8"))
        settings = AppSettings.from_mapping(payload)
        self.validate(settings)
        return settings

    def save(self, settings: AppSettings) -> AppSettings:
        self.validate(settings)
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(
            json.dumps(settings.to_mapping(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return settings

    def update(self, **changes: Any) -> AppSettings:
        current = self.load()
        updated = replace(current, **changes)
        return self.save(updated)

    def validate(self, settings: AppSettings) -> None:
        if settings.connection_timeout <= 0:
            raise SettingsValidationError("connection_timeout must be greater than 0")

