# OpenVPN 3 Linux Client GUI

Production-oriented Linux desktop GUI and automation CLI for OpenVPN 3 Linux.

The project is intentionally built around the OpenVPN 3 Linux D-Bus service
model. The desktop UI, companion CLI, onboarding flow, settings, diagnostics,
and connection lifecycle logic all sit above typed adapter and core layers.

## Current Scope

The repository currently contains the initial production foundation:

- repository skeleton and first-pass native packaging recipes
- typed core models and state machine
- onboarding, settings, proxy, secrets, and diagnostics services
- multi-page GTK shell with Profiles, Settings, and Diagnostics views
- saved proxy CRUD from the Settings page plus per-profile proxy assignment
- connect-time application of assigned proxies plus validated runtime config defaults
- live session telemetry with bytes, rates, latency, and throughput history
- OpenVPN 3 adapter layer behind a shared D-Bus client abstraction
- companion CLI entry point
- Debian `debian/` packaging metadata plus an RPM spec and shared desktop asset staging helper
- guided diagnostics workflows and redacted support-bundle export
- initial GTK-backed E2E smoke coverage under `tests/e2e`
- unit and integration-style tests for the first behaviors

The live D-Bus method signatures still need validation against OpenVPN 3 Linux
introspection data before the adapters can be considered production-complete.
That validation gap is still real. The current code should be treated as a
typed D-Bus integration draft until the repository captures live introspection
results and verifies the adapter methods against them.

## Live D-Bus Validation Gap

The remaining production-readiness work for the adapter layer is:

- capture introspection data from a live OpenVPN 3 Linux installation
- compare the current configuration, session, log, backend, and netcfg adapter
  assumptions against that data
- update method signatures, property names, and signal mappings where they
  differ
- preserve the validated surface in documentation and regression tests

The repo now includes a live validation command for that work:

```bash
ovpn-gui doctor dbus-surface
```

## Development

```bash
uv run pytest
uv run python -m cli.main --help
```

For live GTK and D-Bus development on Linux, the current implementation relies
on the system Python runtime having `python3-gobject` and `python3-dbus`
available. The repo still uses `uv` for dependency management and test runs.
