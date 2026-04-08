# Product Spec

The application targets feature parity with OpenVPN Connect on Windows where
Linux backend capabilities allow it. The Linux implementation remains
D-Bus-first, privilege-aware, and state-machine-driven.

This initial implementation slice establishes the foundational layers required
by `AGENTS.md`:

- typed application core
- OpenVPN 3 adapter boundary
- automation CLI
- initial onboarding, settings, proxy, and diagnostics services

