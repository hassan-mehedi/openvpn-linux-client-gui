# Polkit Policy

This directory contains optional polkit policy files for privilege escalation
in system-mode operation.

## com.openvpn3.clientlinux.policy

Defines two privileged actions:

1. `manage-system-profiles` — Import/delete profiles in system scope
2. `manage-system-connections` — Start/stop system-level VPN connections

### Security Model

- Both actions require admin authentication (`auth_admin`)
- Active sessions get `auth_admin_keep` (password cached briefly)
- These policies are NOT installed by default
- Only relevant when system-mode operation is needed

### Installation

Copy to `/usr/share/polkit-1/actions/` if system-mode is required.
