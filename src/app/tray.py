"""StatusNotifierItem tray integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
import types

try:
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
except ImportError:  # pragma: no cover - depends on system libs
    dbus = None
    DBusGMainLoop = None


STATUS_NOTIFIER_ITEM_IFACE = "org.freedesktop.StatusNotifierItem"
LEGACY_STATUS_NOTIFIER_ITEM_IFACE = "org.kde.StatusNotifierItem"
DBUSMENU_IFACE = "com.canonical.dbusmenu"
WATCHER_OBJECT_PATH = "/StatusNotifierWatcher"
ITEM_OBJECT_PATH = "/StatusNotifierItem"
MENU_OBJECT_PATH = "/StatusNotifierMenu"
WATCHER_CANDIDATES = (
    ("org.kde.StatusNotifierWatcher", "org.kde.StatusNotifierWatcher"),
    ("org.freedesktop.StatusNotifierWatcher", "org.freedesktop.StatusNotifierWatcher"),
)


def _dbus_method(interface_name: str, **kwargs):
    if dbus is None:
        return lambda fn: fn
    return dbus.service.method(interface_name, **kwargs)


def _dbus_signal(interface_name: str, **kwargs):
    if dbus is None:
        return lambda fn: fn
    return dbus.service.signal(interface_name, **kwargs)


def _clone_callable(name: str, fn):
    clone = types.FunctionType(
        fn.__code__,
        fn.__globals__,
        name=name,
        argdefs=fn.__defaults__,
        closure=fn.__closure__,
    )
    clone.__doc__ = fn.__doc__
    clone.__annotations__ = getattr(fn, "__annotations__", {}).copy()
    clone.__kwdefaults__ = getattr(fn, "__kwdefaults__", None)
    return clone


@dataclass(slots=True, frozen=True)
class TraySupport:
    available: bool
    message: str
    watcher_service: str | None = None
    watcher_interface: str | None = None


class TrayIntegration:
    """Owns the optional StatusNotifierItem backend."""

    def __init__(
        self,
        *,
        app_id: str,
        title: str,
        icon_name: str,
        desktop_environment: str | None = None,
        detector: Callable[[str | None], TraySupport] | None = None,
        backend_factory: Callable[..., object] | None = None,
    ) -> None:
        self._app_id = app_id
        self._title = title
        self._icon_name = icon_name
        self._desktop_environment = desktop_environment
        self._detector = detector or detect_tray_support
        self._backend_factory = backend_factory or StatusNotifierItemBackend
        self._backend: object | None = None

    def support(self) -> TraySupport:
        return self._detector(self._desktop_environment)

    def sync(
        self,
        *,
        enabled: bool,
        toggle_window_visibility: Callable[[], None],
        show_window: Callable[[], None],
        quit_application: Callable[[], None],
        is_window_visible: Callable[[], bool],
    ) -> TraySupport:
        support = self.support()
        if not enabled or not support.available:
            self.stop()
            return support
        if self._backend is None:
            backend = self._backend_factory(
                app_id=self._app_id,
                title=self._title,
                icon_name=self._icon_name,
                watcher_service=support.watcher_service or "",
                watcher_interface=support.watcher_interface or "",
                toggle_window_visibility=toggle_window_visibility,
                show_window=show_window,
                quit_application=quit_application,
                is_window_visible=is_window_visible,
            )
            backend.start()
            self._backend = backend
        return support

    def stop(self) -> None:
        if self._backend is None:
            return
        self._backend.stop()
        self._backend = None

    def is_active(self) -> bool:
        return self._backend is not None


def current_desktop_environment() -> str | None:
    values: list[str] = []
    for key in ("XDG_CURRENT_DESKTOP", "DESKTOP_SESSION", "GDMSESSION"):
        raw = os.environ.get(key, "").strip()
        if not raw:
            continue
        for part in raw.split(":"):
            normalized = part.strip()
            if normalized and normalized not in values:
                values.append(normalized)
    if not values:
        return None
    return " / ".join(values)


def detect_tray_support(desktop_environment: str | None = None) -> TraySupport:
    desktop = desktop_environment or current_desktop_environment()
    if dbus is None or DBusGMainLoop is None:
        return TraySupport(
            available=False,
            message="dbus-python is unavailable, so the tray icon cannot be registered.",
        )

    try:
        DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
    except Exception as exc:
        return TraySupport(
            available=False,
            message=f"The session D-Bus is unavailable, so the tray icon cannot be registered: {exc}",
        )

    for service_name, interface_name in WATCHER_CANDIDATES:
        try:
            if bus.name_has_owner(service_name):
                return TraySupport(
                    available=True,
                    message="A StatusNotifier tray host is available on this desktop.",
                    watcher_service=service_name,
                    watcher_interface=interface_name,
                )
        except Exception:
            continue

    desktop_name = (desktop or "").upper()
    if "GNOME" in desktop_name:
        return TraySupport(
            available=False,
            message=(
                "No StatusNotifier tray host was detected. On GNOME, install the "
                "AppIndicator and KStatusNotifierItem Support extension to enable "
                "a real tray icon. The app will fall back to background mode."
            ),
        )
    return TraySupport(
        available=False,
        message=(
            "No StatusNotifier tray host was detected on the current desktop. "
            "The app will fall back to background mode."
        ),
    )


class StatusNotifierItemBackend:
    """Minimal session-bus StatusNotifierItem and DBusMenu implementation."""

    def __init__(
        self,
        *,
        app_id: str,
        title: str,
        icon_name: str,
        watcher_service: str,
        watcher_interface: str,
        toggle_window_visibility: Callable[[], None],
        show_window: Callable[[], None],
        quit_application: Callable[[], None],
        is_window_visible: Callable[[], bool],
    ) -> None:
        self._app_id = app_id
        self._title = title
        self._icon_name = icon_name
        self._watcher_service = watcher_service
        self._watcher_interface = watcher_interface
        self._toggle_window_visibility = toggle_window_visibility
        self._show_window = show_window
        self._quit_application = quit_application
        self._is_window_visible = is_window_visible
        self._dbus = None
        self._service_module = None
        self._bus = None
        self._bus_name = None
        self._service_name = ""
        self._item = None
        self._menu = None

    def start(self) -> None:
        if dbus is None or DBusGMainLoop is None:
            raise RuntimeError("dbus-python is required for tray support.")
        DBusGMainLoop(set_as_default=True)
        self._dbus = dbus
        self._bus = dbus.SessionBus()
        self._service_name = f"org.freedesktop.StatusNotifierItem-{os.getpid()}-1"
        self._bus_name = dbus.service.BusName(self._service_name, bus=self._bus)
        self._menu = _DBusMenu(
            bus_name=self._bus_name,
            show_window=self._show_window,
            quit_application=self._quit_application,
        )
        self._item = _StatusNotifierItem(
            bus_name=self._bus_name,
            app_id=self._app_id,
            title=self._title,
            icon_name=self._icon_name,
            menu_path=MENU_OBJECT_PATH,
            toggle_window_visibility=self._toggle_window_visibility,
            is_window_visible=self._is_window_visible,
        )
        watcher_obj = self._bus.get_object(
            self._watcher_service,
            WATCHER_OBJECT_PATH,
        )
        watcher = dbus.Interface(watcher_obj, dbus_interface=self._watcher_interface)
        watcher.RegisterStatusNotifierItem(self._service_name)

    def stop(self) -> None:
        if self._item is not None:
            self._item.remove_from_connection()
            self._item = None
        if self._menu is not None:
            self._menu.remove_from_connection()
            self._menu = None
        if self._bus is not None and self._service_name:
            try:
                self._bus.release_name(self._service_name)
            except Exception:
                pass
        self._bus_name = None
        self._bus = None


class _StatusNotifierItem(dbus.service.Object if dbus is not None else object):
    def __init__(
        self,
        *,
        bus_name,
        app_id: str,
        title: str,
        icon_name: str,
        menu_path: str,
        toggle_window_visibility: Callable[[], None],
        is_window_visible: Callable[[], bool],
    ) -> None:
        self._app_id = app_id
        self._title = title
        self._icon_name = icon_name
        self._menu_path = menu_path
        self._toggle_window_visibility = toggle_window_visibility
        self._is_window_visible = is_window_visible
        if dbus is None:
            raise RuntimeError("dbus-python is required for tray support.")
        super().__init__(bus_name, ITEM_OBJECT_PATH)

    def remove_from_connection(self) -> None:
        super().remove_from_connection()

    def _context_menu_impl(self, _x: int, _y: int) -> None:
        return None

    ContextMenu = _dbus_method(
        STATUS_NOTIFIER_ITEM_IFACE,
        in_signature="ii",
        out_signature="",
    )(_clone_callable("ContextMenu", _context_menu_impl))
    KdeContextMenu = _dbus_method(
        LEGACY_STATUS_NOTIFIER_ITEM_IFACE,
        in_signature="ii",
        out_signature="",
    )(_clone_callable("ContextMenu", _context_menu_impl))

    def _activate_impl(self, _x: int, _y: int) -> None:
        self._toggle_window_visibility()
        self.NewToolTip()
        self.KdeNewToolTip()

    Activate = _dbus_method(
        STATUS_NOTIFIER_ITEM_IFACE,
        in_signature="ii",
        out_signature="",
    )(_clone_callable("Activate", _activate_impl))
    KdeActivate = _dbus_method(
        LEGACY_STATUS_NOTIFIER_ITEM_IFACE,
        in_signature="ii",
        out_signature="",
    )(_clone_callable("Activate", _activate_impl))

    def _secondary_activate_impl(self, x: int, y: int) -> None:
        self._activate_impl(x, y)

    SecondaryActivate = _dbus_method(
        STATUS_NOTIFIER_ITEM_IFACE,
        in_signature="ii",
        out_signature="",
    )(_clone_callable("SecondaryActivate", _secondary_activate_impl))
    KdeSecondaryActivate = _dbus_method(
        LEGACY_STATUS_NOTIFIER_ITEM_IFACE,
        in_signature="ii",
        out_signature="",
    )(_clone_callable("SecondaryActivate", _secondary_activate_impl))

    def _scroll_impl(self, _delta: int, _orientation: str) -> None:
        return None

    Scroll = _dbus_method(
        STATUS_NOTIFIER_ITEM_IFACE,
        in_signature="is",
        out_signature="",
    )(_clone_callable("Scroll", _scroll_impl))
    KdeScroll = _dbus_method(
        LEGACY_STATUS_NOTIFIER_ITEM_IFACE,
        in_signature="is",
        out_signature="",
    )(_clone_callable("Scroll", _scroll_impl))

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="ss", out_signature="v") if dbus is not None else (lambda fn: fn)
    def Get(self, interface_name: str, property_name: str):
        properties = self._properties_for(interface_name)
        if property_name not in properties:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.UnknownProperty",
                f"Unknown property: {property_name}",
            )
        return properties[property_name]

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="s", out_signature="a{sv}") if dbus is not None else (lambda fn: fn)
    def GetAll(self, interface_name: str):
        return self._properties_for(interface_name)

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="ssv", out_signature="") if dbus is not None else (lambda fn: fn)
    def Set(self, _interface_name: str, _property_name: str, _value) -> None:
        raise dbus.exceptions.DBusException(
            "org.freedesktop.DBus.Error.PropertyReadOnly",
            "Status notifier properties are read-only.",
        )

    def _properties_for(self, interface_name: str):
        if interface_name not in {
            STATUS_NOTIFIER_ITEM_IFACE,
            LEGACY_STATUS_NOTIFIER_ITEM_IFACE,
        }:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.UnknownInterface",
                f"Unknown interface: {interface_name}",
            )
        return {
            "Category": dbus.String("ApplicationStatus"),
            "Id": dbus.String(self._app_id),
            "Title": dbus.String(self._title),
            "Status": dbus.String("Active"),
            "WindowId": dbus.UInt32(0),
            "IconName": dbus.String(self._icon_name),
            "IconPixmap": dbus.Array([], signature="(iiay)"),
            "OverlayIconName": dbus.String(""),
            "OverlayIconPixmap": dbus.Array([], signature="(iiay)"),
            "AttentionIconName": dbus.String(""),
            "AttentionIconPixmap": dbus.Array([], signature="(iiay)"),
            "AttentionMovieName": dbus.String(""),
            "ToolTip": dbus.Struct(
                (
                    dbus.String(self._icon_name),
                    dbus.Array([], signature="(iiay)"),
                    dbus.String(self._title),
                    dbus.String(
                        "Window is visible."
                        if self._is_window_visible()
                        else "Window is hidden in the system tray."
                    ),
                )
            ),
            "ItemIsMenu": dbus.Boolean(False),
            "Menu": dbus.ObjectPath(self._menu_path),
        }

    def _new_title_impl(self) -> None:
        return None

    NewTitle = _dbus_signal(
        STATUS_NOTIFIER_ITEM_IFACE,
        signature="",
    )(_clone_callable("NewTitle", _new_title_impl))
    KdeNewTitle = _dbus_signal(
        LEGACY_STATUS_NOTIFIER_ITEM_IFACE,
        signature="",
    )(_clone_callable("NewTitle", _new_title_impl))

    def _new_icon_impl(self) -> None:
        return None

    NewIcon = _dbus_signal(
        STATUS_NOTIFIER_ITEM_IFACE,
        signature="",
    )(_clone_callable("NewIcon", _new_icon_impl))
    KdeNewIcon = _dbus_signal(
        LEGACY_STATUS_NOTIFIER_ITEM_IFACE,
        signature="",
    )(_clone_callable("NewIcon", _new_icon_impl))

    def _new_tooltip_impl(self) -> None:
        return None

    NewToolTip = _dbus_signal(
        STATUS_NOTIFIER_ITEM_IFACE,
        signature="",
    )(_clone_callable("NewToolTip", _new_tooltip_impl))
    KdeNewToolTip = _dbus_signal(
        LEGACY_STATUS_NOTIFIER_ITEM_IFACE,
        signature="",
    )(_clone_callable("NewToolTip", _new_tooltip_impl))

    def _new_status_impl(self, _status: str) -> None:
        return None

    NewStatus = _dbus_signal(
        STATUS_NOTIFIER_ITEM_IFACE,
        signature="s",
    )(_clone_callable("NewStatus", _new_status_impl))
    KdeNewStatus = _dbus_signal(
        LEGACY_STATUS_NOTIFIER_ITEM_IFACE,
        signature="s",
    )(_clone_callable("NewStatus", _new_status_impl))


class _DBusMenu(dbus.service.Object if dbus is not None else object):
    def __init__(
        self,
        *,
        bus_name,
        show_window: Callable[[], None],
        quit_application: Callable[[], None],
    ) -> None:
        self._show_window = show_window
        self._quit_application = quit_application
        self._revision = 1
        if dbus is None:
            raise RuntimeError("dbus-python is required for tray support.")
        super().__init__(bus_name, MENU_OBJECT_PATH)

    def remove_from_connection(self) -> None:
        super().remove_from_connection()

    def _properties_for_item(self, item_id: int):
        if item_id == 0:
            return {}
        if item_id == 1:
            return {
                "label": dbus.String("Show Window"),
                "enabled": dbus.Boolean(True),
                "visible": dbus.Boolean(True),
            }
        if item_id == 2:
            return {
                "label": dbus.String("Quit"),
                "enabled": dbus.Boolean(True),
                "visible": dbus.Boolean(True),
            }
        raise dbus.exceptions.DBusException(
            "com.canonical.dbusmenu.UnknownId",
            f"Unknown menu item: {item_id}",
        )

    def _children_for(self, item_id: int) -> list[int]:
        if item_id == 0:
            return [1, 2]
        return []

    def _child_array(self, children: list[object]):
        if dbus is None:
            return children
        return dbus.Array(children, signature="v")

    def _layout_node(self, item_id: int, depth: int, property_names: list[str]):
        if depth == 0:
            children = self._child_array([])
        else:
            next_depth = depth - 1 if depth > 0 else depth
            children = self._child_array(
                [
                    self._layout_node(child_id, next_depth, property_names)
                    for child_id in self._children_for(item_id)
                ]
            )
        return (
            dbus.Int32(item_id),
            self._filtered_properties(self._properties_for_item(item_id), property_names),
            children,
        )

    def _filtered_properties(self, properties: dict[str, object], property_names: list[str]):
        if dbus is None:
            return properties
        if not property_names:
            return dbus.Dictionary(properties, signature="sv")
        filtered = {
            key: value
            for key, value in properties.items()
            if key in property_names
        }
        return dbus.Dictionary(filtered, signature="sv")

    @dbus.service.method(DBUSMENU_IFACE, in_signature="iias", out_signature="u(ia{sv}av)") if dbus is not None else (lambda fn: fn)
    def GetLayout(
        self,
        parent_id: int,
        recursion_depth: int,
        property_names: list[str],
    ):
        return (
            dbus.UInt32(self._revision),
            self._layout_node(parent_id, recursion_depth, property_names),
        )

    @dbus.service.method(DBUSMENU_IFACE, in_signature="aias", out_signature="a(ia{sv})") if dbus is not None else (lambda fn: fn)
    def GetGroupProperties(self, ids: list[int], property_names: list[str]):
        target_ids = ids or [0, 1, 2]
        return [
            (
                dbus.Int32(item_id),
                self._filtered_properties(
                    self._properties_for_item(item_id),
                    property_names,
                ),
            )
            for item_id in target_ids
        ]

    @dbus.service.method(DBUSMENU_IFACE, in_signature="is", out_signature="v") if dbus is not None else (lambda fn: fn)
    def GetProperty(self, item_id: int, name: str):
        properties = self._properties_for_item(item_id)
        if name not in properties:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.UnknownProperty",
                f"Unknown menu property: {name}",
            )
        return properties[name]

    @dbus.service.method(DBUSMENU_IFACE, in_signature="isvu", out_signature="") if dbus is not None else (lambda fn: fn)
    def Event(self, item_id: int, event_id: str, _data, _timestamp: int) -> None:
        if event_id != "clicked":
            return
        if item_id == 1:
            self._show_window()
        elif item_id == 2:
            self._quit_application()

    @dbus.service.method(DBUSMENU_IFACE, in_signature="i", out_signature="b") if dbus is not None else (lambda fn: fn)
    def AboutToShow(self, _item_id: int) -> bool:
        return False

    def _menu_properties(self):
        return {
            "Version": dbus.UInt32(3),
            "Status": dbus.String("normal"),
        }

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="ss", out_signature="v") if dbus is not None else (lambda fn: fn)
    def Get(self, interface_name: str, property_name: str):
        if interface_name != DBUSMENU_IFACE:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.UnknownInterface",
                f"Unknown interface: {interface_name}",
            )
        properties = self._menu_properties()
        if property_name not in properties:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.UnknownProperty",
                f"Unknown property: {property_name}",
            )
        return properties[property_name]

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="s", out_signature="a{sv}") if dbus is not None else (lambda fn: fn)
    def GetAll(self, interface_name: str):
        if interface_name != DBUSMENU_IFACE:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.UnknownInterface",
                f"Unknown interface: {interface_name}",
            )
        return self._menu_properties()

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="ssv", out_signature="") if dbus is not None else (lambda fn: fn)
    def Set(self, _interface_name: str, _property_name: str, _value) -> None:
        raise dbus.exceptions.DBusException(
            "org.freedesktop.DBus.Error.PropertyReadOnly",
            "DBusMenu properties are read-only.",
        )
