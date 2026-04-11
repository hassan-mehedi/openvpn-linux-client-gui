"""Disconnected profile details dialog."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import re
from urllib.parse import urlsplit

from app.dialogs.common import configure_dialog_chrome
from core.models import Profile, ProxyDefinition, SavedCredentialState


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


_PROFILE_SAVE_DEBOUNCE_MS = 500


def present_profile_details_dialog(
    parent,
    *,
    profile: Profile,
    proxies: tuple[ProxyDefinition, ...],
    credential_state: SavedCredentialState,
    secure_storage_available: bool,
    on_save: Callable[[str, str | None, bool], None],
    on_connect: Callable[[str, str | None, bool], None],
    on_reset: Callable[[], Profile],
    on_delete: Callable[[], None],
) -> None:
    if Gtk is None or GLib is None:
        raise RuntimeError("GTK4 is required to create the profile details dialog.") from _IMPORT_ERROR

    dialog = Gtk.Dialog(title="Imported Profile", transient_for=parent, modal=True)
    dialog.set_default_size(460, 560)
    dialog.set_resizable(False)

    area = configure_dialog_chrome(dialog, title="Imported Profile")
    shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    shell.set_margin_top(20)
    shell.set_margin_bottom(20)
    shell.set_margin_start(20)
    shell.set_margin_end(20)
    shell.set_vexpand(True)
    area.append(shell)

    title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    shell.append(title_row)

    title = Gtk.Label(label="Imported Profile")
    title.set_xalign(0)
    title.set_hexpand(True)
    title.add_css_class("dialog-title")
    title_row.append(title)

    action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    title_row.append(action_box)

    delete_button = Gtk.Button()
    _configure_icon_action_button(
        delete_button,
        icon_name="user-trash-symbolic",
        tooltip="Delete profile",
        css_class="dialog-action-delete",
    )
    action_box.append(delete_button)

    reset_button = Gtk.Button()
    _configure_icon_action_button(
        reset_button,
        icon_name="edit-clear-symbolic",
        tooltip="Reset local changes",
        css_class="dialog-action-secondary",
    )
    action_box.append(reset_button)

    accept_button = Gtk.Button()
    _configure_icon_action_button(
        accept_button,
        icon_name="network-vpn-symbolic",
        tooltip="Connect profile",
        css_class="dialog-action-connect",
    )
    action_box.append(accept_button)

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_vexpand(True)
    shell.append(scroller)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_hexpand(True)
    scroller.set_child(box)

    current_profile = profile
    details = _resolve_profile_details(current_profile)

    grid = Gtk.Grid(column_spacing=12, row_spacing=14)
    grid.add_css_class("import-review-grid")
    grid.set_hexpand(True)
    box.append(grid)

    profile_name_label = Gtk.Label(label="Profile Name")
    profile_name_label.set_xalign(0)
    profile_name_label.add_css_class("dialog-field-label")
    profile_name_entry = Gtk.Entry()
    profile_name_entry.set_text(details["profile_name"] or current_profile.name)
    profile_name_entry.add_css_class("dialog-entry")
    profile_name_entry.add_css_class("dialog-entry-plain")
    profile_name_entry.set_hexpand(True)
    profile_name_entry.set_halign(Gtk.Align.FILL)
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

    proxy_label = Gtk.Label(label="Assigned Proxy")
    proxy_label.set_xalign(0)
    proxy_label.add_css_class("dialog-field-label")
    proxy_combo = Gtk.ComboBoxText()
    proxy_combo.add_css_class("dialog-entry")
    proxy_combo.append("", "No proxy")
    for proxy in proxies:
        proxy_combo.append(proxy.id, _proxy_option_label(proxy))
    if current_profile.assigned_proxy_id and not any(
        item.id == current_profile.assigned_proxy_id for item in proxies
    ):
        proxy_combo.append(
            current_profile.assigned_proxy_id,
            f"Missing proxy ({current_profile.assigned_proxy_id})",
        )
    proxy_combo.set_active_id(current_profile.assigned_proxy_id or "")
    proxy_combo.set_hexpand(True)
    proxy_combo.set_halign(Gtk.Align.FILL)
    grid.attach(proxy_label, 0, 6, 1, 1)
    grid.attach(proxy_combo, 0, 7, 1, 1)

    proxy_hint = Gtk.Label(
        label=(
            "This assignment is stored per profile and reused by the desktop UI and companion CLI."
            if proxies
            else "No saved proxies are available yet. Create them from Settings."
        )
    )
    proxy_hint.set_xalign(0)
    proxy_hint.set_wrap(True)
    proxy_hint.add_css_class("dialog-note")
    box.append(proxy_hint)

    facts_title = Gtk.Label(label="Profile Facts")
    facts_title.set_xalign(0)
    facts_title.add_css_class("dialog-field-label")
    box.append(facts_title)

    facts_grid = Gtk.Grid(column_spacing=12, row_spacing=14)
    facts_grid.add_css_class("import-review-grid")
    facts_grid.set_hexpand(True)
    box.append(facts_grid)

    source_value = _attach_detail_row(facts_grid, "Source", "", 0)
    origin_value = _attach_detail_row(facts_grid, "Origin", "", 1)
    imported_value = _attach_detail_row(facts_grid, "Imported", "", 2)
    last_used_value = _attach_detail_row(facts_grid, "Last Used", "", 3)
    usage_value = _attach_detail_row(facts_grid, "Session Count", "", 4)
    backend_state_value = _attach_detail_row(facts_grid, "Backend State", "", 5)
    tags_value = _attach_detail_row(facts_grid, "Tags", "", 6)

    facts_hint = Gtk.Label(
        label=(
            "Name and proxy assignment are local app overrides. Backend facts remain read-only "
            "so the desktop UI does not rewrite imported profile content."
        )
    )
    facts_hint.set_xalign(0)
    facts_hint.set_wrap(True)
    facts_hint.add_css_class("dialog-note")
    box.append(facts_hint)

    save_password = Gtk.CheckButton(label="Save password")
    save_password.set_active(credential_state.password_saved)
    save_password.set_sensitive(secure_storage_available or credential_state.password_saved)
    save_password.add_css_class("dialog-check")
    box.append(save_password)

    save_password_hint = Gtk.Label(
        label=_password_hint_text(
            password_saved=credential_state.password_saved,
            save_password_requested=credential_state.password_saved,
            secure_storage_available=secure_storage_available,
        )
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
    last_saved_name = _normalize_profile_name(details["profile_name"] or current_profile.name)
    last_saved_proxy_id = _normalize_proxy_id(current_profile.assigned_proxy_id)
    last_saved_password_state = credential_state.password_saved

    def refresh_fact_rows() -> None:
        nonlocal details
        details = _resolve_profile_details(current_profile)
        source_value.set_label(_profile_source_label(current_profile))
        origin_value.set_label(_profile_origin_label(current_profile))
        imported_value.set_label(_format_profile_timestamp(current_profile.imported_at))
        last_used_value.set_label(_format_profile_timestamp(current_profile.last_used))
        usage_value.set_label(_profile_usage_label(current_profile))
        backend_state_value.set_label(_profile_backend_state(current_profile))
        tags_value.set_label(_profile_tags_label(current_profile))

    refresh_fact_rows()

    def save_profile_name_if_needed() -> bool:
        nonlocal current_profile, save_source_id, last_saved_name, last_saved_proxy_id, last_saved_password_state
        save_source_id = None
        profile_name = _normalize_profile_name(profile_name_entry.get_text())
        assigned_proxy_id = _normalize_proxy_id(proxy_combo.get_active_id())
        save_password_requested = save_password.get_active()
        if not profile_name:
            error_label.set_label("Profile name cannot be empty.")
            error_label.set_visible(True)
            return False
        if (
            profile_name == last_saved_name
            and assigned_proxy_id == last_saved_proxy_id
            and save_password_requested == last_saved_password_state
        ):
            return True
        previous_profile = current_profile
        try:
            on_save(profile_name, assigned_proxy_id, save_password_requested)
        except Exception as exc:
            error_label.set_label(str(exc))
            error_label.set_visible(True)
            return False
        current_profile = Profile(
            id=previous_profile.id,
            name=profile_name,
            source=previous_profile.source,
            imported_at=previous_profile.imported_at,
            parity=previous_profile.parity,
            last_used=previous_profile.last_used,
            assigned_proxy_id=assigned_proxy_id,
            metadata=previous_profile.metadata,
            capabilities=previous_profile.capabilities,
        )
        last_saved_name = profile_name
        last_saved_proxy_id = assigned_proxy_id
        last_saved_password_state = save_password_requested
        error_label.set_visible(False)
        refresh_fact_rows()
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
    proxy_combo.connect("changed", schedule_profile_save)

    def refresh_save_password_hint(*_args) -> None:
        save_password_hint.set_label(
            _password_hint_text(
                password_saved=credential_state.password_saved,
                save_password_requested=save_password.get_active(),
                secure_storage_available=secure_storage_available,
            )
        )
        schedule_profile_save()

    save_password.connect("toggled", refresh_save_password_hint)

    def clear_pending_save() -> None:
        nonlocal save_source_id
        if save_source_id is not None:
            GLib.source_remove(save_source_id)
        save_source_id = None

    def reset_dialog_state() -> None:
        nonlocal current_profile, last_saved_name, last_saved_proxy_id
        clear_pending_save()
        try:
            current_profile = on_reset()
        except Exception as exc:
            error_label.set_label(str(exc))
            error_label.set_visible(True)
            return
        details = _resolve_profile_details(current_profile)
        profile_name_entry.set_text(details["profile_name"] or current_profile.name)
        proxy_combo.set_active_id(current_profile.assigned_proxy_id or "")
        last_saved_name = _normalize_profile_name(profile_name_entry.get_text())
        last_saved_proxy_id = _normalize_proxy_id(current_profile.assigned_proxy_id)
        error_label.set_visible(False)
        refresh_fact_rows()

    def connect_profile(*_args) -> None:
        clear_pending_save()
        if not save_profile_name_if_needed():
            return

        profile_name = _normalize_profile_name(profile_name_entry.get_text())
        if not profile_name:
            return
        on_connect(
            profile_name,
            _normalize_proxy_id(proxy_combo.get_active_id()),
            save_password.get_active(),
        )
        dialog.destroy()

    def delete_profile_and_close(*_args) -> None:
        clear_pending_save()
        on_delete()
        dialog.destroy()

    def on_close_request(*_args) -> bool:
        clear_pending_save()
        return False

    delete_button.connect("clicked", delete_profile_and_close)
    reset_button.connect("clicked", reset_dialog_state)
    accept_button.connect("clicked", connect_profile)
    profile_name_entry.connect("activate", connect_profile)
    dialog.connect("close-request", on_close_request)
    dialog.present()


def _attach_detail_row(grid: Gtk.Grid, label: str, value: str, row: int):
    title = Gtk.Label(label=label)
    title.set_xalign(0)
    title.add_css_class("dialog-field-label")
    current_value = Gtk.Label(label=value)
    current_value.set_xalign(0)
    current_value.set_wrap(True)
    current_value.add_css_class("dialog-value")
    grid.attach(title, 0, row * 2, 1, 1)
    grid.attach(current_value, 0, row * 2 + 1, 1, 1)
    return current_value


def _configure_icon_action_button(button, *, icon_name: str, tooltip: str, css_class: str) -> None:
    button.add_css_class("dialog-action-button")
    button.add_css_class(css_class)
    button.set_tooltip_text(tooltip)
    button.set_label("")
    button.set_icon_name(icon_name)


def _normalize_profile_name(value: str) -> str:
    return value.strip()


def _normalize_proxy_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _proxy_option_label(proxy: ProxyDefinition) -> str:
    return f"{proxy.name} ({proxy.type.value.upper()} {proxy.host}:{proxy.port})"


def _password_hint_text(
    *,
    password_saved: bool,
    save_password_requested: bool,
    secure_storage_available: bool,
) -> str:
    if password_saved and save_password_requested:
        return "A password is already stored securely for this profile."
    if password_saved and not save_password_requested:
        return "Uncheck this to remove the saved password for this profile."
    if not secure_storage_available:
        return "Secure password storage is unavailable on this machine."
    if save_password_requested:
        return "If authentication is required, the password will be stored securely after a successful prompt."
    return "You can enable this now and save the password the next time authentication is required."


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


def _profile_source_label(profile: Profile) -> str:
    return profile.source.value.replace("-", " ").title()


def _profile_origin_label(profile: Profile) -> str:
    canonical_url = profile.metadata.get("canonical_url")
    if not canonical_url:
        return "Imported from local file or drag-and-drop."
    parsed = urlsplit(str(canonical_url))
    if not parsed.scheme or not parsed.netloc:
        return "Remote origin recorded but unavailable for display."
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path or '/'}"


def _format_profile_timestamp(value: datetime | None) -> str:
    if value is None:
        return "Not recorded"
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def _profile_usage_label(profile: Profile) -> str:
    return str(int(profile.metadata.get("used_count", 0) or 0))


def _profile_backend_state(profile: Profile) -> str:
    labels: list[str] = []
    labels.append("Valid" if profile.metadata.get("valid", False) else "Unvalidated")
    if profile.metadata.get("persistent", False):
        labels.append("Persistent")
    if profile.metadata.get("readonly", False):
        labels.append("Read-only")
    if profile.metadata.get("locked_down", False):
        labels.append("Locked down")
    return ", ".join(labels)


def _profile_tags_label(profile: Profile) -> str:
    tags = profile.metadata.get("tags", ())
    if not tags:
        return "None"
    return ", ".join(str(tag) for tag in tags)


def _parse_name_for_details(name: str) -> tuple[str | None, str | None]:
    match = re.search(r"(?P<username>[^@\s]+)@(?P<host>[^\s\[]+)", name)
    if not match:
        return None, None
    return match.group("username"), match.group("host")
