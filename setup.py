from __future__ import annotations

from pathlib import Path
import re

from setuptools import find_packages, setup

ROOT = Path(__file__).resolve().parent
README_PATH = ROOT / "README.md"
PYPROJECT_PATH = ROOT / "pyproject.toml"
_VERSION_LINE_PATTERN = re.compile(r'^version\s*=\s*"(?P<version>[^"]+)"\s*$')


def read_version() -> str:
    current_section: str | None = None
    for raw_line in PYPROJECT_PATH.read_text(encoding="utf-8").splitlines():
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

    raise ValueError("Project version is missing from pyproject.toml")


setup(
    name="openvpn3-client-linux",
    version=read_version(),
    description="Native Linux GUI and CLI for OpenVPN 3 Linux",
    long_description=README_PATH.read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="Mehedi Hassan",
    author_email="howlader.mehedihassan@gmail.com",
    python_requires=">=3.10",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    package_data={"app": ["styles.css"]},
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "ovpn-gui=cli.main:main",
            "ovpn3-linux-gui=app.main:main",
        ]
    },
)
