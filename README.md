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
- **Companion CLI** — full automation surface for profiles, sessions, settings, proxies, and diagnostics
- **Native packaging** — DEB and RPM recipes with desktop, icon, and MIME asset staging
- **System mode** — optional systemd user service and polkit policy for boot-time connections

## Screenshots

*Coming soon.*

## Requirements

- Python 3.11+
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

### From source (development)

```bash
git clone https://github.com/user/openvpn3-client-linux.git
cd openvpn3-client-linux
uv sync --dev
```

### DEB package

```bash
dpkg-buildpackage -us -uc -b
sudo dpkg -i ../openvpn3-client-linux_0.1.0_all.deb
```

### RPM package

```bash
python3 -m build --sdist --no-isolation
cp dist/openvpn3_client_linux-0.1.0.tar.gz ~/rpmbuild/SOURCES/
rpmbuild -ba packaging/rpm/openvpn3-client-linux.spec
sudo rpm -i ~/rpmbuild/RPMS/noarch/openvpn3-client-linux-0.1.0-1.noarch.rpm
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
  security.md
packaging/
  deb/              # Debian packaging
  rpm/              # RPM spec
  desktop/          # .desktop entry template
  icons/            # Application icon (SVG)
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

## System Mode

For unattended or boot-time VPN connections, optional systemd and polkit assets are provided in `packaging/systemd/` and `packaging/polkit/`. These are not installed by default. See the README files in those directories for usage.

## Known Limitations

- **D-Bus validation gap** — the adapter layer method signatures have not yet been validated against a live OpenVPN 3 Linux installation. Run `ovpn-gui doctor dbus-surface` to perform live validation. The adapters should be treated as a typed integration draft until this validation is complete.
- **No Flatpak/AppImage** — native DEB/RPM packages are the only supported distribution format due to deep D-Bus and desktop integration requirements.

## License

This project is licensed under the [Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/).

You are free to use, copy, modify, and share this software for personal, non-commercial purposes. Commercial use is not permitted.
