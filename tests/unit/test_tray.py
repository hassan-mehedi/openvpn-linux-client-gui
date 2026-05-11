from __future__ import annotations

from pathlib import Path

from app.tray import (
    FALLBACK_TRAY_ICON_NAME,
    TrayIntegration,
    TraySupport,
    current_desktop_environment,
    detect_tray_support,
    resolve_tray_icon_name,
)


def test_current_desktop_environment_combines_unique_values(monkeypatch) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME:GNOME")
    monkeypatch.setenv("DESKTOP_SESSION", "ubuntu")
    monkeypatch.setenv("GDMSESSION", "ubuntu")

    assert current_desktop_environment() == "GNOME / ubuntu"


def test_detect_tray_support_reports_available_host(monkeypatch) -> None:
    class FakeBus:
        def name_has_owner(self, name: str) -> bool:
            return name == "org.kde.StatusNotifierWatcher"

    class FakeDBus:
        @staticmethod
        def SessionBus():
            return FakeBus()

    monkeypatch.setattr("app.tray.dbus", FakeDBus)
    monkeypatch.setattr("app.tray.DBusGMainLoop", lambda set_as_default: None)

    support = detect_tray_support("KDE")

    assert support.available is True
    assert support.watcher_service == "org.kde.StatusNotifierWatcher"


def test_detect_tray_support_reports_gnome_extension_hint(monkeypatch) -> None:
    class FakeBus:
        def name_has_owner(self, _name: str) -> bool:
            return False

    class FakeDBus:
        @staticmethod
        def SessionBus():
            return FakeBus()

    monkeypatch.setattr("app.tray.dbus", FakeDBus)
    monkeypatch.setattr("app.tray.DBusGMainLoop", lambda set_as_default: None)

    support = detect_tray_support("GNOME")

    assert support.available is False
    assert "AppIndicator" in support.message


def test_tray_integration_starts_and_stops_backend() -> None:
    events: list[str] = []

    class FakeBackend:
        def __init__(self, **_kwargs) -> None:
            events.append("init")

        def start(self) -> None:
            events.append("start")

        def stop(self) -> None:
            events.append("stop")

    integration = TrayIntegration(
        app_id="openvpn3-client-linux",
        title="OpenVPN Connect",
        icon_name="com.openvpn3.clientlinux",
        detector=lambda _desktop: TraySupport(
            available=True,
            message="available",
            watcher_service="org.kde.StatusNotifierWatcher",
            watcher_interface="org.kde.StatusNotifierWatcher",
        ),
        backend_factory=FakeBackend,
    )

    integration.sync(
        enabled=True,
        toggle_window_visibility=lambda: None,
        show_window=lambda: None,
        quit_application=lambda: None,
        is_window_visible=lambda: True,
    )
    assert integration.is_active() is True

    integration.sync(
        enabled=False,
        toggle_window_visibility=lambda: None,
        show_window=lambda: None,
        quit_application=lambda: None,
        is_window_visible=lambda: True,
    )

    assert integration.is_active() is False
    assert events == ["init", "start", "stop"]


def test_resolve_tray_icon_name_uses_app_icon_when_installed(monkeypatch, tmp_path: Path) -> None:
    icons_dir = tmp_path / "icons" / "hicolor" / "scalable" / "apps"
    icons_dir.mkdir(parents=True)
    (icons_dir / "com.openvpn3.clientlinux.svg").write_text("<svg/>", encoding="utf-8")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    assert resolve_tray_icon_name("com.openvpn3.clientlinux") == "com.openvpn3.clientlinux"


def test_resolve_tray_icon_name_falls_back_when_app_icon_is_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    assert resolve_tray_icon_name("com.openvpn3.clientlinux") == FALLBACK_TRAY_ICON_NAME
