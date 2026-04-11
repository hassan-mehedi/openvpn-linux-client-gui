from __future__ import annotations

from pathlib import Path

from core import version as version_module


def test_application_version_reads_local_pyproject_when_package_metadata_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "openvpn3-client-linux"\nversion = "0.9.1.dev20260410"\n',
        encoding="utf-8",
    )
    module_path = tmp_path / "src" / "core" / "version.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text("# placeholder\n", encoding="utf-8")

    monkeypatch.setattr(version_module, "version", lambda _name: (_ for _ in ()).throw(version_module.PackageNotFoundError))
    monkeypatch.setattr(version_module, "__file__", str(module_path))

    assert version_module.application_version() == "0.9.1.dev20260410"


def test_application_version_falls_back_to_default_when_pyproject_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module_path = tmp_path / "src" / "core" / "version.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text("# placeholder\n", encoding="utf-8")

    monkeypatch.setattr(version_module, "version", lambda _name: (_ for _ in ()).throw(version_module.PackageNotFoundError))
    monkeypatch.setattr(version_module, "__file__", str(module_path))

    assert version_module.application_version() == version_module.DEFAULT_VERSION
