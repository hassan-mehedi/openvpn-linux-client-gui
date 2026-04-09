"""XDG autostart desktop entry management."""

from __future__ import annotations

import os
from pathlib import Path

from core.models import LaunchBehavior

_APP_ID = "com.openvpn3.clientlinux"
_APP_NAME = "OpenVPN 3 Client"
_GUI_EXECUTABLE = "ovpn3-linux-gui"

_LAUNCH_ACTION_MAP = {
    LaunchBehavior.START_APP: None,
    LaunchBehavior.CONNECT_LATEST: "connect-latest",
    LaunchBehavior.RESTORE_CONNECTION: "restore-connection",
}


def _default_autostart_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "autostart"


def _build_desktop_entry(behavior: LaunchBehavior) -> str:
    action = _LAUNCH_ACTION_MAP.get(behavior)
    exec_line = _GUI_EXECUTABLE
    if action is not None:
        exec_line = f"{_GUI_EXECUTABLE} --launch-action={action}"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        f"Name={_APP_NAME}\n"
        "Comment=OpenVPN 3 Linux desktop client (autostart)\n"
        f"Exec={exec_line}\n"
        f"Icon={_APP_ID}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "NoDisplay=true\n"
    )


class AutostartService:
    """Creates and removes XDG autostart desktop entries."""

    def __init__(self, autostart_dir: Path | None = None) -> None:
        self._autostart_dir = autostart_dir or _default_autostart_dir()
        self._entry_path = self._autostart_dir / f"{_APP_ID}.desktop"

    def sync(self, behavior: LaunchBehavior) -> None:
        """Write or remove the autostart entry based on launch behavior."""
        if behavior is LaunchBehavior.NONE:
            self._remove()
        else:
            self._write(behavior)

    def _write(self, behavior: LaunchBehavior) -> None:
        self._autostart_dir.mkdir(parents=True, exist_ok=True)
        self._entry_path.write_text(_build_desktop_entry(behavior), encoding="utf-8")

    def _remove(self) -> None:
        if self._entry_path.exists():
            self._entry_path.unlink()
