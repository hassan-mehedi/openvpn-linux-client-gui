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

- Python 3.10+
- PyGObject
- GTK4
- libadwaita
- libsecret bindings or equivalent secret-service integration
- OpenVPN 3 Linux service packages

If the desktop client is published broadly, release engineering should prefer
versioned native packages and signed GitHub release assets over a bespoke
in-app updater. That keeps upgrades aligned with Linux package expectations.

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
- the AppStream metainfo file
- the OpenVPN profile MIME definition

## Update Strategy

For the current packaging scope, users should discover and install updates
through release artifacts and native package tooling:

- GitHub Actions should publish the latest source, wheel, DEB, and RPM assets on every merge to `main`
- the install script now installs the latest stable packaged release from GitHub instead of cloning and building locally
- future APT or RPM repositories should provide normal package-manager upgrade flows

Until a repository exists, updates are manual:

- DEB users install the newer `.deb`
- RPM users install the newer `.rpm`
- install-script users rerun `install.sh`

## Release Automation

The repo now includes three GitHub Actions workflows:

- `.github/workflows/ci.yml`:
  runs tests plus Debian and RPM packaging smoke builds on pull requests and
  pushes to `main`
- `.github/workflows/release-main.yml`:
  runs on every push to `main`, computes a unique snapshot version, rewrites
  the Python, Debian, and RPM version metadata for that build, publishes
  source, wheel, DEB, and RPM artifacts, and creates a GitHub prerelease
- `.github/workflows/release-stable.yml`:
  runs on version tags such as `v0.2.0` or manual dispatch, rewrites the
  Python, Debian, and RPM version metadata for that stable release, publishes
  source, wheel, DEB, and RPM artifacts, and creates a non-prerelease GitHub
  release

The release workflow relies on `packaging/scripts/release_version.py` to keep
version metadata aligned across:

- `pyproject.toml`
- `debian/changelog`
- `packaging/rpm/openvpn3-client-linux.spec`

This avoids the earlier hardcoded `0.1.0` package filenames and makes each
automated build installable as a distinct package revision.

## Package-Manager Upgrades

Automatic GitHub Releases are only half of the update story. Native upgrade
commands still depend on repository distribution:

- `apt update` and `apt upgrade` only surface new versions after the package is
  installed from an APT repository listed in `sources.list`
- `dnf update` only surfaces new versions after the package is installed from a
  DNF or YUM repository such as Fedora COPR or a self-hosted RPM repository

Recommended rollout order:

1. Keep GitHub prerelease automation on `main` for fast validation.
2. Publish a stable APT repository for Debian and Ubuntu users.
3. Publish a Fedora COPR or another signed RPM repository.
4. Keep the AppStream metainfo release notes updated for stable releases.
5. Point `install.sh` at those repositories instead of cloning and building
   from source.

See [repository-publishing.md](/home/mehedi/Projects/personal/openvpn3-client-linux/docs/repository-publishing.md) for the detailed rollout plan.

Stable release checklist:

1. Bump `pyproject.toml` to the target stable version.
2. Update `packaging/metainfo/com.openvpn3.clientlinux.metainfo.xml` with the
   new release note entry.
3. Push a version tag such as `v0.2.0`.
4. Let `.github/workflows/release-stable.yml` publish the stable assets.

## Tray Support

The close-to-tray feature uses the Linux StatusNotifierItem protocol on the
session bus. Package metadata should therefore continue to ship `python3-dbus`
and should describe GNOME tray support honestly.

Recommended wording for release notes and user docs:

- **Verified**:
  Fedora 43 GNOME 49.5 with `gnome-shell-extension-appindicator` enabled
- **Expected**:
  KDE Plasma, Xfce with notification area or status notifier support,
  Cinnamon, MATE, and Debian or Ubuntu GNOME with the AppIndicator extension
- **Unsupported / limited**:
  GNOME without the AppIndicator or KStatusNotifier extension, and sessions
  without any StatusNotifier host

Behavior expectations:

- KDE Plasma generally works out of the box because Plasma ships a
  StatusNotifier-capable tray
- Xfce works when the panel exposes its notification area or status notifier
  support
- GNOME generally requires the `AppIndicator and KStatusNotifierItem Support`
  extension or an equivalent distro package such as
  `gnome-shell-extension-appindicator`
- when no host is available, the application falls back to background mode plus
  launcher and notification re-entry

Release notes and user docs should include distro-specific GNOME guidance:

- Fedora GNOME:
  `sudo dnf install gnome-shell-extension-appindicator`
- Debian or Ubuntu GNOME:
  `sudo apt install gnome-shell-extension-appindicator`
- after installation:
  `gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com`
