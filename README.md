# OpenVPN 3 Linux Client GUI

Production-oriented Linux desktop GUI and automation CLI for OpenVPN 3 Linux.

The project is intentionally built around the OpenVPN 3 Linux D-Bus service
model. The desktop UI, companion CLI, onboarding flow, settings, diagnostics,
and connection lifecycle logic all sit above typed adapter and core layers.

## Current Scope

The repository currently contains the initial production foundation:

- repository skeleton and packaging metadata
- typed core models and state machine
- onboarding, settings, proxy, secrets, and diagnostics services
- multi-page GTK shell with Profiles, Settings, and Diagnostics views
- OpenVPN 3 adapter layer behind a shared D-Bus client abstraction
- companion CLI entry point
- unit and integration-style tests for the first behaviors

The live D-Bus method signatures still need validation against OpenVPN 3 Linux
introspection data before the adapters can be considered production-complete.

## Development

```bash
uv run pytest
uv run python -m cli.main --help
```

For live GTK and D-Bus development on Linux, the current implementation relies
on the system Python runtime having `python3-gobject` and `python3-dbus`
available. The repo still uses `uv` for dependency management and test runs.
