"""OpenVPN 3 backend reachability adapter."""

from __future__ import annotations

from ovpn3_dbus.dbus_client import (
    BACKEND_SERVICE_NAME,
    CONFIGURATION_SERVICE_NAME,
    DBusClient,
    LOG_SERVICE_NAME,
    NETCFG_SERVICE_NAME,
    SESSION_SERVICE_NAME,
)


BACKEND_INTERFACE = "net.openvpn.v3.backends"


class BackendService:
    def __init__(self, client: DBusClient) -> None:
        self._client = client

    def reachable_services(self) -> dict[str, bool]:
        services = {
            CONFIGURATION_SERVICE_NAME: "/net/openvpn/v3/configuration",
            SESSION_SERVICE_NAME: "/net/openvpn/v3/sessions",
            LOG_SERVICE_NAME: "/net/openvpn/v3/log",
            NETCFG_SERVICE_NAME: "/net/openvpn/v3/netcfg",
            BACKEND_SERVICE_NAME: "/net/openvpn/v3/backends",
        }
        reachability: dict[str, bool] = {}
        for service, object_path in services.items():
            try:
                self._client.ping(service=service, object_path=object_path)
            except Exception:
                reachability[service] = False
            else:
                reachability[service] = True
        return reachability
