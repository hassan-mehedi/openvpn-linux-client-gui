from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_release_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "packaging"
        / "scripts"
        / "release_version.py"
    )
    spec = importlib.util.spec_from_file_location("release_version", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_release_plan_for_snapshot() -> None:
    module = _load_release_module()

    plan = module.build_release_plan(
        channel="snapshot",
        sha="abcdef123456",
        timestamp="202604101200",
    )

    assert plan.python_version.endswith(".dev202604101200")
    assert plan.deb_version.endswith("~dev202604101200-1")
    assert plan.rpm_release == "0.1.dev202604101200%{?dist}"
    assert plan.tag == "main-202604101200-abcdef1"
    assert plan.prerelease is True


def test_build_release_plan_for_stable() -> None:
    module = _load_release_module()

    plan = module.build_release_plan(
        channel="stable",
        release_version="0.2.0",
    )

    assert plan.python_version == "0.2.0"
    assert plan.deb_version == "0.2.0-1"
    assert plan.rpm_version == "0.2.0"
    assert plan.rpm_release == "1%{?dist}"
    assert plan.tag == "v0.2.0"
    assert plan.title == "OpenVPN 3 Linux Client 0.2.0"
    assert plan.prerelease is False


def test_apply_release_plan_updates_packaging_metadata(tmp_path: Path, monkeypatch) -> None:
    module = _load_release_module()

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "openvpn3-client-linux"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    rpm_spec = tmp_path / "packaging" / "rpm" / "openvpn3-client-linux.spec"
    rpm_spec.parent.mkdir(parents=True)
    rpm_spec.write_text(
        "Name: openvpn3-client-linux\nVersion:        0.1.0\nRelease:        1%{?dist}\n",
        encoding="utf-8",
    )
    debian_changelog = tmp_path / "debian" / "changelog"
    debian_changelog.parent.mkdir(parents=True)
    debian_changelog.write_text("", encoding="utf-8")

    monkeypatch.setattr(module, "PYPROJECT_PATH", pyproject)
    monkeypatch.setattr(module, "RPM_SPEC_PATH", rpm_spec)
    monkeypatch.setattr(module, "DEBIAN_CHANGELOG_PATH", debian_changelog)

    plan = module.ReleasePlan(
        python_version="0.1.0.dev202604101200",
        deb_version="0.1.0~dev202604101200-1",
        rpm_version="0.1.0",
        rpm_release="0.1.dev202604101200%{?dist}",
        tag="main-202604101200-abcdef1",
        title="Main snapshot",
        prerelease=True,
        changelog_message="Automated snapshot build from main.",
    )
    module.apply_release_plan(
        plan,
        maintainer_name="CI Bot",
        maintainer_email="ci@example.com",
        release_date=datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
    )

    assert 'version = "0.1.0.dev202604101200"' in pyproject.read_text(encoding="utf-8")
    spec_contents = rpm_spec.read_text(encoding="utf-8")
    assert "Version:        0.1.0" in spec_contents
    assert "Release:        0.1.dev202604101200%{?dist}" in spec_contents
    changelog = debian_changelog.read_text(encoding="utf-8")
    assert "openvpn3-client-linux (0.1.0~dev202604101200-1) unstable" in changelog
    assert "Automated snapshot build from main." in changelog
