"""Application version helpers."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib

PACKAGE_NAME = "openvpn3-client-linux"
DEFAULT_VERSION = "0.1.0"


def application_version() -> str:
    """Return the installed package version or the local source version."""

    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return _local_project_version()


def _local_project_version() -> str:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as handle:
            project = tomllib.load(handle)["project"]
    except (FileNotFoundError, KeyError, tomllib.TOMLDecodeError):
        return DEFAULT_VERSION

    local_version = project.get("version")
    return local_version if isinstance(local_version, str) and local_version else DEFAULT_VERSION
