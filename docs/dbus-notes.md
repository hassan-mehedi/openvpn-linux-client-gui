# D-Bus Notes

The adapter layer in `src/openvpn3/` owns all service names, object path
resolution, method invocation, and signal subscriptions.

The current code intentionally keeps raw D-Bus object paths inside the adapter
layer by converting them to opaque profile and session identifiers before they
reach the core or UI layers.

The OpenVPN 3 Linux v27 surface has now been partially verified against a live
system installation and the installed Python bindings:

- configuration manager: `/net/openvpn/v3/configuration`
- configuration methods: `FetchAvailableConfigs`, `Import`, `LookupConfigName`
- configuration object methods: `Fetch`, `FetchJSON`, `Remove`, `Validate`
- session manager: `/net/openvpn/v3/sessions`
- session manager methods: `NewTunnel`, `FetchAvailableSessions`,
  `FetchManagedInterfaces`, `LookupConfigName`, `LookupInterface`
- session object methods: `Ready`, `Connect`, `Disconnect`, `Pause`, `Resume`,
  `Restart`, `UserInputQueueGetTypeGroup`, `UserInputQueueCheck`,
  `UserInputQueueFetch`, `UserInputProvide`
- session signals: `AttentionRequired`, `StatusChange`, `Log`

The current adapter implementation has been updated to follow those real method
names and object paths.

On the current test machine, `net.openvpn.v3.configuration` and
`net.openvpn.v3.sessions` are D-Bus-activatable and may not own their bus names
until the first client request. The shared D-Bus client therefore retries a
small set of startup-race failures where the service name activates before the
manager object path is fully registered.
