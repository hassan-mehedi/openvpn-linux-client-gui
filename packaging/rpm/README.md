# RPM Packaging Plan

This directory contains the Fedora-family RPM packaging metadata.

## Implemented Contents

- `openvpn3-client-linux.spec` using the pyproject RPM macros
- file manifests for the Python install plus desktop integration assets
- `%post` and `%postun` cache refresh scriptlets
- shared non-Python asset staging via `packaging/scripts/install_shared_assets.py`

## Package Shape

The first RPM pass should mirror the DEB functional surface:

- one primary desktop package for GUI plus CLI automation
- optional subpackages for privileged integrations that should remain isolated

Scriptlets should stay narrow and distro-appropriate. Use them only for cache
updates or registration tasks that the platform requires.

## Local Build

```bash
# Install build dependencies (one-time)
sudo dnf install python3-build rpm-build pyproject-rpm-macros python3-devel python3-setuptools python3-wheel

# Build and install
make rpm-build
make rpm-install

# Reinstall after rebuilding
make rpm-reinstall

# Uninstall
make rpm-uninstall
```

## Validation Checklist

- install on Fedora or another RPM-based desktop
- launch from GNOME or another native desktop shell
- verify desktop entry, icon, and URI registration
- run `ovpn-gui doctor workflows`
- remove the package cleanly and confirm no stale integrations remain
