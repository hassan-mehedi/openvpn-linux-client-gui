"""Packaging helper and metadata coverage."""

from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_packaging_helper():
    helper_path = PROJECT_ROOT / "packaging" / "scripts" / "install_shared_assets.py"
    spec = importlib.util.spec_from_file_location("install_shared_assets", helper_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive guard
        raise RuntimeError("Failed to load packaging helper module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_render_desktop_entry_replaces_template_tokens() -> None:
    helper = _load_packaging_helper()
    template = (PROJECT_ROOT / "packaging" / "desktop" / "openvpn3-client.desktop.in").read_text(
        encoding="utf-8"
    )

    rendered = helper.render_desktop_entry(template)

    assert "@APP_NAME@" not in rendered
    assert "@APP_ID@" not in rendered
    assert "Name=OpenVPN 3 Linux" in rendered
    assert "Exec=ovpn3-linux-gui %u" in rendered
    assert "MimeType=application/x-openvpn-profile;x-scheme-handler/openvpn;" in rendered


def test_install_shared_assets_stages_expected_files(tmp_path: Path) -> None:
    helper = _load_packaging_helper()

    installed = helper.install_shared_assets(destdir=tmp_path)

    expected_root = tmp_path / "usr" / "share"
    desktop_file = expected_root / "applications" / "com.openvpn3.clientlinux.desktop"
    icon_file = expected_root / "icons" / "hicolor" / "scalable" / "apps" / "com.openvpn3.clientlinux.svg"
    mime_file = expected_root / "mime" / "packages" / "openvpn3-client-linux.xml"
    metainfo_file = expected_root / "metainfo" / "com.openvpn3.clientlinux.metainfo.xml"

    assert installed == [desktop_file, icon_file, mime_file, metainfo_file]
    assert desktop_file.read_text(encoding="utf-8").startswith("[Desktop Entry]")
    assert "Icon=com.openvpn3.clientlinux" in desktop_file.read_text(encoding="utf-8")
    assert "<svg" in icon_file.read_text(encoding="utf-8")
    assert 'glob pattern="*.ovpn"' in mime_file.read_text(encoding="utf-8")
    assert "<component type=\"desktop-application\">" in metainfo_file.read_text(encoding="utf-8")


def test_debian_recipe_uses_shared_asset_helper() -> None:
    rules = (PROJECT_ROOT / "debian" / "rules").read_text(encoding="utf-8")
    control = (PROJECT_ROOT / "debian" / "control").read_text(encoding="utf-8")
    postinst = (PROJECT_ROOT / "debian" / "openvpn3-client-linux.postinst").read_text(
        encoding="utf-8"
    )

    assert "python3 packaging/scripts/install_shared_assets.py" in rules
    assert "python3 -m installer" in rules
    assert "gir1.2-secret-1" in control
    assert "update-mime-database" in postinst


def test_rpm_spec_includes_desktop_assets_and_cache_hooks() -> None:
    spec = (
        PROJECT_ROOT / "packaging" / "rpm" / "openvpn3-client-linux.spec"
    ).read_text(encoding="utf-8")

    assert "%pyproject_install" in spec
    assert "packaging/scripts/install_shared_assets.py" in spec
    assert "%post" in spec
    assert "%postun" in spec
    assert "%{_datadir}/applications/com.openvpn3.clientlinux.desktop" in spec
    assert "%{_datadir}/metainfo/com.openvpn3.clientlinux.metainfo.xml" in spec


def test_appstream_metainfo_references_desktop_launcher() -> None:
    metainfo = (
        PROJECT_ROOT / "packaging" / "metainfo" / "com.openvpn3.clientlinux.metainfo.xml"
    ).read_text(encoding="utf-8")

    assert "<id>com.openvpn3.clientlinux</id>" in metainfo
    assert "<launchable type=\"desktop-id\">com.openvpn3.clientlinux.desktop</launchable>" in metainfo
    assert "<releases>" in metainfo
