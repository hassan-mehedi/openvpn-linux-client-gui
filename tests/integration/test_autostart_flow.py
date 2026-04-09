from pathlib import Path
from core.autostart import AutostartService
from core.models import LaunchBehavior


def test_enable_autostart_creates_desktop_entry(tmp_path: Path) -> None:
    service = AutostartService(autostart_dir=tmp_path)
    service.sync(LaunchBehavior.START_APP)
    entry = tmp_path / "com.openvpn3.clientlinux.desktop"
    assert entry.exists()
    content = entry.read_text()
    assert "X-GNOME-Autostart-enabled=true" in content
    assert "Exec=" in content


def test_disable_autostart_removes_desktop_entry(tmp_path: Path) -> None:
    service = AutostartService(autostart_dir=tmp_path)
    service.sync(LaunchBehavior.START_APP)
    service.sync(LaunchBehavior.NONE)
    entry = tmp_path / "com.openvpn3.clientlinux.desktop"
    assert not entry.exists()


def test_connect_latest_adds_argument(tmp_path: Path) -> None:
    service = AutostartService(autostart_dir=tmp_path)
    service.sync(LaunchBehavior.CONNECT_LATEST)
    entry = tmp_path / "com.openvpn3.clientlinux.desktop"
    content = entry.read_text()
    assert "--launch-action=connect-latest" in content


def test_restore_connection_adds_argument(tmp_path: Path) -> None:
    service = AutostartService(autostart_dir=tmp_path)
    service.sync(LaunchBehavior.RESTORE_CONNECTION)
    entry = tmp_path / "com.openvpn3.clientlinux.desktop"
    content = entry.read_text()
    assert "--launch-action=restore-connection" in content
