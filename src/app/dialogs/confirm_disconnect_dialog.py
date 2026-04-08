"""Disconnect confirmation dialog."""

from __future__ import annotations

from collections.abc import Callable


try:
    import gi

    gi.require_version("Gtk", "4.0")

    from gi.repository import Gtk
except (ImportError, ValueError) as exc:  # pragma: no cover - depends on system libs
    Gtk = None
    _IMPORT_ERROR = exc
else:  # pragma: no cover - UI boot is not exercised in unit tests
    _IMPORT_ERROR = None


def present_disconnect_confirmation_dialog(
    parent,
    *,
    profile_name: str,
    on_confirm: Callable[[bool], None],
) -> None:
    if Gtk is None:
        raise RuntimeError("GTK4 is required to create the disconnect dialog.") from _IMPORT_ERROR

    dialog = Gtk.Dialog(title="Disconnect VPN", transient_for=parent, modal=True)
    dialog.set_default_size(380, 240)
    dialog.set_resizable(False)
    dialog.add_css_class("connect-dialog")
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Confirm", Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.ACCEPT)

    accept_button = dialog.get_widget_for_response(Gtk.ResponseType.ACCEPT)
    cancel_button = dialog.get_widget_for_response(Gtk.ResponseType.CANCEL)
    if accept_button is not None:
        accept_button.add_css_class("primary-cta")
    if cancel_button is not None:
        cancel_button.add_css_class("secondary-cta")

    area = dialog.get_content_area()
    area.add_css_class("dialog-shell")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    box.set_margin_top(20)
    box.set_margin_bottom(20)
    box.set_margin_start(20)
    box.set_margin_end(20)

    title = Gtk.Label(label="Disconnect VPN")
    title.set_xalign(0)
    title.add_css_class("dialog-title")

    body = Gtk.Label(
        label=f"You will be disconnected from:\n\n{profile_name}"
    )
    body.set_xalign(0)
    body.set_wrap(True)
    body.add_css_class("dialog-body")

    remember = Gtk.CheckButton(label="Don't show again")
    remember.add_css_class("dialog-check")

    box.append(title)
    box.append(body)
    box.append(remember)
    area.append(box)

    def on_response(_dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id == Gtk.ResponseType.ACCEPT:
            on_confirm(remember.get_active())
        dialog.destroy()

    dialog.connect("response", on_response)
    dialog.present()
