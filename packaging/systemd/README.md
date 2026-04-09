# Systemd Integration

This directory contains optional systemd unit files for system-mode operation.

## openvpn3-client-linux.service

A template user service that connects a profile at boot via the companion CLI.
This is a `parity-linux-adapted` feature equivalent to Windows service-daemon mode.

### Usage

```bash
# Enable auto-login profile at boot
systemctl --user enable openvpn3-client-linux@PROFILE_ID.service

# Start manually
systemctl --user start openvpn3-client-linux@PROFILE_ID.service

# Check status
systemctl --user status openvpn3-client-linux@PROFILE_ID.service
```

### Security

The unit runs with restricted privileges (NoNewPrivileges, ProtectSystem=strict).
It delegates to the `ovpn-gui` companion CLI which uses unprivileged D-Bus access.

### Installation

These units are NOT installed by default. Administrators who need system-mode
behavior should copy the unit file to `~/.config/systemd/user/` or
`/etc/systemd/user/` depending on scope requirements.
