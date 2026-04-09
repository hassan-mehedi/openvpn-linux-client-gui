from pathlib import Path

from core.models import (
    AppSettings,
    ConnectionProtocol,
    LaunchBehavior,
    SecurityLevel,
    ThemeMode,
)
from core.settings import SettingsService


def test_settings_full_roundtrip(tmp_path: Path) -> None:
    service = SettingsService(config_dir=tmp_path)

    custom = AppSettings(
        protocol=ConnectionProtocol.TCP,
        connection_timeout=60,
        launch_behavior=LaunchBehavior.RESTORE_CONNECTION,
        seamless_tunnel=True,
        theme=ThemeMode.DARK,
        security_level=SecurityLevel.STRICT,
        enforce_tls13=True,
        dco=True,
        block_ipv6=True,
        google_dns_fallback=True,
        local_dns=False,
        disconnect_confirmation=False,
    )
    service.save(custom)
    loaded = service.load()

    assert loaded.protocol is ConnectionProtocol.TCP
    assert loaded.connection_timeout == 60
    assert loaded.launch_behavior is LaunchBehavior.RESTORE_CONNECTION
    assert loaded.seamless_tunnel is True
    assert loaded.theme is ThemeMode.DARK
    assert loaded.security_level is SecurityLevel.STRICT
    assert loaded.enforce_tls13 is True
    assert loaded.dco is True
    assert loaded.block_ipv6 is True
    assert loaded.google_dns_fallback is True
    assert loaded.local_dns is False
    assert loaded.disconnect_confirmation is False


def test_settings_update_preserves_untouched_fields(tmp_path: Path) -> None:
    service = SettingsService(config_dir=tmp_path)
    service.save(AppSettings(protocol=ConnectionProtocol.UDP, dco=True))
    updated = service.update(theme=ThemeMode.LIGHT)
    assert updated.protocol is ConnectionProtocol.UDP
    assert updated.dco is True
    assert updated.theme is ThemeMode.LIGHT


def test_settings_defaults_on_missing_file(tmp_path: Path) -> None:
    service = SettingsService(config_dir=tmp_path)
    settings = service.load()
    assert settings.protocol is ConnectionProtocol.AUTO
    assert settings.launch_behavior is LaunchBehavior.NONE
    assert settings.theme is ThemeMode.SYSTEM
