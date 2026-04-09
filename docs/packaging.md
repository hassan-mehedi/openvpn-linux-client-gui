# Packaging Notes

Native packages remain the first packaging target because this desktop client
needs deep Linux integration that generic app bundles do not handle well:

- OpenVPN 3 Linux D-Bus service access
- `openvpn://import-profile/...` URI handling
- XDG autostart
- optional systemd and polkit assets
- desktop launcher and icons installed into native locations

## Packaging Goals

The initial production packaging target is:

- DEB for Debian and Ubuntu families
- RPM for Fedora and related families

Flatpak and AppImage stay explicitly out of scope for the first production
pass. The packaging surface needs to model Linux-native integration first.

## Package Layout

Both package families should install the same functional surface:

- Python application code under the distro-appropriate site-packages path
- `ovpn-gui` companion CLI on `PATH`
- `ovpn3-linux-gui` desktop launcher entry point
- desktop file generated from `packaging/desktop/openvpn3-client.desktop.in`
- icons from `packaging/icons/`
- URI handler metadata from `packaging/uri-handler/`
- optional polkit assets from `packaging/polkit/`
- optional systemd units from `packaging/systemd/`

## Runtime Dependencies

Native packages should declare at least:

- Python 3.11+
- PyGObject
- GTK4
- libadwaita
- libsecret bindings or equivalent secret-service integration
- OpenVPN 3 Linux service packages

Package definitions should keep privilege boundaries explicit. The desktop GUI
must not silently acquire elevated helpers through package scripts.

## Integration Requirements

Packaging work is not complete until native packages handle:

- desktop menu launch
- icon registration
- URI association for `openvpn://import-profile/...`
- optional autostart assets for launch behavior
- optional system-mode extras isolated from the main desktop package

## Current Status

The repo now includes first-pass native packaging recipes:

- root-level `debian/` metadata for `dpkg-buildpackage`
- `packaging/rpm/openvpn3-client-linux.spec` for `rpmbuild`
- shared asset staging via `packaging/scripts/install_shared_assets.py`
- desktop, icon, and MIME assets for launcher and URI integration
- narrow post-install and post-remove cache refresh hooks

The following optional system-mode assets are now also available:

- `packaging/systemd/openvpn3-client-linux.service` — template user service
  unit for connecting profiles at boot via the companion CLI
- `packaging/polkit/com.openvpn3.clientlinux.policy` — polkit policy defining
  privileged actions for system-wide profile and connection management

These are NOT installed by default. See the README files in each directory
for installation and usage instructions.

## Build Commands

Debian and Ubuntu:

```bash
make deb-build
make deb-install
```

Fedora-family:

```bash
make rpm-build
make rpm-install
```

See the project Makefile for all available targets (`rpm-reinstall`,
`rpm-uninstall`, `deb-uninstall`).

Both packaging flows rely on the shared asset helper to stage:

- the rendered desktop entry
- the scalable app icon
- the OpenVPN profile MIME definition
