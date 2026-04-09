#!/usr/bin/env python3
"""Stage non-Python desktop integration assets for native packages."""

from __future__ import annotations

import argparse
from pathlib import Path


APP_ID = "com.openvpn3.clientlinux"
APP_NAME = "OpenVPN 3 Linux"
GUI_EXECUTABLE = "ovpn3-linux-gui"
ICON_NAME = APP_ID
DESKTOP_FILE_NAME = f"{APP_ID}.desktop"
ICON_FILE_NAME = f"{ICON_NAME}.svg"
MIME_PACKAGE_NAME = "openvpn3-client-linux.xml"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def render_desktop_entry(template: str) -> str:
    replacements = {
        "@APP_ID@": APP_ID,
        "@APP_NAME@": APP_NAME,
        "@GUI_EXECUTABLE@": GUI_EXECUTABLE,
        "@ICON_NAME@": ICON_NAME,
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered


def install_shared_assets(*, destdir: Path, prefix: Path = Path("/usr")) -> list[Path]:
    root = project_root()
    target_root = _join_destdir(destdir, prefix)
    applications_dir = target_root / "share" / "applications"
    icons_dir = target_root / "share" / "icons" / "hicolor" / "scalable" / "apps"
    mime_dir = target_root / "share" / "mime" / "packages"

    applications_dir.mkdir(parents=True, exist_ok=True)
    icons_dir.mkdir(parents=True, exist_ok=True)
    mime_dir.mkdir(parents=True, exist_ok=True)

    desktop_template = (root / "packaging" / "desktop" / "openvpn3-client.desktop.in").read_text(
        encoding="utf-8"
    )
    desktop_path = applications_dir / DESKTOP_FILE_NAME
    desktop_path.write_text(render_desktop_entry(desktop_template), encoding="utf-8")

    icon_source = root / "packaging" / "icons" / ICON_FILE_NAME
    icon_path = icons_dir / ICON_FILE_NAME
    icon_path.write_text(icon_source.read_text(encoding="utf-8"), encoding="utf-8")

    mime_source = root / "packaging" / "uri-handler" / MIME_PACKAGE_NAME
    mime_path = mime_dir / MIME_PACKAGE_NAME
    mime_path.write_text(mime_source.read_text(encoding="utf-8"), encoding="utf-8")

    return [desktop_path, icon_path, mime_path]


def _join_destdir(destdir: Path, prefix: Path) -> Path:
    prefix_parts = prefix.parts[1:] if prefix.is_absolute() else prefix.parts
    target = destdir
    for part in prefix_parts:
        target /= part
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage desktop integration assets for native package builds."
    )
    parser.add_argument(
        "--destdir",
        type=Path,
        required=True,
        help="Staging directory root such as a package buildroot.",
    )
    parser.add_argument(
        "--prefix",
        type=Path,
        default=Path("/usr"),
        help="Installation prefix inside the staging directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    installed = install_shared_assets(destdir=args.destdir, prefix=args.prefix)
    for path in installed:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
