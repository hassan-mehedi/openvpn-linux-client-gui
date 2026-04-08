# Packaging Notes

Native packages are the first packaging target because the app needs integration
with:

- system D-Bus
- URI handlers
- XDG autostart
- optional systemd and polkit components

The repository now includes the expected packaging directory layout for DEB,
RPM, desktop integration, URI handling, systemd units, and polkit policy.

