"""OpenVPN 3 network capability adapter."""

from __future__ import annotations

from pathlib import Path
from shutil import which
from typing import Callable

from core.models import CapabilityState
from openvpn3.dbus_client import DBusClient


NETCFG_INTERFACE = "net.openvpn.v3.netcfg"


class NetCfgService:
    def __init__(
        self,
        client: DBusClient,
        *,
        path_exists: Callable[[Path], bool] | None = None,
        command_exists: Callable[[str], bool] | None = None,
    ) -> None:
        self._client = client
        self._path_exists = path_exists or Path.exists
        self._command_exists = command_exists or (lambda name: which(name) is not None)

    def detect_capabilities(self) -> tuple[CapabilityState, ...]:
        dco_paths = (
            Path("/sys/module/ovpn_dco_v2"),
            Path("/sys/module/ovpn_dco"),
        )
        dco_available = any(self._path_exists(path) for path in dco_paths)
        posture_agents = (
            "openvpn3-addon-devposture",
            "openvpn3-dpc-openvpninc",
        )
        posture_available = all(self._command_exists(name) for name in posture_agents)
        return (
            CapabilityState(
                key="dco",
                available=dco_available,
                reason=None if dco_available else "Kernel DCO module not detected.",
            ),
            CapabilityState(
                key="posture",
                available=posture_available,
                reason=(
                    None
                    if posture_available
                    else (
                        "Linux posture prerequisites were not detected. "
                        "Install the device posture helper packages before enabling posture-based access."
                    )
                ),
            ),
        )
