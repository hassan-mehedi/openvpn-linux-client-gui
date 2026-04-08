"""Shared D-Bus client abstraction."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Callable, Protocol


CONFIGURATION_SERVICE_NAME = "net.openvpn.v3.configuration"
SESSION_SERVICE_NAME = "net.openvpn.v3.sessions"
ATTENTION_SERVICE_NAME = "net.openvpn.v3.attention"
LOG_SERVICE_NAME = "net.openvpn.v3.log"
NETCFG_SERVICE_NAME = "net.openvpn.v3.netcfg"
BACKEND_SERVICE_NAME = "net.openvpn.v3.backends"

ROOT_OBJECT_PATH = "/net/openvpn/v3"
DBUS_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
DBUS_PEER_INTERFACE = "org.freedesktop.DBus.Peer"


class DBusTransport(Protocol):
    def call(
        self,
        *,
        bus_name: str,
        object_path: str,
        interface: str,
        method: str,
        params: Any | None = None,
        signature: str | None = None,
    ) -> Any:
        """Invoke a D-Bus method."""

    def subscribe(
        self,
        *,
        bus_name: str,
        object_path: str,
        interface: str,
        signal_name: str,
        callback: Callable[[Any], None],
    ) -> Callable[[], None]:
        """Subscribe to a D-Bus signal and return an unsubscribe callback."""


@dataclass(slots=True)
class DBusClient:
    transport: DBusTransport
    activation_retries: int = 3
    activation_retry_delay: float = 0.2

    def call_method(
        self,
        *,
        service: str,
        object_path: str,
        interface: str,
        method: str,
        params: Any | None = None,
        signature: str | None = None,
    ) -> Any:
        attempts = max(1, self.activation_retries)
        for attempt in range(attempts):
            try:
                return self.transport.call(
                    bus_name=service,
                    object_path=object_path,
                    interface=interface,
                    method=method,
                    params=params,
                    signature=signature,
                )
            except Exception as exc:
                if attempt == attempts - 1 or not _is_activation_race(exc):
                    raise
                time.sleep(self.activation_retry_delay)
        raise RuntimeError("Unreachable D-Bus retry loop")

    def get_property(self, *, service: str, object_path: str, interface: str, name: str) -> Any:
        return self.call_method(
            service=service,
            object_path=object_path,
            interface=DBUS_PROPERTIES_INTERFACE,
            method="Get",
            signature="ss",
            params=(interface, name),
        )

    def get_all_properties(self, *, service: str, object_path: str, interface: str) -> dict[str, Any]:
        properties = self.call_method(
            service=service,
            object_path=object_path,
            interface=DBUS_PROPERTIES_INTERFACE,
            method="GetAll",
            signature="s",
            params=(interface,),
        )
        return dict(properties or {})

    def ping(self, *, service: str, object_path: str) -> None:
        self.call_method(
            service=service,
            object_path=object_path,
            interface=DBUS_PEER_INTERFACE,
            method="Ping",
        )

    def subscribe_signal(
        self,
        *,
        service: str,
        object_path: str,
        interface: str,
        signal_name: str,
        callback: Callable[[Any], None],
    ) -> Callable[[], None]:
        return self.transport.subscribe(
            bus_name=service,
            object_path=object_path,
            interface=interface,
            signal_name=signal_name,
            callback=callback,
        )


class GioDBusTransport:
    """Runtime Gio-backed transport.

    This class remains lightly wrapped because tests use fake transports. The
    live method signatures should be validated against OpenVPN 3 Linux
    introspection data before production rollout.
    """

    def __init__(self) -> None:
        try:
            import gi

            gi.require_version("Gio", "2.0")
            from gi.repository import Gio
        except (ImportError, ValueError) as exc:  # pragma: no cover - system-dependent
            raise RuntimeError("PyGObject with Gio is required for D-Bus access.") from exc

        self._gio = Gio
        self._connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

    def call(
        self,
        *,
        bus_name: str,
        object_path: str,
        interface: str,
        method: str,
        params: Any | None = None,
        signature: str | None = None,
    ) -> Any:  # pragma: no cover - depends on system bus
        variant = None
        if params is not None:
            if signature is not None:
                body = tuple(params) if isinstance(params, Sequence) and not isinstance(params, (str, bytes, bytearray)) else (params,)
                variant = self._gio.Variant(f"({signature})", body)
            else:
                variant = self._gio.Variant("a{sv}", params)
        result = self._connection.call_sync(
            bus_name,
            object_path,
            interface,
            method,
            variant,
            None,
            self._gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        return _normalize_variant_result(result.unpack() if result is not None else None)

    def subscribe(
        self,
        *,
        bus_name: str,
        object_path: str,
        interface: str,
        signal_name: str,
        callback: Callable[[Any], None],
    ) -> Callable[[], None]:  # pragma: no cover - depends on system bus
        subscription_id = self._connection.signal_subscribe(
            bus_name,
            interface,
            signal_name,
            object_path,
            None,
            self._gio.DBusSignalFlags.NONE,
            lambda *_args: callback(
                _normalize_variant_result(_args[-1].unpack() if _args[-1] else None)
            ),
        )

        def unsubscribe() -> None:
            self._connection.signal_unsubscribe(subscription_id)

        return unsubscribe


class PythonDBusTransport:
    """dbus-python transport.

    The upstream OpenVPN 3 Python bindings are built on top of dbus-python, so
    this transport is preferred when available.
    """

    def __init__(self) -> None:
        try:
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop
        except ImportError as exc:  # pragma: no cover - system-dependent
            raise RuntimeError("dbus-python is required for D-Bus access.") from exc

        DBusGMainLoop(set_as_default=True)
        self._dbus = dbus
        self._bus = dbus.SystemBus()

    def call(
        self,
        *,
        bus_name: str,
        object_path: str,
        interface: str,
        method: str,
        params: Any | None = None,
        signature: str | None = None,
    ) -> Any:  # pragma: no cover - depends on system bus
        obj = self._bus.get_object(bus_name, object_path)
        dbus_interface = self._dbus.Interface(obj, dbus_interface=interface)
        method_fn = getattr(dbus_interface, method)
        if params is None:
            result = method_fn()
        elif isinstance(params, Sequence) and not isinstance(params, (str, bytes, bytearray)):
            result = method_fn(*tuple(params))
        else:
            result = method_fn(params)
        return _normalize_dbus_value(result)

    def subscribe(
        self,
        *,
        bus_name: str,
        object_path: str,
        interface: str,
        signal_name: str,
        callback: Callable[[Any], None],
    ) -> Callable[[], None]:  # pragma: no cover - depends on system bus
        def wrapped(*args: Any) -> None:
            if len(args) == 1:
                callback(_normalize_dbus_value(args[0]))
            else:
                callback(_normalize_dbus_value(args))

        self._bus.add_signal_receiver(
            wrapped,
            signal_name=signal_name,
            dbus_interface=interface,
            bus_name=bus_name,
            path=object_path,
        )

        def unsubscribe() -> None:
            self._bus.remove_signal_receiver(
                wrapped,
                signal_name=signal_name,
                dbus_interface=interface,
                bus_name=bus_name,
                path=object_path,
            )

        return unsubscribe


def opaque_identifier(prefix: str, object_path: str) -> str:
    digest = hashlib.sha1(object_path.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def create_default_transport() -> DBusTransport:
    try:
        return PythonDBusTransport()
    except RuntimeError:
        return GioDBusTransport()


def _normalize_variant_result(value: Any) -> Any:
    if value == ():
        return None
    if isinstance(value, tuple) and len(value) == 1:
        return _normalize_variant_result(value[0])
    return value


def _normalize_dbus_value(value: Any) -> Any:
    type_name = type(value).__name__
    if type_name == "Array":
        return [_normalize_dbus_value(item) for item in value]
    if type_name == "Dictionary":
        return {str(key): _normalize_dbus_value(val) for key, val in value.items()}
    if type_name == "Struct":
        return tuple(_normalize_dbus_value(item) for item in value)
    if type_name in {
        "String",
        "ObjectPath",
        "Signature",
    }:
        return str(value)
    if type_name in {
        "Boolean",
    }:
        return bool(value)
    if type_name in {
        "UInt16",
        "UInt32",
        "UInt64",
        "Int16",
        "Int32",
        "Int64",
        "Byte",
    }:
        return int(value)
    return value


def _is_activation_race(exc: Exception) -> bool:
    message = str(exc)
    dbus_name_getter = getattr(exc, "get_dbus_name", None)
    dbus_name = dbus_name_getter() if callable(dbus_name_getter) else ""
    transient_names = {
        "org.freedesktop.DBus.Error.NameHasNoOwner",
        "org.freedesktop.DBus.Error.ServiceUnknown",
        "org.freedesktop.DBus.Error.UnknownMethod",
        "org.freedesktop.DBus.Error.UnknownObject",
        "org.freedesktop.DBus.Error.Spawn.ChildExited",
    }
    transient_fragments = (
        "Object does not exist at path",
        "did not receive a reply",
        "The name is not activatable",
    )
    return dbus_name in transient_names or any(
        fragment in message for fragment in transient_fragments
    )
