# DEB Packaging Plan

This directory documents the Debian and Ubuntu native packaging metadata.

The actual `dpkg-buildpackage` input now lives in the repo root under
[`debian/`](../../debian).

## Implemented Contents

- `debian/control` with runtime and build dependencies
- `debian/rules` that builds the wheel and stages it into the package root
- `debian/openvpn3-client-linux.postinst` and `.postrm` cache refresh hooks
- `debian/source/format`, `debian/changelog`, and supporting metadata
- shared non-Python asset staging via `packaging/scripts/install_shared_assets.py`

## Package Shape

The first DEB packaging pass should prefer:

- one desktop package for the GUI and CLI
- optional split packages only for privileged or system-mode integrations

Maintainer scripts should stay minimal. Use them only for actions such as
desktop database or icon cache refresh when required by the target distro.

## Local Build

```bash
dpkg-buildpackage -us -uc -b
```

## Validation Checklist

- install on a clean Debian or Ubuntu machine
- launch from the desktop shell
- import via `openvpn://import-profile/...`
- verify `ovpn-gui doctor summary`
- remove the package cleanly without leaving privileged helpers behind
