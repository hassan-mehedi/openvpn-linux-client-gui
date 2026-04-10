from pathlib import Path

import pytest

from core.models import AppSettings
from core.settings import SettingsService, SettingsValidationError


def test_settings_round_trip(tmp_path: Path) -> None:
    service = SettingsService(config_dir=tmp_path)
    settings = AppSettings(
        connection_timeout=45,
        seamless_tunnel=True,
        close_to_tray=True,
    )

    service.save(settings)
    loaded = service.load()

    assert loaded.connection_timeout == 45
    assert loaded.seamless_tunnel is True
    assert loaded.close_to_tray is True


def test_settings_validation_rejects_non_positive_timeout(tmp_path: Path) -> None:
    service = SettingsService(config_dir=tmp_path)

    with pytest.raises(SettingsValidationError):
        service.save(AppSettings(connection_timeout=0))
