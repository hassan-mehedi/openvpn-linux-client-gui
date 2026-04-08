"""OpenVPN 3 network capability adapter."""

from __future__ import annotations

from pathlib import Path

from core.models import CapabilityState
from openvpn3.dbus_client import DBusClient


NETCFG_INTERFACE = "net.openvpn.v3.netcfg"


class NetCfgService:
    def __init__(self, client: DBusClient) -> None:
        self._client = client

    def detect_capabilities(self) -> tuple[CapabilityState, ...]:
        dco_paths = (
            Path("/sys/module/ovpn_dco_v2"),
            Path("/sys/module/ovpn_dco"),
        )
        dco_available = any(path.exists() for path in dco_paths)
        return (
            CapabilityState(
                key="dco",
                available=dco_available,
                reason=None if dco_available else "Kernel DCO module not detected.",
            ),
        )
