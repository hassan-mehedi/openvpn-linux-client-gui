"""Application version helpers."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import re

PACKAGE_NAME = "openvpn3-client-linux"
DEFAULT_VERSION = "0.1.0"
_VERSION_LINE_PATTERN = re.compile(r'^version\s*=\s*"(?P<version>[^"]+)"\s*$')


def application_version() -> str:
    """Return the installed package version or the local source version."""

    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return _local_project_version()


def _local_project_version() -> str:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        return _read_project_version(pyproject_path)
    except FileNotFoundError:
        return DEFAULT_VERSION


def _read_project_version(pyproject_path: Path) -> str:
    current_section: str | None = None
    for raw_line in pyproject_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            continue
        if current_section != "project":
            continue

        match = _VERSION_LINE_PATTERN.fullmatch(line)
        if match:
            return match.group("version")

    return DEFAULT_VERSION
