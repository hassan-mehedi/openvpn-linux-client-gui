# Manual Testing

Run these commands from the repository root.

## Unit And Full Test Runs

```bash
.venv/bin/pytest tests/unit/test_openvpn_services.py -q
.venv/bin/pytest tests/unit/test_diagnostics.py -q
.venv/bin/pytest tests/unit/test_cli.py -q
.venv/bin/pytest tests/unit/test_main_window_helpers.py -q
.venv/bin/pytest
```

## GTK E2E Flows

Use a Python environment that can import both `pytest` and `gi`.

If `python3` already has both:

```bash
xvfb-run -a python3 -m pytest tests/e2e/test_gui_smoke.py -q
```

If `python3` has `gi` but not `pytest`, create a venv that can see system GTK
bindings:

```bash
python3 -m venv .venv-gtk --system-site-packages
.venv-gtk/bin/pip install pytest
xvfb-run -a .venv-gtk/bin/pytest tests/e2e/test_gui_smoke.py -q
```

## Live D-Bus Validation

Run these on a machine with OpenVPN 3 Linux installed and its D-Bus services
available:

First verify the interpreter can see both `dbus` and `gi`:

```bash
python3 -c "import dbus, gi; print('dbus+gi ok')"
```

If that succeeds, run the CLI against the source tree with the system Python:

```bash
PYTHONPATH=src python3 -m cli.main doctor dbus-surface
PYTHONPATH=src python3 -m cli.main doctor dbus-surface > dbus-surface-report.json
PYTHONPATH=src python3 -m cli.main doctor summary
PYTHONPATH=src python3 -m cli.main doctor export
```

If you prefer a virtualenv, create one that can see system packages and install
the project into it:

```bash
python3 -m venv .venv-live --system-site-packages
.venv-live/bin/pip install -e .
.venv-live/bin/python -c "import dbus, gi; print('dbus+gi ok')"
.venv-live/bin/python -m cli.main doctor dbus-surface
.venv-live/bin/python -m cli.main doctor dbus-surface > dbus-surface-report.json
.venv-live/bin/python -m cli.main doctor summary
.venv-live/bin/python -m cli.main doctor export
```

## Package Builds

Debian and Ubuntu:

```bash
dpkg-buildpackage -us -uc -b
```

Fedora-family:

```bash
sudo dnf install python3-build rpm-build pyproject-rpm-macros python3-devel python3-setuptools python3-wheel
mkdir -p ~/rpmbuild/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
python3 -m build --sdist --no-isolation
cp dist/openvpn3_client_linux-0.1.0.tar.gz ~/rpmbuild/SOURCES/
rpmbuild -ba packaging/rpm/openvpn3-client-linux.spec
```

## Installed-App Smoke Checks

After installing the package or setting up the runtime environment:

```bash
ovpn-gui --help
ovpn-gui doctor summary
ovpn-gui doctor dbus-surface
ovpn3-linux-gui
```
