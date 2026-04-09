"""Windows-like profile import dialog."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.dialogs.common import configure_dialog_chrome
from core.models import ImportPreview, ImportSource


try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("Gio", "2.0")

    from gi.repository import Gdk, Gio, Gtk
except (ImportError, ValueError) as exc:  # pragma: no cover - depends on system libs
    Gdk = None
    Gio = None
    Gtk = None
    _IMPORT_ERROR = exc
else:  # pragma: no cover - UI boot is not exercised in unit tests
    _IMPORT_ERROR = None


def present_import_profile_dialog(
    parent,
    *,
    on_preview_url: Callable[[str], ImportPreview],
    on_preview_file: Callable[[Path, ImportSource], ImportPreview],
    on_commit_url: Callable[[str, str, bool], None],
    on_commit_file: Callable[[Path, ImportSource, str, bool], None],
    initial_mode: str = "url",
) -> None:
    if Gtk is None or Gdk is None or Gio is None:
        raise RuntimeError("GTK4 with GDK/GIO is required to create the import dialog.") from _IMPORT_ERROR

    dialog = Gtk.Dialog(title="Import Profile", transient_for=parent, modal=True)
    dialog.set_default_size(440, 520)
    dialog.set_resizable(False)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Profiles", Gtk.ResponseType.REJECT)
    dialog.add_button("Next", Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.ACCEPT)

    cancel_button = dialog.get_widget_for_response(Gtk.ResponseType.CANCEL)
    profiles_button = dialog.get_widget_for_response(Gtk.ResponseType.REJECT)
    accept_button = dialog.get_widget_for_response(Gtk.ResponseType.ACCEPT)
    if cancel_button is not None:
        cancel_button.add_css_class("secondary-cta")
    if profiles_button is not None:
        profiles_button.add_css_class("secondary-cta")
    if accept_button is not None:
        accept_button.add_css_class("primary-cta")

    area = configure_dialog_chrome(dialog, title="Import Profile")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    box.set_margin_top(20)
    box.set_margin_bottom(20)
    box.set_margin_start(20)
    box.set_margin_end(20)
    area.append(box)

    title = Gtk.Label(label="Import Profile")
    title.set_xalign(0)
    title.add_css_class("dialog-title")
    box.append(title)

    outer_stack = Gtk.Stack()
    outer_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
    box.append(outer_stack)

    source_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    source_page.add_css_class("dialog-page")
    outer_stack.add_named(source_page, "source")

    switcher = Gtk.StackSwitcher()
    switcher.set_halign(Gtk.Align.FILL)
    switcher.add_css_class("import-switcher")
    source_page.append(switcher)

    source_stack = Gtk.Stack()
    source_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
    switcher.set_stack(source_stack)
    source_page.append(source_stack)

    url_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    url_page.add_css_class("dialog-page")
    source_stack.add_titled(url_page, "url", "URL")

    url_hint = Gtk.Label(
        label=(
            "Paste an HTTPS profile URL. Token URLs using "
            "`openvpn://import-profile/...` are supported too."
        )
    )
    url_hint.set_xalign(0)
    url_hint.set_wrap(True)
    url_hint.add_css_class("dialog-body")
    url_page.append(url_hint)

    url_entry = Gtk.Entry()
    url_entry.set_placeholder_text("https://vpn.example.com/profile.ovpn")
    url_entry.add_css_class("dialog-entry")
    url_page.append(url_entry)

    file_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    file_page.add_css_class("dialog-page")
    source_stack.add_titled(file_page, "file", "FILE")

    file_hint = Gtk.Label(
        label="Drag and drop a single .ovpn profile here, or browse for one."
    )
    file_hint.set_xalign(0)
    file_hint.set_wrap(True)
    file_hint.add_css_class("dialog-body")
    file_page.append(file_hint)

    drop_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    drop_card.add_css_class("file-drop-card")
    drop_card.set_halign(Gtk.Align.FILL)
    file_page.append(drop_card)

    file_icon = Gtk.Image.new_from_icon_name("document-open-symbolic")
    file_icon.set_pixel_size(52)
    file_icon.add_css_class("drop-card-icon")
    drop_card.append(file_icon)

    file_label = Gtk.Label(label=".OVPN")
    file_label.set_wrap(True)
    file_label.set_justify(Gtk.Justification.CENTER)
    file_label.add_css_class("drop-card-title")
    drop_card.append(file_label)

    file_subtitle = Gtk.Label(label="Drop profile to upload")
    file_subtitle.set_wrap(True)
    file_subtitle.set_justify(Gtk.Justification.CENTER)
    file_subtitle.add_css_class("drop-card-subtitle")
    drop_card.append(file_subtitle)

    browse_button = Gtk.Button(label="Browse")
    browse_button.add_css_class("secondary-cta")
    browse_button.set_halign(Gtk.Align.CENTER)
    drop_card.append(browse_button)

    review_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    review_page.add_css_class("dialog-page")
    outer_stack.add_named(review_page, "review")

    review_title = Gtk.Label(label="Imported Profile")
    review_title.set_xalign(0)
    review_title.add_css_class("dialog-section-title")
    review_page.append(review_title)

    review_hint = Gtk.Label(
        label="Confirm the detected profile details before importing."
    )
    review_hint.set_xalign(0)
    review_hint.set_wrap(True)
    review_hint.add_css_class("dialog-note")
    review_page.append(review_hint)

    review_grid = Gtk.Grid(column_spacing=12, row_spacing=14)
    review_grid.add_css_class("import-review-grid")
    review_page.append(review_grid)

    review_name_label = Gtk.Label(label="Profile Name")
    review_name_label.set_xalign(0)
    review_name_label.add_css_class("dialog-field-label")
    review_name_entry = Gtk.Entry()
    review_name_entry.add_css_class("dialog-entry")
    review_name_entry.add_css_class("dialog-entry-plain")
    review_name_entry.set_hexpand(True)
    review_name_entry.set_halign(Gtk.Align.FILL)
    review_grid.attach(review_name_label, 0, 0, 1, 1)
    review_grid.attach(review_name_entry, 0, 1, 1, 1)

    review_server_value = _attach_detail_row(review_grid, "Server Hostname (locked)", 1)
    review_username_value = _attach_detail_row(review_grid, "Username (locked)", 2)
    review_source_value = _attach_detail_row(review_grid, "Import Source", 3)

    save_password = Gtk.CheckButton(label="Save password")
    save_password.set_sensitive(False)
    save_password.add_css_class("dialog-check")
    review_page.append(save_password)

    save_password_hint = Gtk.Label(
        label="Secure password storage is not configured yet on this build."
    )
    save_password_hint.set_xalign(0)
    save_password_hint.set_wrap(True)
    save_password_hint.add_css_class("dialog-note")
    review_page.append(save_password_hint)

    duplicate_label = Gtk.Label()
    duplicate_label.set_xalign(0)
    duplicate_label.set_wrap(True)
    duplicate_label.add_css_class("dialog-note")
    duplicate_label.set_visible(False)
    review_page.append(duplicate_label)

    warning_label = Gtk.Label()
    warning_label.set_xalign(0)
    warning_label.set_wrap(True)
    warning_label.add_css_class("dialog-warning")
    warning_label.set_visible(False)
    review_page.append(warning_label)

    error_label = Gtk.Label()
    error_label.set_xalign(0)
    error_label.set_wrap(True)
    error_label.add_css_class("dialog-error")
    error_label.set_visible(False)
    box.append(error_label)

    selected_file: dict[str, Path | None] = {"path": None}
    selected_file_source: dict[str, ImportSource] = {"value": ImportSource.FILE}
    current_preview: dict[str, ImportPreview | None] = {"value": None}

    def sync_actions() -> None:
        review_visible = outer_stack.get_visible_child_name() == "review"
        if profiles_button is not None:
            profiles_button.set_visible(review_visible)
        if cancel_button is not None:
            cancel_button.set_label("Back" if review_visible else "Cancel")
        if accept_button is not None:
            accept_button.set_label("Connect" if review_visible else "Next")
            if review_visible:
                accept_button.set_sensitive(bool(review_name_entry.get_text().strip()))
            elif source_stack.get_visible_child_name() == "file":
                accept_button.set_sensitive(selected_file["path"] is not None)
            else:
                accept_button.set_sensitive(bool(url_entry.get_text().strip()))

    def set_error(message: str | None) -> None:
        if message:
            error_label.set_label(message)
            error_label.set_visible(True)
        else:
            error_label.set_visible(False)

    def reset_review() -> None:
        current_preview["value"] = None
        duplicate_label.set_visible(False)
        warning_label.set_visible(False)
        save_password.set_active(False)
        review_name_entry.set_text("")
        review_server_value.set_label("")
        review_username_value.set_label("")
        review_source_value.set_label("")
        review_hint.set_label("Confirm the detected profile details before importing.")

    def fill_review(preview: ImportPreview) -> None:
        details = preview.details
        review_name_entry.set_text(
            details.profile_name if details is not None else preview.name
        )
        review_server_value.set_label(
            details.server_hostname if details and details.server_hostname else "Detected after import"
        )
        review_username_value.set_label(
            details.username if details and details.username else "Requested when connecting"
        )
        review_source_value.set_label(_source_label(preview))
        review_hint.set_label(_review_hint(preview))
        if preview.duplicate_profile_id and preview.duplicate_profile_name:
            duplicate_label.set_label(
                "Matching profile detected: "
                f"{preview.duplicate_profile_name} ({preview.duplicate_reason or 'Existing import'}). "
                "Import again only if you intentionally need a separate copy."
            )
            duplicate_label.set_visible(True)
        else:
            duplicate_label.set_visible(False)
        if preview.warnings:
            warning_label.set_label("\n".join(preview.warnings))
            warning_label.set_visible(True)
        else:
            warning_label.set_visible(False)
        sync_actions()

    def preview_current_selection() -> bool:
        set_error(None)
        sync_actions()
        try:
            if source_stack.get_visible_child_name() == "file":
                if selected_file["path"] is None:
                    raise ValueError("Select or drop a single .ovpn file first.")
                preview = on_preview_file(
                    selected_file["path"],
                    selected_file_source["value"],
                )
            else:
                url = url_entry.get_text().strip()
                if not url:
                    raise ValueError("Enter a profile URL first.")
                preview = on_preview_url(url)
        except Exception as exc:
            set_error(str(exc))
            return False

        current_preview["value"] = preview
        fill_review(preview)
        outer_stack.set_visible_child_name("review")
        sync_actions()
        return True

    def finish_import(connect_after: bool) -> None:
        set_error(None)
        profile_name = review_name_entry.get_text().strip()
        if not profile_name:
            set_error("Profile name cannot be empty.")
            return
        try:
            if source_stack.get_visible_child_name() == "file":
                assert selected_file["path"] is not None
                on_commit_file(
                    selected_file["path"],
                    selected_file_source["value"],
                    profile_name,
                    connect_after,
                )
            else:
                on_commit_url(url_entry.get_text().strip(), profile_name, connect_after)
        except Exception as exc:
            set_error(str(exc))
            return
        dialog.destroy()

    def choose_file(*_args) -> None:
        chooser = Gtk.FileChooserNative(
            title="Choose .ovpn profile",
            transient_for=parent,
            action=Gtk.FileChooserAction.OPEN,
            accept_label="Select",
            cancel_label="Cancel",
        )

        def on_response(_dialog: Gtk.FileChooserNative, response: int) -> None:
            if response == Gtk.ResponseType.ACCEPT:
                selected = chooser.get_file()
                if selected is not None and selected.get_path():
                    set_selected_file(
                        Path(selected.get_path()),
                        ImportSource.FILE,
                    )
            chooser.destroy()

        chooser.connect("response", on_response)
        chooser.show()

    def set_selected_file(path: Path, source: ImportSource) -> None:
        selected_file["path"] = path
        selected_file_source["value"] = source
        file_label.set_label(path.name)
        file_subtitle.set_label("Ready to review import")
        set_error(None)

    def on_drop(_target, value, _x, _y) -> bool:
        files = _coerce_dropped_files(value)
        if len(files) != 1:
            set_error("Only one .ovpn profile can be imported at a time.")
            return False
        file_item = files[0]
        if Gio is not None and not isinstance(file_item, Gio.File):
            set_error("Dropped item is not a file.")
            return False
        path = file_item.get_path()
        if not path:
            set_error("Dropped file is not available on the local filesystem.")
            return False
        set_selected_file(Path(path), ImportSource.DRAG_AND_DROP)
        return True

    def on_response(_dialog: Gtk.Dialog, response_id: int) -> None:
        review_visible = outer_stack.get_visible_child_name() == "review"
        if not review_visible:
            if response_id == Gtk.ResponseType.ACCEPT:
                preview_current_selection()
                return
            dialog.destroy()
            return

        if response_id == Gtk.ResponseType.CANCEL:
            outer_stack.set_visible_child_name("source")
            reset_review()
            sync_actions()
            return
        if response_id == Gtk.ResponseType.ACCEPT:
            finish_import(review_visible)
            return
        if response_id == Gtk.ResponseType.REJECT:
            finish_import(False)
            return
        dialog.destroy()

    browse_button.connect("clicked", choose_file)
    url_entry.connect("changed", lambda *_args: (set_error(None), sync_actions()))
    review_name_entry.connect("changed", lambda *_args: (set_error(None), sync_actions()))
    source_stack.connect("notify::visible-child-name", lambda *_args: sync_actions())

    drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
    drop_target.connect("drop", on_drop)
    drop_card.add_controller(drop_target)

    source_stack.set_visible_child_name(initial_mode if initial_mode in {"url", "file"} else "url")
    outer_stack.set_visible_child_name("source")
    dialog.connect("response", on_response)
    sync_actions()
    dialog.present()


def _attach_detail_row(grid: Gtk.Grid, label: str, row: int) -> Gtk.Label:
    title = Gtk.Label(label=label)
    title.set_xalign(0)
    title.add_css_class("dialog-field-label")
    value = Gtk.Label()
    value.set_xalign(0)
    value.set_wrap(True)
    value.add_css_class("dialog-value")
    grid.attach(title, 0, row * 2, 1, 1)
    grid.attach(value, 0, row * 2 + 1, 1, 1)
    return value


def _source_label(preview: ImportPreview) -> str:
    label = preview.source.value.replace("-", " ").title()
    if preview.redacted_location:
        return f"{label}: {preview.redacted_location}"
    return label


def _coerce_dropped_files(value: Any) -> list[Any]:
    if hasattr(value, "get_files"):
        value = value.get_files()
    if hasattr(value, "get_n_items") and hasattr(value, "get_item"):
        return [value.get_item(index) for index in range(value.get_n_items())]
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _review_hint(preview: ImportPreview) -> str:
    if preview.source is ImportSource.TOKEN_URL:
        return "Token onboarding was normalized into a standard HTTPS import for review."
    if preview.source is ImportSource.URL:
        return "Remote profile details are inferred from the URL until the file is imported."
    return "Local profile details were detected from the selected .ovpn file."
