# OpenVPN 3 Linux Client

A native Linux desktop GUI and companion CLI for [OpenVPN 3 Linux](https://github.com/OpenVPN/openvpn3-linux), built with GTK4, libadwaita, and Python.

The project integrates directly with the OpenVPN 3 Linux D-Bus service model — it does not shell out to `openvpn3` commands. All connection lifecycle, profile management, and configuration operations go through typed D-Bus adapter layers.

## Features

- **Profile management** — import from file, URL, or `openvpn://` token URL; search, rename, delete
- **Connection lifecycle** — connect, disconnect, pause, resume, restart with a formal state machine
- **Credential handling** — username/password, OTP/MFA, passphrase prompts driven by D-Bus attention events
- **Saved passwords** — optional secure storage via libsecret with auto-submission on connect
- **App settings** — protocol, timeout, launch behavior, theme, security level, TLS 1.3, DCO, IPv6, DNS
- **Proxy management** — saved proxy CRUD, per-profile assignment, connect-time proxy override
- **Session telemetry** — live bytes, packets, latency, throughput rate graph
- **Diagnostics** — service reachability, environment checks, guided recovery workflows, redacted support bundle export
- **Launch behavior** — XDG autostart with connect-latest or restore-last-connection on startup
- **Desktop integration** — `.ovpn` file association, `openvpn://` URI handler, light/dark theme
- **Window controls** — custom minimize, maximize, and close buttons in the top bar
- **Background close behavior** — optional close-to-tray/background preference with native StatusNotifier support where available and launcher/notification fallback elsewhere
- **Companion CLI** — full automation surface for profiles, sessions, settings, proxies, and diagnostics
- **Native packaging** — DEB and RPM recipes with desktop, icon, and MIME asset staging
- **Software center metadata** — AppStream metainfo for GNOME Software, KDE Discover, and release-note surfacing
- **System mode** — optional systemd user service and polkit policy for boot-time connections

## Screenshots

*Coming soon.*

## Requirements

- Python 3.10+
- [OpenVPN 3 Linux](https://github.com/OpenVPN/openvpn3-linux) installed and running
- GTK4 and libadwaita
- PyGObject (`python3-gi`)
- python3-dbus
- libsecret (`gir1.2-secret-1`)

### Fedora

```bash
sudo dnf install python3-gobject gtk4 libadwaita python3-dbus libsecret openvpn3-client
```

### Ubuntu / Debian

```bash
sudo apt install gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-secret-1 python3-gi python3-dbus openvpn3
```

## Installation

### Quick install (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/hassan-mehedi/openvpn-linux-client-gui/main/install.sh | bash
```

This detects the current distro and version, fetches the latest stable DEB or RPM release from GitHub, bootstraps the required OpenVPN 3 repository on Debian-family systems, and installs the package with the native package manager.

### From source (development)

```bash
git clone https://github.com/hassan-mehedi/openvpn-linux-client-gui.git
cd openvpn3-client-linux
uv sync --dev
```

### DEB package (Debian/Ubuntu)

```bash
make deb-build
make deb-install

# Uninstall
make deb-uninstall
```

### RPM package (Fedora)

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

## Usage

### GUI

```bash
ovpn3-linux-gui
```

Or launch from your desktop application menu.

### CLI

```bash
# Profile management
ovpn-gui profiles list
ovpn-gui profiles import-file /path/to/profile.ovpn
ovpn-gui profiles import-url https://vpn.example.com/profile.ovpn
ovpn-gui profiles rename PROFILE_ID "My VPN"
ovpn-gui profiles remove PROFILE_ID

# Sessions
ovpn-gui sessions connect PROFILE_ID
ovpn-gui sessions status SESSION_ID
ovpn-gui sessions pause SESSION_ID
ovpn-gui sessions resume SESSION_ID
ovpn-gui sessions disconnect SESSION_ID

# Settings
ovpn-gui settings list
ovpn-gui settings set protocol tcp
ovpn-gui settings set launch_behavior restore-connection

# Proxy management
ovpn-gui proxies list
ovpn-gui proxies add --name "Corp Proxy" --type http --host proxy.corp.com --port 8080
ovpn-gui profiles assign-proxy PROFILE_ID PROXY_ID

# Diagnostics
ovpn-gui doctor
ovpn-gui doctor logs
ovpn-gui doctor export
ovpn-gui doctor dbus-surface
```

Add `--json` to most commands for machine-readable output.

## Architecture

```
┌─────────────────────────────────────┐
│  GTK4 + libadwaita UI              │
│  (Profiles, Settings, Diagnostics)  │
├─────────────────────────────────────┤
│  Core Services                      │
│  state machine, settings, secrets,  │
│  onboarding, proxies, diagnostics,  │
│  telemetry, catalog, autostart      │
├─────────────────────────────────────┤
│  OpenVPN 3 D-Bus Adapter Layer      │
│  configuration, session, attention, │
│  log, backend, netcfg, introspect   │
├─────────────────────────────────────┤
│  OpenVPN 3 Linux D-Bus Services     │
└─────────────────────────────────────┘
```

- **UI layer** (`src/app/`) — GTK4 windows, dialogs, and widgets
- **Core layer** (`src/core/`) — business logic, state machine, settings, secrets, diagnostics
- **Adapter layer** (`src/openvpn3/`) — typed D-Bus client wrapping OpenVPN 3 Linux services
- **CLI** (`src/cli/`) — companion CLI using the same core services

The GUI and CLI share the same `ServiceContainer` (dependency injection in `core/bootstrap.py`), so behavior is consistent across interfaces.

## Project Structure

```
src/
  app/              # GTK4/libadwaita UI
    windows/        # Main application window
    dialogs/        # Import, proxy, attention, profile details dialogs
  core/             # Business logic
    state_machine.py
    session_manager.py
    settings.py
    secrets.py
    onboarding.py
    proxies.py
    diagnostics.py
    catalog.py
    autostart.py
    app_state.py
    bootstrap.py
  openvpn3/         # D-Bus adapter layer
    dbus_client.py
    configuration_service.py
    session_service.py
    attention_service.py
    log_service.py
    netcfg_service.py
    backend_service.py
    introspection_service.py
  cli/              # Companion CLI
tests/
  unit/             # 122 unit tests
  integration/      # 30 integration tests
  e2e/              # 6 GTK smoke tests
docs/
  feature-parity.md
  product-spec.md
  dbus-notes.md
  packaging.md
  repository-publishing.md
  security.md
.github/workflows/
  ci.yml            # Tests plus DEB/RPM packaging smoke checks
  release-main.yml  # Automatic GitHub prerelease for every merge to main
  release-stable.yml # Stable GitHub release for version tags such as v0.2.0
packaging/
  deb/              # Debian packaging
  rpm/              # RPM spec
  desktop/          # .desktop entry template
  icons/            # Application icon (SVG)
  metainfo/         # AppStream metadata for software centers
  uri-handler/      # MIME type definition
  systemd/          # Optional user service unit
  polkit/           # Optional privilege policy
```

## Testing

```bash
# Run all tests
uv run pytest

# Unit and integration only
uv run pytest tests/unit tests/integration -v

# E2E tests (requires display or Xvfb)
xvfb-run -a uv run pytest tests/e2e -v -m e2e

# Specific test file
uv run pytest tests/unit/test_state_machine.py -v
```

## Desktop Integration

When installed via native packages, the app registers:

- **Application launcher** in the desktop menu (Network category)
- **File association** for `.ovpn` files (`application/x-openvpn-profile`)
- **URI handler** for `openvpn://import-profile/...` token URLs
- **XDG autostart** entry (when launch behavior is configured)
- **AppStream metadata** for software centers such as GNOME Software and KDE Discover

When **Close to system tray** is enabled in Settings, closing the window keeps
the application running in the background instead of terminating it. On
desktops with a StatusNotifier host, the app registers a real tray icon with
Show Window and Quit actions. On desktops without one, the app falls back to
the launcher and background notification.

### Tray Support Matrix

The tray feature uses the Linux **StatusNotifierItem** protocol. Whether the
icon appears depends more on the desktop environment than on the distro alone.

Support levels used below:

- **Verified**: manually confirmed during project testing
- **Expected**: not manually verified in this repo yet, but should work when the desktop exposes a StatusNotifier host
- **Unsupported / limited**: tray icon is not expected to appear unless the user adds extra shell or panel support

#### Verified

- **Fedora 43 / GNOME 49.5**:
  Verified with the GNOME AppIndicator extension enabled:

  ```bash
  sudo dnf install gnome-shell-extension-appindicator
  gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
  ```

  Log out and back in if GNOME Shell does not pick it up immediately.
  Without that extension, GNOME falls back to launcher or notification re-entry
  instead of showing a real tray icon.

#### Expected

- **Fedora KDE Plasma**:
  Plasma normally ships a StatusNotifier-capable tray, so no extra tray package
  is typically required.

- **Fedora Xfce**:
  Xfce should work when the panel exposes its notification area or status
  notifier support. If the icon does not appear, add the panel's
  **Notification Area** item, or install/add `xfce4-statusnotifier-plugin` on
  older setups.

- **Ubuntu GNOME**:
  Ubuntu often ships AppIndicator support already. If the tray icon does not
  appear, install or enable:

  ```bash
  sudo apt install gnome-shell-extension-appindicator
  gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
  ```

- **Debian GNOME**:
  Install and enable the same extension:

  ```bash
  sudo apt install gnome-shell-extension-appindicator
  gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
  ```

- **Ubuntu or Debian KDE Plasma**:
  No additional tray package is usually needed.

- **Ubuntu or Debian Xfce**:
  Ensure the panel has the **Notification Area** item enabled. On older Xfce
  setups, the separate status notifier plugin may still be needed.

- **Cinnamon / MATE**:
  These desktops usually work when their panel exposes AppIndicator or
  StatusNotifier support. If the icon does not appear, first verify the panel
  includes its notification area or tray applet.

#### Unsupported Or Limited

- **GNOME without the AppIndicator/KStatusNotifier extension**:
  GNOME does not expose StatusNotifier tray icons by default. The app will
  still keep running in the background, but it is reopened from the launcher or
  notification rather than from a tray icon.

- **Tiling WMs / minimal sessions without a tray host**:
  If the session does not provide a StatusNotifier host, the app falls back to
  background mode only.

### Tray Troubleshooting

Use this checklist when the app closes to background but no tray icon appears:

1. Turn on **Close to system tray** in the app settings.
2. Confirm your desktop provides a tray host or compatible extension.
3. For GNOME, verify the extension is enabled:

   ```bash
   gnome-extensions list --enabled | grep appindicator
   ```

4. Restart the application after enabling the extension:

   ```bash
   pkill -f "python3 -m app.main"
   PYTHONPATH=src python3 -m app.main
   ```

5. If the tray icon still does not appear, the app will continue to run in the
   background and can be reopened from the desktop launcher or notification.

## Releases And Updates

For a published build, the cleanest release story is:

- automatically publish GitHub Releases with matching source, wheel, DEB, and RPM artifacts
- keep the install script pointed at the latest stable release
- publish an APT repository and Fedora COPR or RPM repository later if you want native package-manager updates

How users know an update exists:

- GitHub Releases notifications, release notes, and the project changelog
- package manager update lists after the app is published through an APT or RPM repository
- GNOME Software, KDE Discover, or other software centers once AppStream metadata and package repositories are in place
- the installer page or README pointing to the latest release version

How users update:

- **Install script users**: rerun the same `install.sh` command to fetch and install the latest release
- **DEB users**: download the new `.deb` from Releases and install it over the existing package, or upgrade via APT once a repository exists
- **RPM users**: install the newer `.rpm` over the existing package, or upgrade with DNF once a repository exists
- **Source users**: pull the new tag or branch, then rebuild and reinstall

What is automated today:

- every push to `main` triggers `.github/workflows/release-main.yml`
- that workflow computes a unique snapshot version, builds source, wheel, DEB, and RPM artifacts, and publishes a GitHub prerelease automatically
- pushing a version tag such as `v0.2.0` triggers `.github/workflows/release-stable.yml`
- the stable workflow rebuilds the same source as a non-prerelease and publishes source, wheel, DEB, RPM, and checksum artifacts
- `.github/workflows/ci.yml` runs tests and DEB/RPM packaging smoke checks on pull requests and pushes

What is NOT automatic yet:

- `sudo apt update && sudo apt upgrade` cannot update this app until users install it from an APT repository you control
- `sudo dnf update` cannot update this app until users install it from Fedora COPR or another RPM repository you control
- the app does not currently include an in-app self-updater, and that is intentional

Recommended next step for the easiest user experience:

1. Keep the new GitHub release automation for build artifacts.
2. Publish an APT repository for Debian or Ubuntu users.
3. Publish a Fedora COPR project or another signed RPM repository.
4. Keep the AppStream metainfo updated with release notes for stable releases.
5. Switch `install.sh` from GitHub release assets to repository-based installation once the APT and RPM repositories exist.

Until those repositories exist, native package distribution should still be
treated as the source of truth for upgrades, but upgrades remain manual.

For the concrete repository rollout plan, see [docs/repository-publishing.md](/home/mehedi/Projects/personal/openvpn3-client-linux/docs/repository-publishing.md).

Stable release flow:

1. Bump the version in `pyproject.toml` when you are ready for a new stable release.
2. Update the AppStream `<releases>` section in `packaging/metainfo/com.openvpn3.clientlinux.metainfo.xml`.
3. Push a tag such as `v0.2.0`.
4. GitHub Actions publishes the stable release automatically.

## System Mode

For unattended or boot-time VPN connections, optional systemd and polkit assets are provided in `packaging/systemd/` and `packaging/polkit/`. These are not installed by default. See the README files in those directories for usage.

## Known Limitations

- **D-Bus validation gap** — the adapter layer method signatures have not yet been validated against a live OpenVPN 3 Linux installation. Run `ovpn-gui doctor dbus-surface` to perform live validation. The adapters should be treated as a typed integration draft until this validation is complete.
- **No Flatpak/AppImage** — native DEB/RPM packages are the only supported distribution format due to deep D-Bus and desktop integration requirements.

## License

This project is licensed under the [Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/).

You are free to use, copy, modify, and share this software for personal, non-commercial purposes. Commercial use is not permitted.
