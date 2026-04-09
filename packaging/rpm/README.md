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
sudo dnf install python3-build rpm-build pyproject-rpm-macros python3-devel python3-setuptools python3-wheel
mkdir -p ~/rpmbuild/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
python3 -m build --sdist --no-isolation
cp dist/openvpn3_client_linux-0.1.0.tar.gz ~/rpmbuild/SOURCES/
rpmbuild -ba packaging/rpm/openvpn3-client-linux.spec
```

## Validation Checklist

- install on Fedora or another RPM-based desktop
- launch from GNOME or another native desktop shell
- verify desktop entry, icon, and URI registration
- run `ovpn-gui doctor workflows`
- remove the package cleanly and confirm no stale integrations remain
