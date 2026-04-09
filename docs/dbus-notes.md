# D-Bus Notes

The adapter layer in `src/openvpn3/` owns all service names, object path
resolution, method invocation, signal subscriptions, and live introspection
validation.

The current code intentionally keeps raw D-Bus object paths inside the adapter
layer by converting them to opaque profile and session identifiers before they
reach the core or UI layers.

## Current Status

The repository now includes a live validation path at
`src/openvpn3/introspection_service.py` plus a CLI entry point:

```bash
ovpn-gui doctor dbus-surface
```

That command introspects the current OpenVPN 3 Linux D-Bus services and compares
the live interfaces to the adapter assumptions for:

- configuration manager and a sampled configuration object
- session manager and a sampled session object, including `AttentionRequired`,
  `StatusChange`, and `Log` signals on the session interface
- log manager
- backend manager
- netcfg manager

## What Is Still Missing

This repo still does not ship a committed live introspection artifact from a
real OpenVPN 3 Linux installation. Until that capture is produced and reviewed,
the adapters should still be treated as an unverified implementation draft.

The remaining validation work is:

- run `ovpn-gui doctor dbus-surface` on a live OpenVPN 3 Linux machine
- compare any missing members to the current typed adapters
- update `src/openvpn3/` if the live interface differs
- preserve the resulting report in project documentation or release artifacts

## Runtime Notes

For current settings behavior, the adapter still treats `connection_timeout` as
a core-layer policy instead of a saved D-Bus configuration override. The
configuration adapter applies runtime overrides for settings such as protocol,
DNS fallback, seamless tunnel, TLS 1.3 enforcement, IPv6 handling, DNS scope,
and DCO through the configuration object when the backend supports them.

On live systems, `net.openvpn.v3.configuration` and `net.openvpn.v3.sessions`
may be D-Bus-activatable and may not own their bus names until the first client
request. The shared D-Bus client retries a small set of startup-race failures
where the service name activates before the manager object path is fully
registered.
