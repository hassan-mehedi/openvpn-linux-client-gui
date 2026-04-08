"""Profile deletion confirmation dialog."""

from __future__ import annotations

from collections.abc import Callable

from app.dialogs.common import configure_dialog_chrome

try:
    import gi

    gi.require_version("Gtk", "4.0")

    from gi.repository import Gtk
except (ImportError, ValueError) as exc:  # pragma: no cover - depends on system libs
    Gtk = None
    _IMPORT_ERROR = exc
else:  # pragma: no cover - UI boot is not exercised in unit tests
    _IMPORT_ERROR = None


def present_delete_confirmation_dialog(
    parent,
    *,
    profile_name: str,
    on_confirm: Callable[[], None],
) -> None:
    if Gtk is None:
        raise RuntimeError("GTK4 is required to create the delete dialog.") from _IMPORT_ERROR

    dialog = Gtk.Dialog(title="Delete profile", transient_for=parent, modal=True)
    dialog.set_default_size(400, 220)
    dialog.set_resizable(False)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Delete", Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.CANCEL)

    accept_button = dialog.get_widget_for_response(Gtk.ResponseType.ACCEPT)
    cancel_button = dialog.get_widget_for_response(Gtk.ResponseType.CANCEL)
    if accept_button is not None:
        accept_button.add_css_class("destructive-cta")
    if cancel_button is not None:
        cancel_button.add_css_class("secondary-cta")

    area = configure_dialog_chrome(dialog, title="Delete profile")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    box.set_margin_top(20)
    box.set_margin_bottom(20)
    box.set_margin_start(20)
    box.set_margin_end(20)

    title = Gtk.Label(label="Delete profile")
    title.set_xalign(0)
    title.add_css_class("dialog-title")

    body = Gtk.Label(
        label=(
            f"This will remove the imported profile from this device.\n\n"
            f"Profile: {profile_name}"
        )
    )
    body.set_xalign(0)
    body.set_wrap(True)
    body.add_css_class("dialog-body")

    box.append(title)
    box.append(body)
    area.append(box)

    def on_response(_dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id == Gtk.ResponseType.ACCEPT:
            on_confirm()
        dialog.destroy()

    dialog.connect("response", on_response)
    dialog.present()
