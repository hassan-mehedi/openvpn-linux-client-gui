"""Proxy management dialogs."""

from __future__ import annotations

from collections.abc import Callable

from app.dialogs.common import configure_dialog_chrome
from core.models import ProxyCredentials, ProxyDefinition, ProxyType


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


def present_proxy_manager_dialog(
    parent,
    *,
    list_proxies: Callable[[], tuple[ProxyDefinition, ...]],
    load_credentials: Callable[[str], ProxyCredentials | None],
    save_proxy: Callable[[ProxyDefinition, ProxyCredentials | None, bool], ProxyDefinition],
    delete_proxy: Callable[[str], None],
    secure_storage_available: bool,
    on_changed: Callable[[], None],
) -> None:
    if Gtk is None or GLib is None:
        raise RuntimeError("GTK4 is required to manage proxies.") from _IMPORT_ERROR

    dialog = Gtk.Dialog(title="Saved Proxies", transient_for=parent, modal=True)
    dialog.set_default_size(520, 460)
    dialog.add_button("Close", Gtk.ResponseType.CLOSE)
    area = configure_dialog_chrome(dialog, title="Saved Proxies")

    shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    shell.set_margin_top(20)
    shell.set_margin_bottom(20)
    shell.set_margin_start(20)
    shell.set_margin_end(20)
    area.append(shell)

    title = Gtk.Label(label="Saved Proxies")
    title.set_xalign(0)
    title.add_css_class("dialog-title")
    shell.append(title)

    description = Gtk.Label(
        label=(
            "Create reusable HTTP or SOCKS5 proxies here. Profile assignment stays in the "
            "profile details flow so the UI keeps one proxy per profile."
        )
    )
    description.set_xalign(0)
    description.set_wrap(True)
    description.add_css_class("dialog-note")
    shell.append(description)

    storage_label = Gtk.Label()
    storage_label.set_xalign(0)
    storage_label.set_wrap(True)
    storage_label.add_css_class("dialog-note")
    shell.append(storage_label)

    list_box = Gtk.ListBox()
    list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
    list_box.add_css_class("boxed-list")
    shell.append(list_box)

    summary_label = Gtk.Label()
    summary_label.set_xalign(0)
    summary_label.set_wrap(True)
    summary_label.add_css_class("dialog-note")
    shell.append(summary_label)

    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    shell.append(actions)

    add_button = Gtk.Button(label="Add Proxy")
    add_button.add_css_class("primary-cta")
    actions.append(add_button)

    edit_button = Gtk.Button(label="Edit Selected")
    edit_button.add_css_class("secondary-cta")
    edit_button.set_sensitive(False)
    actions.append(edit_button)

    delete_button = Gtk.Button(label="Delete Selected")
    delete_button.add_css_class("secondary-cta")
    delete_button.set_sensitive(False)
    actions.append(delete_button)

    state = {"selected_proxy_id": None}

    def selected_proxy() -> ProxyDefinition | None:
        proxy_id = state["selected_proxy_id"]
        if proxy_id is None:
            return None
        for item in list_proxies():
            if item.id == proxy_id:
                return item
        return None

    def refresh_list(*, preserve_selection: bool = True) -> None:
        proxies = list_proxies()
        selected_proxy_id = state["selected_proxy_id"] if preserve_selection else None

        while True:
            child = list_box.get_first_child()
            if child is None:
                break
            list_box.remove(child)

        if secure_storage_available:
            storage_label.set_label(
                "Authentication is optional. When provided, credentials stay outside plain-text metadata."
            )
        else:
            storage_label.set_label(
                "Secure credential storage is unavailable right now. Authenticated proxies will fail to save until the secret store is configured."
            )

        selected_row = None
        for proxy in proxies:
            row = Gtk.ListBoxRow()
            row.proxy_id = proxy.id

            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            body.set_margin_top(10)
            body.set_margin_bottom(10)
            body.set_margin_start(12)
            body.set_margin_end(12)

            name = Gtk.Label(label=proxy.name)
            name.set_xalign(0)
            name.add_css_class("setting-title")
            body.append(name)

            details = Gtk.Label(label=_proxy_detail_text(proxy))
            details.set_xalign(0)
            details.set_wrap(True)
            details.add_css_class("setting-description")
            body.append(details)

            row.set_child(body)
            list_box.append(row)
            if proxy.id == selected_proxy_id:
                selected_row = row

        if selected_row is not None:
            list_box.select_row(selected_row)
        elif proxies:
            list_box.select_row(list_box.get_row_at_index(0))
        else:
            state["selected_proxy_id"] = None

        edit_button.set_sensitive(state["selected_proxy_id"] is not None)
        delete_button.set_sensitive(state["selected_proxy_id"] is not None)
        if proxies:
            summary_label.set_label(
                f"{len(proxies)} saved proxy definition(s). Select one to edit or delete it."
            )
        else:
            summary_label.set_label("No saved proxies yet.")

    def open_editor(proxy: ProxyDefinition | None) -> None:
        existing_credentials = None
        if proxy is not None and proxy.credential_ref:
            try:
                existing_credentials = load_credentials(proxy.id)
            except Exception:
                existing_credentials = None

        present_proxy_editor_dialog(
            dialog,
            proxy=proxy,
            existing_credentials=existing_credentials,
            secure_storage_available=secure_storage_available,
            on_save=lambda updated_proxy, credentials, clear_credentials: _save_proxy_and_refresh(
                updated_proxy,
                credentials,
                clear_credentials,
            ),
        )

    def _save_proxy_and_refresh(
        proxy: ProxyDefinition,
        credentials: ProxyCredentials | None,
        clear_credentials: bool,
    ) -> ProxyDefinition:
        saved = save_proxy(proxy, credentials, clear_credentials)
        state["selected_proxy_id"] = saved.id
        refresh_list()
        on_changed()
        return saved

    def on_row_selected(_list_box, row) -> None:
        state["selected_proxy_id"] = getattr(row, "proxy_id", None) if row is not None else None
        edit_button.set_sensitive(state["selected_proxy_id"] is not None)
        delete_button.set_sensitive(state["selected_proxy_id"] is not None)

    list_box.connect("row-selected", on_row_selected)
    add_button.connect("clicked", lambda *_args: open_editor(None))
    edit_button.connect("clicked", lambda *_args: open_editor(selected_proxy()))

    def on_delete(*_args) -> None:
        proxy = selected_proxy()
        if proxy is None:
            return
        delete_proxy(proxy.id)
        state["selected_proxy_id"] = None
        refresh_list(preserve_selection=False)
        on_changed()

    delete_button.connect("clicked", on_delete)
    dialog.connect("response", lambda current, _response: current.destroy())

    refresh_list()
    dialog.present()


def present_proxy_editor_dialog(
    parent,
    *,
    proxy: ProxyDefinition | None,
    existing_credentials: ProxyCredentials | None,
    secure_storage_available: bool,
    on_save: Callable[[ProxyDefinition, ProxyCredentials | None, bool], ProxyDefinition],
) -> None:
    if Gtk is None:
        raise RuntimeError("GTK4 is required to edit proxies.") from _IMPORT_ERROR

    dialog = Gtk.Dialog(
        title="Edit Proxy" if proxy is not None else "Add Proxy",
        transient_for=parent,
        modal=True,
    )
    dialog.set_default_size(420, 420)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Save", Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.ACCEPT)
    area = configure_dialog_chrome(
        dialog,
        title="Edit Proxy" if proxy is not None else "Add Proxy",
    )

    shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    shell.set_margin_top(20)
    shell.set_margin_bottom(20)
    shell.set_margin_start(20)
    shell.set_margin_end(20)
    area.append(shell)

    grid = Gtk.Grid(column_spacing=12, row_spacing=12)
    shell.append(grid)

    name_entry = Gtk.Entry()
    name_entry.set_text(proxy.name if proxy is not None else "")
    _attach_form_row(grid, "Name", name_entry, 0)

    type_combo = Gtk.ComboBoxText()
    for item, label in (
        (ProxyType.HTTP.value, "HTTP"),
        (ProxyType.SOCKS5.value, "SOCKS5"),
    ):
        type_combo.append(item, label)
    type_combo.set_active_id(proxy.type.value if proxy is not None else ProxyType.HTTP.value)
    type_combo.set_hexpand(True)
    type_combo.set_halign(Gtk.Align.FILL)
    _attach_form_row(grid, "Type", type_combo, 1)

    host_entry = Gtk.Entry()
    host_entry.set_text(proxy.host if proxy is not None else "")
    _attach_form_row(grid, "Host", host_entry, 2)

    port_spin = Gtk.SpinButton.new_with_range(1, 65535, 1)
    port_spin.set_numeric(True)
    port_spin.set_value(float(proxy.port if proxy is not None else 8080))
    _attach_form_row(grid, "Port", port_spin, 3)

    enabled_switch = Gtk.Switch()
    enabled_switch.set_active(proxy.enabled if proxy is not None else True)
    _attach_form_row(grid, "Enabled", enabled_switch, 4)

    auth_switch = Gtk.Switch()
    has_saved_credentials = bool(proxy is not None and proxy.credential_ref)
    auth_switch.set_active(existing_credentials is not None or has_saved_credentials)
    _attach_form_row(grid, "Authentication", auth_switch, 5)

    username_entry = Gtk.Entry()
    username_entry.set_text(existing_credentials.username if existing_credentials is not None else "")
    _attach_form_row(grid, "Username", username_entry, 6)

    password_entry = Gtk.PasswordEntry()
    password_entry.set_text(existing_credentials.password if existing_credentials is not None else "")
    _attach_form_row(grid, "Password", password_entry, 7)

    note_label = Gtk.Label()
    note_label.set_xalign(0)
    note_label.set_wrap(True)
    note_label.add_css_class("dialog-note")
    shell.append(note_label)

    error_label = Gtk.Label()
    error_label.set_xalign(0)
    error_label.set_wrap(True)
    error_label.add_css_class("dialog-error")
    error_label.set_visible(False)
    shell.append(error_label)

    def refresh_auth_ui(*_args) -> None:
        auth_enabled = auth_switch.get_active()
        username_entry.set_sensitive(auth_enabled)
        password_entry.set_sensitive(auth_enabled)
        if not auth_enabled:
            note_label.set_label("Authentication is disabled for this proxy.")
            return
        if not secure_storage_available:
            note_label.set_label(
                "Secure credential storage is unavailable. Saving username and password will fail until the secret store is configured."
            )
            return
        if has_saved_credentials:
            note_label.set_label(
                "Saved credentials will be kept unless you enter a new username and password or disable authentication."
            )
            return
        note_label.set_label(
            "Authentication is optional. Enter a username and password only if this proxy requires them."
        )

    refresh_auth_ui()
    auth_switch.connect("notify::active", refresh_auth_ui)

    def on_response(current: Gtk.Dialog, response_id: int) -> None:
        if response_id != Gtk.ResponseType.ACCEPT:
            current.destroy()
            return

        error_label.set_visible(False)

        credentials: ProxyCredentials | None = None
        clear_credentials = False
        auth_enabled = auth_switch.get_active()
        username = username_entry.get_text().strip()
        password = password_entry.get_text()
        if auth_enabled:
            if username or password:
                credentials = ProxyCredentials(username=username, password=password)
            elif not has_saved_credentials:
                error_label.set_label(
                    "Enter both username and password, or disable authentication."
                )
                error_label.set_visible(True)
                return
        elif has_saved_credentials:
            clear_credentials = True

        definition = ProxyDefinition(
            id=proxy.id if proxy is not None else "",
            name=name_entry.get_text(),
            type=ProxyType(type_combo.get_active_id() or ProxyType.HTTP.value),
            host=host_entry.get_text(),
            port=int(port_spin.get_value()),
            credential_ref=proxy.credential_ref if proxy is not None else None,
            enabled=enabled_switch.get_active(),
        )

        try:
            on_save(definition, credentials, clear_credentials)
        except Exception as exc:
            error_label.set_label(str(exc))
            error_label.set_visible(True)
            return
        current.destroy()

    dialog.connect("response", on_response)
    dialog.present()


def _attach_form_row(grid: Gtk.Grid, label: str, widget, row: int) -> None:
    title = Gtk.Label(label=label)
    title.set_xalign(0)
    title.add_css_class("dialog-field-label")
    grid.attach(title, 0, row, 1, 1)
    if isinstance(widget, Gtk.Switch):
        widget.add_css_class("setting-switch")
        widget.set_hexpand(False)
        widget.set_halign(Gtk.Align.START)
        widget.set_valign(Gtk.Align.CENTER)
    else:
        widget.add_css_class("setting-control")
        widget.set_hexpand(True)
        widget.set_halign(Gtk.Align.FILL)
    grid.attach(widget, 1, row, 1, 1)


def _proxy_detail_text(proxy: ProxyDefinition) -> str:
    auth_state = "Auth saved" if proxy.credential_ref else "No auth"
    enabled_state = "Enabled" if proxy.enabled else "Disabled"
    return f"{proxy.type.value.upper()}  •  {proxy.host}:{proxy.port}  •  {auth_state}  •  {enabled_state}"
