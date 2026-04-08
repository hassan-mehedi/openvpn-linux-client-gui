"""Credential and challenge prompt dialog."""

from __future__ import annotations

from collections.abc import Callable

from core.models import AttentionFieldType, AttentionRequest


try:
    import gi

    gi.require_version("Gtk", "4.0")

    from gi.repository import Gtk
except (ImportError, ValueError) as exc:  # pragma: no cover - depends on system libs
    Gtk = None
    _IMPORT_ERROR = exc
else:  # pragma: no cover - UI boot is not exercised in unit tests
    _IMPORT_ERROR = None


def present_attention_dialog(
    parent,
    *,
    profile_name: str,
    requests: tuple[AttentionRequest, ...],
    allow_save_password: bool = False,
    save_password: bool = False,
    on_submit: Callable[[dict[str, str], bool], None],
) -> None:
    if Gtk is None:
        raise RuntimeError("GTK4 is required to create the attention dialog.") from _IMPORT_ERROR

    title_text = "Enter password" if len(requests) == 1 and requests[0].secret else "Authentication Required"
    dialog = Gtk.Dialog(title=title_text, transient_for=parent, modal=True)
    dialog.set_default_size(380, 260)
    dialog.add_css_class("connect-dialog")
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("OK", Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.ACCEPT)
    dialog.set_resizable(False)

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

    title_label = Gtk.Label(label=title_text)
    title_label.set_xalign(0)
    title_label.add_css_class("dialog-title")

    intro = Gtk.Label(
        label=(
            f"Profile: {profile_name}\n"
            "Provide the required credentials to continue the VPN session."
        )
    )
    intro.set_wrap(True)
    intro.set_xalign(0)
    intro.add_css_class("dialog-body")
    box.append(title_label)
    box.append(intro)

    fields = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    entries: dict[str, Gtk.Editable] = {}
    for request in requests:
        field_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        label = Gtk.Label(label=request.label)
        label.set_xalign(0)
        label.add_css_class("dialog-field-label")

        if request.field_type in {
            AttentionFieldType.SECRET,
            AttentionFieldType.OTP,
            AttentionFieldType.PASSPHRASE,
        }:
            entry = Gtk.PasswordEntry()
            if request.field_type is AttentionFieldType.OTP:
                entry.set_show_peek_icon(False)
        else:
            entry = Gtk.Entry()

        entry.set_hexpand(True)
        entry.add_css_class("dialog-entry")
        if request.field_type is AttentionFieldType.OTP:
            entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        if request.value:
            entry.set_text(request.value)
        field_box.append(label)
        field_box.append(entry)
        fields.append(field_box)
        entries[request.field_id] = entry

    box.append(fields)

    save_password_toggle = None
    if allow_save_password:
        save_password_toggle = Gtk.CheckButton(label="Save password securely")
        save_password_toggle.set_active(save_password)
        save_password_toggle.add_css_class("dialog-check")
        box.append(save_password_toggle)

    error_label = Gtk.Label()
    error_label.set_wrap(True)
    error_label.set_xalign(0)
    error_label.add_css_class("dialog-error")
    error_label.set_visible(False)
    box.append(error_label)

    area.append(box)

    def on_response(_dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id == Gtk.ResponseType.ACCEPT:
            values = {field_id: entry.get_text().strip() for field_id, entry in entries.items()}
            empty_labels = [
                request.label
                for request in requests
                if not values.get(request.field_id)
            ]
            if empty_labels:
                error_label.set_label(f"Required: {', '.join(empty_labels)}")
                error_label.set_visible(True)
                return
            on_submit(
                values,
                save_password_toggle.get_active() if save_password_toggle is not None else False,
            )
        dialog.destroy()

    dialog.connect("response", on_response)
    dialog.present()
