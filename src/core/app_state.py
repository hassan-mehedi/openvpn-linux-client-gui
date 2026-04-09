"""Lightweight runtime state persistence (XDG state directory)."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _default_state_dir(app_name: str = "openvpn3-client-linux") -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / app_name


class AppStateService:
    """Persists ephemeral runtime state that survives app restarts."""

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or _default_state_dir()
        self._state_path = self._state_dir / "state.json"

    def last_connected_profile_id(self) -> str | None:
        return self._read().get("last_connected_profile_id")

    def record_connected_profile(self, profile_id: str) -> None:
        state = self._read()
        state["last_connected_profile_id"] = profile_id
        self._write(state)

    def clear_last_connected_profile(self) -> None:
        state = self._read()
        state.pop("last_connected_profile_id", None)
        self._write(state)

    def _read(self) -> dict:
        if not self._state_path.exists():
            return {}
        try:
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, state: dict) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
