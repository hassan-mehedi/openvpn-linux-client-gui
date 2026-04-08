# Feature Parity Matrix

| Capability | Parity label | Initial status | Notes |
| --- | --- | --- | --- |
| Profile import from file | `parity-direct` | initial UI and CLI implemented | Core onboarding service, profile catalog, GTK file import, and CLI path exist. |
| Profile import from URL | `parity-direct` | initial UI and CLI implemented | HTTPS validation, duplicate detection, GTK URL import, and CLI path exist. |
| Token URL onboarding | `parity-linux-adapted` | initial UI and CLI implemented | `openvpn://import-profile/...` is normalized into an HTTPS import flow in core, GTK, and CLI paths. |
| Connection lifecycle state machine | `parity-direct` | initial orchestration implemented | Core transitions, validation, and session lifecycle coordination exist. |
| App settings model | `parity-linux-adapted` | initial GUI implemented | Strong typing and XDG config persistence exist, and the GTK shell now exposes the full settings surface with DCO capability-aware gating. |
| Proxy management | `parity-direct` | foundation implemented | Metadata persistence and secret-store abstraction exist. |
| Diagnostics export | `parity-linux-adapted` | initial GUI implemented | Report building and redaction logic exist, and the GTK shell now exposes a diagnostics center with reachability, capability, logs, and support bundle export. |
| GTK profile list UI | `parity-direct` | initial implementation | Main window lists profiles, supports search, import, refresh, connect, and delete actions. |
| Connect flow UI | `parity-direct` | challenge flow implemented | Main window now follows active session state, surfaces connect/pause/resume/disconnect actions, and drives multi-field credential/challenge prompts through the verified OpenVPN 3 input queue. |
| GUI navigation shell | `parity-linux-adapted` | initial implementation | The desktop shell now has dedicated Profiles, Settings, and Diagnostics views instead of a single-screen layout. |
| Native packaging | `parity-linux-adapted` | deferred | Packaging directories are prepared for DEB/RPM work. |
