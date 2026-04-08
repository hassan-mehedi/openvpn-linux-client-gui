"""Disconnected profile details dialog."""

from __future__ import annotations

from collections.abc import Callable
import re

from core.models import Profile


try:
    import gi

    gi.require_version("Gtk", "4.0")

    from gi.repository import GLib, Gtk
except (ImportError, ValueError) as exc:  # pragma: no cover - depends on system libs
    GLib = None
    Gtk = None
    _IMPORT_ERROR = exc
else:  # pragma: no cover - UI boot is not exercised in unit tests
    _IMPORT_ERROR = None


DELETE_RESPONSE = 1001
_PROFILE_SAVE_DEBOUNCE_MS = 500


def present_profile_details_dialog(
    parent,
    *,
    profile: Profile,
    on_save: Callable[[str], None],
    on_connect: Callable[[str], None],
    on_delete: Callable[[], None],
) -> None:
    if Gtk is None or GLib is None:
        raise RuntimeError("GTK4 is required to create the profile details dialog.") from _IMPORT_ERROR

    dialog = Gtk.Dialog(title="Imported Profile", transient_for=parent, modal=True)
    dialog.set_default_size(420, 360)
    dialog.set_resizable(False)
    dialog.add_css_class("connect-dialog")
    dialog.add_button("", DELETE_RESPONSE)
    dialog.add_button("", Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.ACCEPT)

    delete_button = dialog.get_widget_for_response(DELETE_RESPONSE)
    accept_button = dialog.get_widget_for_response(Gtk.ResponseType.ACCEPT)
    if delete_button is not None:
        _configure_icon_action_button(
            delete_button,
            icon_name="user-trash-symbolic",
            tooltip="Delete profile",
            css_class="dialog-action-delete",
        )
    if accept_button is not None:
        _configure_icon_action_button(
            accept_button,
            icon_name="network-vpn-symbolic",
            tooltip="Connect profile",
            css_class="dialog-action-connect",
        )

    area = dialog.get_content_area()
    area.add_css_class("dialog-shell")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_margin_top(20)
    box.set_margin_bottom(20)
    box.set_margin_start(20)
    box.set_margin_end(20)
    area.append(box)

    title = Gtk.Label(label="Imported Profile")
    title.set_xalign(0)
    title.add_css_class("dialog-title")
    box.append(title)

    details = _resolve_profile_details(profile)

    grid = Gtk.Grid(column_spacing=12, row_spacing=14)
    grid.add_css_class("import-review-grid")
    box.append(grid)

    profile_name_label = Gtk.Label(label="Profile Name")
    profile_name_label.set_xalign(0)
    profile_name_label.add_css_class("dialog-field-label")
    profile_name_entry = Gtk.Entry()
    profile_name_entry.set_text(details["profile_name"] or profile.name)
    profile_name_entry.add_css_class("dialog-entry")
    profile_name_entry.add_css_class("dialog-entry-plain")
    grid.attach(profile_name_label, 0, 0, 1, 1)
    grid.attach(profile_name_entry, 0, 1, 1, 1)

    _attach_detail_row(
        grid,
        "Server Hostname (locked)",
        details["server_hostname"] or "Unavailable",
        1,
    )
    _attach_detail_row(
        grid,
        "Username (locked)",
        details["username"] or "Requested when connecting",
        2,
    )

    save_password = Gtk.CheckButton(label="Save password")
    save_password.set_sensitive(False)
    save_password.add_css_class("dialog-check")
    box.append(save_password)

    save_password_hint = Gtk.Label(
        label="Secure password storage is not configured yet on this build."
    )
    save_password_hint.set_xalign(0)
    save_password_hint.set_wrap(True)
    save_password_hint.add_css_class("dialog-note")
    box.append(save_password_hint)

    error_label = Gtk.Label()
    error_label.set_xalign(0)
    error_label.set_wrap(True)
    error_label.add_css_class("dialog-error")
    error_label.set_visible(False)
    box.append(error_label)

    save_source_id: int | None = None
    last_saved_name = _normalize_profile_name(details["profile_name"] or profile.name)

    def save_profile_name_if_needed() -> bool:
        nonlocal save_source_id, last_saved_name
        save_source_id = None
        profile_name = _normalize_profile_name(profile_name_entry.get_text())
        if not profile_name:
            error_label.set_label("Profile name cannot be empty.")
            error_label.set_visible(True)
            return False
        if profile_name == last_saved_name:
            return True
        try:
            on_save(profile_name)
        except Exception as exc:
            error_label.set_label(str(exc))
            error_label.set_visible(True)
            return False
        last_saved_name = profile_name
        error_label.set_visible(False)
        return True

    def schedule_profile_save(*_args) -> None:
        nonlocal save_source_id
        error_label.set_visible(False)
        if save_source_id is not None:
            GLib.source_remove(save_source_id)
        save_source_id = GLib.timeout_add(
            _PROFILE_SAVE_DEBOUNCE_MS,
            save_profile_name_if_needed,
        )

    profile_name_entry.connect("changed", schedule_profile_save)

    def on_response(_dialog: Gtk.Dialog, response_id: int) -> None:
        nonlocal save_source_id
        if response_id == DELETE_RESPONSE:
            if save_source_id is not None:
                GLib.source_remove(save_source_id)
                save_source_id = None
            on_delete()
            dialog.destroy()
            return

        if response_id != Gtk.ResponseType.ACCEPT:
            if save_source_id is not None:
                GLib.source_remove(save_source_id)
                save_source_id = None
            dialog.destroy()
            return

        if save_source_id is not None:
            GLib.source_remove(save_source_id)
            save_source_id = None
        if not save_profile_name_if_needed():
            return

        profile_name = _normalize_profile_name(profile_name_entry.get_text())
        if not profile_name:
            return
        on_connect(profile_name)
        dialog.destroy()

    dialog.connect("response", on_response)
    dialog.present()


def _attach_detail_row(grid: Gtk.Grid, label: str, value: str, row: int) -> None:
    title = Gtk.Label(label=label)
    title.set_xalign(0)
    title.add_css_class("dialog-field-label")
    current_value = Gtk.Label(label=value)
    current_value.set_xalign(0)
    current_value.set_wrap(True)
    current_value.add_css_class("dialog-value")
    grid.attach(title, 0, row * 2, 1, 1)
    grid.attach(current_value, 0, row * 2 + 1, 1, 1)


def _configure_icon_action_button(button, *, icon_name: str, tooltip: str, css_class: str) -> None:
    button.add_css_class("dialog-action-button")
    button.add_css_class(css_class)
    button.set_tooltip_text(tooltip)
    button.set_label("")
    button.set_icon_name(icon_name)


def _normalize_profile_name(value: str) -> str:
    return value.strip()


def _resolve_profile_details(profile: Profile) -> dict[str, str | None]:
    metadata = profile.metadata
    server_hostname = metadata.get("server_hostname")
    username = metadata.get("username")
    if isinstance(server_hostname, str) and isinstance(username, str):
        return {
            "profile_name": str(metadata.get("profile_name", profile.name)),
            "server_hostname": server_hostname,
            "username": username,
        }

    parsed_username, parsed_host = _parse_name_for_details(profile.name)
    return {
        "profile_name": str(metadata.get("profile_name", profile.name)),
        "server_hostname": str(server_hostname) if server_hostname else parsed_host,
        "username": str(username) if username else parsed_username,
    }


def _parse_name_for_details(name: str) -> tuple[str | None, str | None]:
    match = re.search(r"(?P<username>[^@\s]+)@(?P<host>[^\s\[]+)", name)
    if not match:
        return None, None
    return match.group("username"), match.group("host")
