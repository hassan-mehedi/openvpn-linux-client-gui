"""Primary application window."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import os
from pathlib import Path
from time import monotonic

from app.dialogs import (
    present_attention_dialog,
    present_delete_confirmation_dialog,
    present_disconnect_confirmation_dialog,
    present_import_profile_dialog,
    present_profile_details_dialog,
    present_proxy_manager_dialog,
)
from app.theme import apply_theme_mode
from core.bootstrap import ServiceContainer
from core.models import (
    AppSettings,
    CapabilityState,
    DiagnosticCheck,
    DiagnosticStatus,
    ConnectionProtocol,
    ImportPreview,
    ImportSource,
    LaunchBehavior,
    Profile,
    ProxyCredentials,
    ProxyDefinition,
    SavedCredentialState,
    SecurityLevel,
    SessionPhase,
    SessionTelemetryPoint,
    SessionTelemetrySnapshot,
    ThemeMode,
)
from core.onboarding import OnboardingError
from core.secrets import saved_password_request_id
from core.session_manager import SessionSnapshot


try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")

    from gi.repository import Adw, GLib, Gtk
except (ImportError, ValueError) as exc:  # pragma: no cover - depends on system libs
    Adw = None
    GLib = None
    Gtk = None
    _IMPORT_ERROR = exc
else:  # pragma: no cover - UI boot is not exercised in unit tests
    _IMPORT_ERROR = None


_ACTION_DEBOUNCE_SECONDS = 0.75
_SETTINGS_SAVE_DEBOUNCE_MS = 250


def OpenVPNMainWindow(application, services: ServiceContainer):  # noqa: N802
    if Adw is None or Gtk is None or GLib is None:
        raise RuntimeError(
            "PyGObject with GTK4/libadwaita is required to build the main window."
        ) from _IMPORT_ERROR

    window = Adw.ApplicationWindow(application=application)
    window.set_title("OpenVPN Connect")
    window.set_default_size(560, 860)

    toast_overlay = Adw.ToastOverlay()
    toast_overlay.add_css_class("connect-shell")
    window.set_content(toast_overlay)

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    toast_overlay.set_child(root)

    top_bar = Gtk.CenterBox()
    top_bar.add_css_class("brand-strip")
    top_bar.set_size_request(-1, 78)

    title_handle = Gtk.WindowHandle()
    title_handle.set_child(top_bar)
    root.append(title_handle)

    refresh_button = Gtk.Button(icon_name="view-refresh-symbolic")
    refresh_button.add_css_class("nav-icon")
    refresh_button.set_tooltip_text("Refresh profiles and session status")
    top_bar.set_start_widget(refresh_button)

    title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    title_box.set_hexpand(True)
    title_box.set_valign(Gtk.Align.CENTER)

    app_title = Gtk.Label(label="OpenVPN Connect")
    app_title.add_css_class("brand-title")
    subtitle = Gtk.Label(label="Profiles")
    subtitle.add_css_class("brand-subtitle")
    title_box.append(app_title)
    title_box.append(subtitle)
    top_bar.set_center_widget(title_box)

    top_bar_spacer = Gtk.Box()
    top_bar_spacer.set_size_request(42, 42)
    top_bar.set_end_widget(top_bar_spacer)

    shell_switcher = Gtk.StackSwitcher()
    shell_switcher.set_halign(Gtk.Align.CENTER)
    shell_switcher.add_css_class("shell-switcher")
    shell_switcher.set_margin_top(14)
    shell_switcher.set_margin_bottom(8)
    root.append(shell_switcher)

    page_stack = Gtk.Stack()
    page_stack.set_hexpand(True)
    page_stack.set_vexpand(True)
    page_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
    shell_switcher.set_stack(page_stack)
    root.append(page_stack)

    overlay = Gtk.Overlay()
    overlay.set_hexpand(True)
    overlay.set_vexpand(True)
    page_stack.add_titled(overlay, "profiles", "Profiles")

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    overlay.set_child(scroller)

    clamp = Adw.Clamp()
    clamp.set_maximum_size(480)
    clamp.set_tightening_threshold(380)
    scroller.set_child(clamp)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    content.add_css_class("content-column")
    content.set_margin_top(18)
    content.set_margin_bottom(96)
    content.set_margin_start(18)
    content.set_margin_end(18)
    clamp.set_child(content)

    search_entry = Gtk.SearchEntry()
    search_entry.set_placeholder_text("Search profiles")
    search_entry.add_css_class("search-pill")
    content.append(search_entry)

    service_banner = Adw.Banner()
    service_banner.set_revealed(False)
    content.append(service_banner)

    status_label = Gtk.Label()
    status_label.set_xalign(0)
    status_label.add_css_class("section-status")
    content.append(status_label)

    summary_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    summary_card.add_css_class("surface-card")
    content.append(summary_card)

    summary_title = Gtk.Label()
    summary_title.set_xalign(0)
    summary_title.add_css_class("card-title")

    summary_detail = Gtk.Label()
    summary_detail.set_xalign(0)
    summary_detail.set_wrap(True)
    summary_detail.add_css_class("card-detail")

    summary_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    summary_primary = Gtk.Button()
    summary_primary.add_css_class("primary-cta")
    summary_secondary = Gtk.Button()
    summary_secondary.add_css_class("secondary-cta")
    summary_actions.append(summary_primary)
    summary_actions.append(summary_secondary)

    summary_card.append(summary_title)
    summary_card.append(summary_detail)
    summary_card.append(summary_actions)

    profiles_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    content.append(profiles_list)

    stats_heading = Gtk.Label(label="CONNECTION STATS")
    stats_heading.set_xalign(0)
    stats_heading.add_css_class("stats-heading")
    content.append(stats_heading)

    stats_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    stats_card.add_css_class("surface-card")
    content.append(stats_card)

    stats_overview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    stats_overview.add_css_class("stats-overview")
    stats_card.append(stats_overview)

    stats_badges = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    stats_overview.append(stats_badges)

    stats_state_badge = Gtk.Label()
    stats_state_badge.add_css_class("stats-badge")
    stats_badges.append(stats_state_badge)

    stats_session_badge = Gtk.Label()
    stats_session_badge.add_css_class("stats-badge")
    stats_badges.append(stats_session_badge)

    stats_overview_title = Gtk.Label()
    stats_overview_title.set_xalign(0)
    stats_overview_title.add_css_class("stats-overview-title")
    stats_overview.append(stats_overview_title)

    stats_overview_body = Gtk.Label()
    stats_overview_body.set_xalign(0)
    stats_overview_body.set_wrap(True)
    stats_overview_body.add_css_class("stats-overview-body")
    stats_overview.append(stats_overview_body)

    stats_grid = Gtk.Grid(column_spacing=24, row_spacing=12)
    stats_grid.set_hexpand(True)
    stats_grid.set_column_homogeneous(True)
    stats_card.append(stats_grid)

    stats_duration_value = _build_stat(stats_grid, "DURATION", 0, 0)
    stats_phase_value = _build_stat(stats_grid, "STATUS", 1, 0)
    stats_bytes_in_value = _build_stat(stats_grid, "BYTES IN", 2, 0)
    stats_updated_value = _build_stat(stats_grid, "LAST UPDATE", 0, 1)
    stats_session_value = _build_stat(stats_grid, "SESSION", 1, 1)
    stats_bytes_out_value = _build_stat(stats_grid, "BYTES OUT", 2, 1)
    stats_rx_rate_value = _build_stat(stats_grid, "RX RATE", 0, 2)
    stats_tx_rate_value = _build_stat(stats_grid, "TX RATE", 1, 2)
    stats_latency_value = _build_stat(stats_grid, "LATENCY", 2, 2)
    stats_packets_in_value = _build_stat(stats_grid, "PACKETS IN", 0, 3)
    stats_packets_out_value = _build_stat(stats_grid, "PACKETS OUT", 1, 3)
    stats_packet_age_value = _build_stat(stats_grid, "PACKET AGE", 2, 3)

    telemetry_graph_title = Gtk.Label(label="THROUGHPUT")
    telemetry_graph_title.set_xalign(0)
    telemetry_graph_title.add_css_class("stats-heading")
    stats_card.append(telemetry_graph_title)

    telemetry_graph = Gtk.DrawingArea()
    telemetry_graph.set_content_height(88)
    telemetry_graph.set_hexpand(True)
    telemetry_graph.add_css_class("surface-card")
    stats_card.append(telemetry_graph)

    telemetry_graph_detail = Gtk.Label()
    telemetry_graph_detail.set_xalign(0)
    telemetry_graph_detail.set_wrap(True)
    telemetry_graph_detail.add_css_class("section-caption")
    stats_card.append(telemetry_graph_detail)

    empty_page = Adw.StatusPage(
        title="No profiles imported",
        description=(
            "Import an .ovpn file, an HTTPS profile URL, or a token URL "
            "to start using the client."
        ),
    )
    empty_page.set_icon_name("network-vpn-symbolic")
    empty_page.add_css_class("surface-card")
    content.append(empty_page)

    fab_button = Gtk.MenuButton(icon_name="list-add-symbolic")
    fab_button.add_css_class("fab-button")
    fab_button.set_tooltip_text("Import profile")
    fab_button.set_halign(Gtk.Align.END)
    fab_button.set_valign(Gtk.Align.END)
    fab_button.set_margin_bottom(28)
    fab_button.set_margin_end(28)
    overlay.add_overlay(fab_button)

    settings_scroller = Gtk.ScrolledWindow()
    settings_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    page_stack.add_titled(settings_scroller, "settings", "Settings")

    settings_clamp = Adw.Clamp()
    settings_clamp.set_maximum_size(560)
    settings_clamp.set_tightening_threshold(420)
    settings_scroller.set_child(settings_clamp)

    settings_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    settings_content.add_css_class("content-column")
    settings_content.set_margin_top(18)
    settings_content.set_margin_bottom(32)
    settings_content.set_margin_start(18)
    settings_content.set_margin_end(18)
    settings_clamp.set_child(settings_content)

    connection_card, connection_body = _build_section_card(
        "Connection Defaults",
        "These values are stored in the app config and reused by the desktop UI and companion CLI.",
    )
    settings_content.append(connection_card)

    protocol_combo = Gtk.ComboBoxText()
    for option, label in (
        (ConnectionProtocol.AUTO.value, "Automatic"),
        (ConnectionProtocol.UDP.value, "UDP"),
        (ConnectionProtocol.TCP.value, "TCP"),
    ):
        protocol_combo.append(option, label)
    connection_body.append(
        _build_setting_row(
            "Protocol",
            "Preferred transport when a profile does not override it.",
            protocol_combo,
        )
    )

    timeout_spin = Gtk.SpinButton.new_with_range(5, 600, 5)
    timeout_spin.set_numeric(True)
    connection_body.append(
        _build_setting_row(
            "Connection timeout",
            "Seconds to allow active connect or reconnect progress before the app aborts the attempt.",
            timeout_spin,
        )
    )

    launch_combo = Gtk.ComboBoxText()
    for option, label in (
        (LaunchBehavior.NONE.value, "Do nothing"),
        (LaunchBehavior.START_APP.value, "Start app"),
        (LaunchBehavior.CONNECT_LATEST.value, "Connect latest"),
        (LaunchBehavior.RESTORE_CONNECTION.value, "Restore connection"),
    ):
        launch_combo.append(option, label)
    connection_body.append(
        _build_setting_row(
            "Launch behavior",
            "Linux-native equivalent of the Windows client startup options.",
            launch_combo,
        )
    )

    seamless_switch = Gtk.Switch()
    connection_body.append(
        _build_setting_row(
            "Seamless tunnel",
            "Keep the connection lifecycle stable while the app manages reconnects.",
            seamless_switch,
            control_align=Gtk.Align.END,
        )
    )

    presentation_card, presentation_body = _build_section_card(
        "Presentation",
        "Visual defaults and confirmation prompts exposed through the GUI shell.",
    )
    settings_content.append(presentation_card)

    theme_combo = Gtk.ComboBoxText()
    for option, label in (
        (ThemeMode.SYSTEM.value, "Follow system"),
        (ThemeMode.LIGHT.value, "Light"),
        (ThemeMode.DARK.value, "Dark"),
    ):
        theme_combo.append(option, label)
    presentation_body.append(
        _build_setting_row(
            "Theme",
            "Select whether the client follows the desktop appearance or forces a mode.",
            theme_combo,
        )
    )

    disconnect_switch = Gtk.Switch()
    presentation_body.append(
        _build_setting_row(
            "Disconnect confirmation",
            "Ask before disconnecting an active tunnel from the profiles page.",
            disconnect_switch,
            control_align=Gtk.Align.END,
        )
    )

    security_card, security_body = _build_section_card(
        "Security And Network",
        "Capability-gated switches stay visible even when the current machine cannot enable them.",
    )
    settings_content.append(security_card)

    settings_capability_label = Gtk.Label()
    settings_capability_label.set_xalign(0)
    settings_capability_label.set_wrap(True)
    settings_capability_label.add_css_class("section-caption")
    security_body.append(settings_capability_label)

    security_combo = Gtk.ComboBoxText()
    for option, label in (
        (SecurityLevel.STANDARD.value, "Standard"),
        (SecurityLevel.STRICT.value, "Strict"),
    ):
        security_combo.append(option, label)
    security_body.append(
        _build_setting_row(
            "Security level",
            "Strict mode hardens Linux backend behavior without hiding unsupported options.",
            security_combo,
        )
    )

    tls13_switch = Gtk.Switch()
    security_body.append(
        _build_setting_row(
            "Enforce TLS 1.3",
            "Reject connections that cannot negotiate TLS 1.3 when this is enabled.",
            tls13_switch,
            control_align=Gtk.Align.END,
        )
    )

    dco_switch = Gtk.Switch()
    security_body.append(
        _build_setting_row(
            "Data Channel Offload (DCO)",
            "Only available when the Linux kernel module is detected on this machine.",
            dco_switch,
            control_align=Gtk.Align.END,
        )
    )

    dco_hint = Gtk.Label()
    dco_hint.set_xalign(0)
    dco_hint.set_wrap(True)
    dco_hint.add_css_class("section-caption")
    security_body.append(dco_hint)

    block_ipv6_switch = Gtk.Switch()
    security_body.append(
        _build_setting_row(
            "Block IPv6",
            "Linux-adapted IPv6 policy that disables tunnel IPv6 capability when enabled.",
            block_ipv6_switch,
            control_align=Gtk.Align.END,
        )
    )

    google_dns_switch = Gtk.Switch()
    security_body.append(
        _build_setting_row(
            "Google DNS fallback",
            "Allow the client to fall back to public DNS when the primary configuration fails.",
            google_dns_switch,
            control_align=Gtk.Align.END,
        )
    )

    local_dns_switch = Gtk.Switch()
    security_body.append(
        _build_setting_row(
            "Local DNS",
            "Keep platform DNS defaults unless disabled, which asks the backend for global VPN DNS scope.",
            local_dns_switch,
            control_align=Gtk.Align.END,
        )
    )

    proxy_card, proxy_body = _build_section_card(
        "Proxies",
        "Manage saved proxies in one place, then assign a single proxy per profile from the profile details flow.",
    )
    settings_content.append(proxy_card)

    proxy_summary_label = Gtk.Label()
    proxy_summary_label.set_xalign(0)
    proxy_summary_label.set_wrap(True)
    proxy_summary_label.add_css_class("section-caption")
    proxy_body.append(proxy_summary_label)

    manage_proxies_button = Gtk.Button(label="Manage Proxies")
    manage_proxies_button.add_css_class("secondary-cta")
    proxy_body.append(manage_proxies_button)

    settings_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    settings_actions.set_halign(Gtk.Align.START)
    settings_content.append(settings_actions)

    reload_settings_button = Gtk.Button(label="Reload")
    reload_settings_button.add_css_class("secondary-cta")
    settings_actions.append(reload_settings_button)

    diagnostics_scroller = Gtk.ScrolledWindow()
    diagnostics_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    page_stack.add_titled(diagnostics_scroller, "diagnostics", "Diagnostics")

    diagnostics_clamp = Adw.Clamp()
    diagnostics_clamp.set_maximum_size(620)
    diagnostics_clamp.set_tightening_threshold(480)
    diagnostics_scroller.set_child(diagnostics_clamp)

    diagnostics_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    diagnostics_content.add_css_class("content-column")
    diagnostics_content.set_margin_top(18)
    diagnostics_content.set_margin_bottom(32)
    diagnostics_content.set_margin_start(18)
    diagnostics_content.set_margin_end(18)
    diagnostics_clamp.set_child(diagnostics_content)

    diagnostics_updated_label = Gtk.Label()
    diagnostics_updated_label.set_xalign(0)
    diagnostics_updated_label.set_wrap(True)
    diagnostics_updated_label.add_css_class("section-caption")
    diagnostics_content.append(diagnostics_updated_label)

    diagnostics_summary_label = Gtk.Label()
    diagnostics_summary_label.set_xalign(0)
    diagnostics_summary_label.set_wrap(True)
    diagnostics_summary_label.add_css_class("card-detail")
    diagnostics_content.append(diagnostics_summary_label)

    service_card, service_body = _build_section_card(
        "Service Reachability",
        "The desktop app should surface backend availability instead of silently degrading.",
    )
    diagnostics_content.append(service_card)
    service_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    service_body.append(service_rows)

    capability_card, capability_body = _build_section_card(
        "Capabilities",
        "Capability-dependent features stay visible with explicit status and reasons.",
    )
    diagnostics_content.append(capability_card)
    capability_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    capability_body.append(capability_rows)

    environment_card, environment_body = _build_section_card(
        "Environment Checks",
        "Linux-specific prerequisites and runtime assumptions are surfaced here before they become connection failures.",
    )
    diagnostics_content.append(environment_card)
    environment_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    environment_body.append(environment_rows)

    troubleshooting_card, troubleshooting_body = _build_section_card(
        "Troubleshooting",
        "Recommendations are derived from live services, settings, and capability checks.",
    )
    diagnostics_content.append(troubleshooting_card)
    troubleshooting_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    troubleshooting_body.append(troubleshooting_rows)

    workflow_card, workflow_body = _build_section_card(
        "Guided Recovery",
        "Follow these workflows when diagnostics uncover environment or capability blockers.",
    )
    diagnostics_content.append(workflow_card)
    workflow_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    workflow_body.append(workflow_rows)

    logs_card, logs_body = _build_section_card(
        "Recent Logs",
        "Logs are redacted before they are shown here or written into a support bundle.",
    )
    diagnostics_content.append(logs_card)

    logs_scroller = Gtk.ScrolledWindow()
    logs_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    logs_scroller.set_min_content_height(220)
    logs_scroller.add_css_class("diagnostics-log-scroller")
    logs_body.append(logs_scroller)

    logs_view = Gtk.TextView()
    logs_view.set_editable(False)
    logs_view.set_cursor_visible(False)
    logs_view.set_monospace(True)
    logs_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    logs_view.add_css_class("diagnostics-log")
    logs_scroller.set_child(logs_view)

    export_card, export_body = _build_section_card(
        "Support Bundle",
        "Export a redacted JSON bundle into the XDG state directory for troubleshooting.",
    )
    diagnostics_content.append(export_card)

    export_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    export_actions.set_halign(Gtk.Align.START)
    export_body.append(export_actions)

    diagnostics_refresh_button = Gtk.Button(label="Refresh Diagnostics")
    diagnostics_refresh_button.add_css_class("secondary-cta")
    export_actions.append(diagnostics_refresh_button)

    export_bundle_button = Gtk.Button(label="Export Support Bundle")
    export_bundle_button.add_css_class("primary-cta")
    export_actions.append(export_bundle_button)

    export_path_label = Gtk.Label()
    export_path_label.set_xalign(0)
    export_path_label.set_wrap(True)
    export_path_label.add_css_class("section-caption")
    export_body.append(export_path_label)

    active_watch: Callable[[], None] | None = None
    watched_session_id: str | None = None
    diagnostics_log_watch: Callable[[], None] | None = None
    diagnostics_log_session_id: str | None = None
    recent_actions: dict[str, float] = {}
    diagnostics_cache: dict[str, object | None] = {"snapshot": None}
    telemetry_cache: dict[str, object | None] = {"snapshot": None}
    last_diagnostics_render_at = 0.0
    settings_save_source_id: int | None = None
    settings_rendering = False
    last_saved_settings_signature: tuple[tuple[str, object], ...] | None = None
    last_announced_session_error: str | None = None

    def show_toast(message: str) -> None:
        toast_overlay.add_toast(Adw.Toast.new(message))

    def announce_session_error(snapshot: SessionSnapshot) -> None:
        nonlocal last_announced_session_error
        if snapshot.state is not SessionPhase.ERROR or not snapshot.last_error:
            last_announced_session_error = None
            return
        if snapshot.last_error == last_announced_session_error:
            return
        last_announced_session_error = snapshot.last_error
        show_toast(snapshot.last_error)

    def run_debounced_action(
        action_name: str,
        callback: Callable[[], object | None],
        *,
        widgets: tuple[object, ...] = (),
    ) -> object | None:
        now = monotonic()
        if not _should_run_debounced_action(
            recent_actions,
            action_name,
            now,
            cooldown_seconds=_ACTION_DEBOUNCE_SECONDS,
        ):
            return None

        recent_actions[action_name] = now
        _set_widgets_sensitive(widgets, False)

        def release_widgets() -> bool:
            _set_widgets_sensitive(widgets, True)
            return False

        GLib.timeout_add(
            int(_ACTION_DEBOUNCE_SECONDS * 1000),
            release_widgets,
        )
        return callback()

    def profile_name_for(profile_id: str | None) -> str:
        if not profile_id:
            return "OpenVPN Profile"
        for profile in services.profile_catalog.list_profiles().profiles:
            if profile.id == profile_id:
                return profile.name
        return profile_id

    def proxy_name_for(proxy_id: str | None) -> str | None:
        if not proxy_id:
            return None
        proxy = services.proxies.get_proxy(proxy_id)
        if proxy is None:
            return f"Missing proxy ({proxy_id})"
        return proxy.name

    def clear_session_watch() -> None:
        nonlocal active_watch, watched_session_id
        if active_watch is not None:
            active_watch()
            active_watch = None
        if watched_session_id is not None:
            services.telemetry.clear_session(watched_session_id)
        watched_session_id = None

    def clear_diagnostics_log_watch() -> None:
        nonlocal diagnostics_log_watch, diagnostics_log_session_id
        if diagnostics_log_watch is not None:
            diagnostics_log_watch()
            diagnostics_log_watch = None
        diagnostics_log_session_id = None

    def set_diagnostics_logs(lines: tuple[str, ...]) -> None:
        logs_text = "\n".join(lines) if lines else "No recent logs available."
        logs_view.get_buffer().set_text(logs_text)

    def ensure_diagnostics_log_watch(session_id: str | None) -> None:
        nonlocal diagnostics_log_watch, diagnostics_log_session_id
        if session_id is None:
            clear_diagnostics_log_watch()
            return
        if (
            diagnostics_log_watch is not None
            and diagnostics_log_session_id == session_id
        ):
            return
        clear_diagnostics_log_watch()
        diagnostics_log_session_id = session_id
        diagnostics_log_watch = services.diagnostics.subscribe_live_logs(
            session_id=session_id,
            callback=set_diagnostics_logs,
        )

    def visible_page_name() -> str:
        return page_stack.get_visible_child_name() or "profiles"

    def apply_window_theme(theme_mode: ThemeMode) -> None:
        apply_theme_mode(theme_mode)
        toast_overlay.remove_css_class("theme-dark")
        toast_overlay.remove_css_class("theme-light")
        if theme_mode is ThemeMode.DARK:
            toast_overlay.add_css_class("theme-dark")
        elif theme_mode is ThemeMode.LIGHT:
            toast_overlay.add_css_class("theme-light")

    def build_capability_index() -> dict[str, CapabilityState]:
        try:
            snapshot = services.diagnostics.build_snapshot(
                profiles=services.profile_catalog.list_profiles().profiles,
                settings=services.settings.load(),
            )
        except Exception:
            return {}
        return {item.key: item for item in snapshot.capabilities}

    def render_settings() -> None:
        nonlocal settings_rendering, last_saved_settings_signature
        capability_index = build_capability_index()
        dco_capability = capability_index.get("dco")
        try:
            settings = services.settings.load()
        except Exception as exc:  # pragma: no cover - filesystem dependent
            show_toast(f"Could not load settings: {exc}")
            settings = AppSettings()

        settings_rendering = True
        try:
            apply_window_theme(settings.theme)
            protocol_combo.set_active_id(settings.protocol.value)
            timeout_spin.set_value(settings.connection_timeout)
            launch_combo.set_active_id(settings.launch_behavior.value)
            seamless_switch.set_active(settings.seamless_tunnel)
            theme_combo.set_active_id(settings.theme.value)
            disconnect_switch.set_active(settings.disconnect_confirmation)
            security_combo.set_active_id(settings.security_level.value)
            tls13_switch.set_active(settings.enforce_tls13)
            block_ipv6_switch.set_active(settings.block_ipv6)
            google_dns_switch.set_active(settings.google_dns_fallback)
            local_dns_switch.set_active(settings.local_dns)

            dco_enabled = bool(dco_capability and dco_capability.available and settings.dco)
            dco_switch.set_active(dco_enabled)
            dco_switch.set_sensitive(bool(dco_capability and dco_capability.available))
            if dco_capability is None:
                settings_capability_label.set_label(
                    "Live capability data is not available right now. The form still saves normal client preferences."
                )
                dco_hint.set_label(
                    "DCO gating could not be evaluated because capability detection is unavailable."
                )
            else:
                settings_capability_label.set_label(
                    "Capability-dependent settings stay visible so the GUI does not hide unsupported features."
                )
                dco_hint.set_label(_capability_detail(dco_capability))
            render_proxy_summary()
        finally:
            settings_rendering = False
        last_saved_settings_signature = _settings_signature(settings)

    def render_proxy_summary() -> None:
        try:
            proxies = services.proxies.list_proxies()
            profiles = services.profile_catalog.list_profiles().profiles
        except Exception as exc:  # pragma: no cover - filesystem dependent
            proxy_summary_label.set_label(f"Proxy settings are unavailable: {exc}")
            return

        assigned_count = sum(1 for profile in profiles if profile.assigned_proxy_id)
        storage_state = (
            "Secure credential storage is available."
            if services.proxies.secure_storage_available()
            else "Credential-backed proxies require a configured secure secret store."
        )
        if not proxies:
            proxy_summary_label.set_label(
                "No saved proxies yet. Create one here, then assign it from a profile details dialog. "
                + storage_state
            )
            return
        proxy_summary_label.set_label(
            f"{len(proxies)} proxy definition(s) saved. {assigned_count} profile(s) currently have a proxy assignment. "
            + storage_state
        )

    def collect_settings() -> AppSettings:
        capability_index = build_capability_index()
        dco_capability = capability_index.get("dco")
        dco_allowed = bool(dco_capability and dco_capability.available)
        return AppSettings(
            protocol=ConnectionProtocol(protocol_combo.get_active_id() or ConnectionProtocol.AUTO.value),
            connection_timeout=int(timeout_spin.get_value()),
            launch_behavior=LaunchBehavior(
                launch_combo.get_active_id() or LaunchBehavior.NONE.value
            ),
            seamless_tunnel=seamless_switch.get_active(),
            theme=ThemeMode(theme_combo.get_active_id() or ThemeMode.SYSTEM.value),
            security_level=SecurityLevel(
                security_combo.get_active_id() or SecurityLevel.STANDARD.value
            ),
            enforce_tls13=tls13_switch.get_active(),
            dco=dco_allowed and dco_switch.get_active(),
            block_ipv6=block_ipv6_switch.get_active(),
            google_dns_fallback=google_dns_switch.get_active(),
            local_dns=local_dns_switch.get_active(),
            disconnect_confirmation=disconnect_switch.get_active(),
        )

    def save_settings() -> bool:
        nonlocal settings_save_source_id, last_saved_settings_signature
        settings_save_source_id = None
        try:
            settings = collect_settings()
            settings_signature = _settings_signature(settings)
            if settings_signature == last_saved_settings_signature:
                return False
            services.settings.save(settings)
        except Exception as exc:  # pragma: no cover - filesystem dependent
            show_toast(f"Could not save settings: {exc}")
            return False
        try:
            services.autostart.sync(settings.launch_behavior)
        except Exception:
            pass
        last_saved_settings_signature = settings_signature
        apply_window_theme(settings.theme)
        show_toast("Settings updated.")
        return False

    def schedule_settings_save(*_args) -> None:
        nonlocal settings_save_source_id
        if settings_rendering:
            return
        if settings_save_source_id is not None:
            GLib.source_remove(settings_save_source_id)
        settings_save_source_id = GLib.timeout_add(
            _SETTINGS_SAVE_DEBOUNCE_MS,
            save_settings,
        )

    def render_diagnostics() -> None:
        nonlocal last_diagnostics_render_at
        active_session = services.session_lifecycle.snapshot().active_session
        active_session_id = active_session.id if active_session is not None else None
        try:
            snapshot = services.diagnostics.build_snapshot(
                profiles=services.profile_catalog.list_profiles().profiles,
                settings=services.settings.load(),
                session_id=active_session_id,
            )
        except Exception as exc:  # pragma: no cover - runtime D-Bus dependent
            diagnostics_updated_label.set_label("Diagnostics unavailable")
            diagnostics_summary_label.set_label(str(exc))
            _clear_box(service_rows)
            _clear_box(capability_rows)
            _clear_box(environment_rows)
            _clear_box(troubleshooting_rows)
            _clear_box(workflow_rows)
            clear_diagnostics_log_watch()
            set_diagnostics_logs(())
            export_path_label.set_label("")
            diagnostics_cache["snapshot"] = None
            last_diagnostics_render_at = monotonic()
            return

        diagnostics_cache["snapshot"] = snapshot
        last_diagnostics_render_at = monotonic()
        diagnostics_updated_label.set_label(
            f"Updated {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )
        diagnostics_summary_label.set_label(
            _diagnostics_summary(snapshot)
        )

        _clear_box(service_rows)
        for name, reachable in sorted(snapshot.reachable_services.items()):
            service_rows.append(
                _build_diagnostic_row(
                    _short_service_name(name),
                    "Reachable" if reachable else "Unavailable",
                    None if reachable else "The D-Bus service could not be activated or reached.",
                )
            )

        _clear_box(capability_rows)
        if snapshot.capabilities:
            for capability in snapshot.capabilities:
                capability_rows.append(
                    _build_diagnostic_row(
                        _display_capability_name(capability.key),
                        "Available" if capability.available else "Unavailable",
                        _capability_detail(capability),
                    )
                )
        else:
            capability_rows.append(
                _build_diagnostic_row(
                    "Capabilities",
                    "No data",
                    "The adapter did not return any capability states.",
                )
            )

        _clear_box(environment_rows)
        for check in snapshot.environment_checks:
            environment_rows.append(
                _build_diagnostic_row(
                    check.label,
                    _diagnostic_status_label(check.status),
                    check.detail,
                )
            )

        _clear_box(troubleshooting_rows)
        for item in snapshot.troubleshooting_items:
            troubleshooting_rows.append(
                _build_diagnostic_row(
                    item.label,
                    _diagnostic_status_label(item.status),
                    item.detail,
                )
            )

        _clear_box(workflow_rows)
        for workflow in snapshot.guided_workflows:
            workflow_rows.append(
                _build_diagnostic_row(
                    workflow.label,
                    _diagnostic_status_label(workflow.status),
                    _diagnostic_workflow_detail(workflow),
                )
            )

        set_diagnostics_logs(snapshot.recent_logs)
        if visible_page_name() == "diagnostics":
            ensure_diagnostics_log_watch(active_session_id)

    def export_support_bundle() -> None:
        snapshot = diagnostics_cache.get("snapshot")
        if snapshot is None:
            render_diagnostics()
            snapshot = diagnostics_cache.get("snapshot")
        if snapshot is None:
            show_toast("Diagnostics are unavailable.")
            return

        target = _default_support_bundle_path()
        try:
            exported = services.diagnostics.export_support_bundle(target, snapshot)
        except Exception as exc:  # pragma: no cover - filesystem dependent
            show_toast(f"Export failed: {exc}")
            return
        export_path_label.set_label(str(exported))
        show_toast("Support bundle exported.")

    def sync_shell() -> None:
        page_name = visible_page_name()
        subtitle.set_label(_subtitle_for_page(page_name))
        fab_button.set_visible(page_name == "profiles")
        refresh_button.set_tooltip_text(_refresh_tooltip_for_page(page_name))
        if page_name == "settings":
            clear_diagnostics_log_watch()
            render_settings()
        elif page_name == "diagnostics":
            render_diagnostics()
        else:
            clear_diagnostics_log_watch()

    def refresh_service_banner() -> None:
        try:
            reachability = services.backend.reachable_services()
        except Exception as exc:  # pragma: no cover - depends on runtime D-Bus
            service_banner.set_title(f"OpenVPN 3 services unavailable: {exc}")
            service_banner.set_revealed(True)
            return

        unreachable = [name for name, ok in reachability.items() if not ok]
        if unreachable:
            service_banner.set_title(
                "Unavailable services: " + ", ".join(sorted(unreachable))
            )
            service_banner.set_revealed(True)
        else:
            service_banner.set_revealed(False)

    def ensure_session_watch() -> None:
        nonlocal active_watch, watched_session_id
        snapshot = services.session_lifecycle.snapshot()
        session_id = snapshot.active_session.id if snapshot.active_session is not None else None
        if session_id == watched_session_id:
            return

        clear_session_watch()
        if session_id is None:
            return

        def on_update(_snapshot: SessionSnapshot) -> None:
            GLib.idle_add(render_profiles, False)

        active_watch = services.session_lifecycle.watch_active_session(on_update)
        watched_session_id = session_id

    def sync_profile_password(
        profile_id: str,
        requests,
        values: dict[str, str],
        remaining_requests,
        *,
        save_password_requested: bool,
    ) -> None:
        field_id = saved_password_request_id(requests)
        if field_id is None:
            return
        if not save_password_requested:
            try:
                services.profile_secrets.clear_password(profile_id)
            except Exception as exc:  # pragma: no cover - secure storage dependent
                show_toast(f"Could not clear saved password: {exc}")
            return
        if any(request.field_id == field_id for request in remaining_requests):
            return
        password = values.get(field_id, "").strip()
        if not password:
            return
        try:
            services.profile_secrets.save_password(profile_id, password)
        except Exception as exc:  # pragma: no cover - secure storage dependent
            show_toast(f"Could not save password: {exc}")

    def prompt_attention(
        profile_id: str,
        profile_name: str,
        snapshot: SessionSnapshot,
        *,
        save_password_requested: bool = False,
    ) -> None:
        if not snapshot.attention_requests:
            return
        allow_save_password = (
            saved_password_request_id(snapshot.attention_requests) is not None
            and services.profile_secrets.secure_storage_available()
        )
        current_credential_state = services.profile_secrets.saved_state(profile_id)

        def on_submit(values: dict[str, str], save_password_choice: bool) -> None:
            try:
                updated = services.session_lifecycle.submit_attention_inputs(values)
            except Exception as exc:  # pragma: no cover - depends on runtime D-Bus
                show_toast(f"Input failed: {exc}")
                render_profiles(False)
                return
            sync_profile_password(
                profile_id,
                snapshot.attention_requests,
                values,
                updated.attention_requests,
                save_password_requested=save_password_choice,
            )

            ensure_session_watch()
            render_profiles(False)
            if updated.attention_requests:
                prompt_attention(
                    profile_id,
                    profile_name,
                    updated,
                    save_password_requested=save_password_choice,
                )
                return

            try:
                continued = services.session_lifecycle.connect()
            except Exception as exc:  # pragma: no cover - depends on runtime D-Bus
                show_toast(f"Connect failed: {exc}")
                render_profiles(False)
                return
            handle_connect_snapshot(
                profile_id,
                profile_name,
                continued,
                save_password_requested=save_password_choice,
            )

        present_attention_dialog(
            window,
            profile_name=profile_name,
            requests=snapshot.attention_requests,
            allow_save_password=allow_save_password,
            save_password=current_credential_state.password_saved or save_password_requested,
            on_submit=on_submit,
        )

    def handle_connect_snapshot(
        profile_id: str,
        profile_name: str,
        snapshot: SessionSnapshot,
        *,
        save_password_requested: bool = False,
    ) -> None:
        ensure_session_watch()
        render_profiles(False)
        if snapshot.attention_requests:
            prompt_attention(
                profile_id,
                profile_name,
                snapshot,
                save_password_requested=save_password_requested,
            )
            return
        if snapshot.state is SessionPhase.CONNECTED:
            show_toast(f"Connected to {profile_name}.")
        elif snapshot.state is SessionPhase.CONNECTING:
            show_toast(f"Connecting to {profile_name}.")
        elif snapshot.state is SessionPhase.RECONNECTING:
            show_toast(f"Reconnecting to {profile_name}.")
        else:
            announce_session_error(snapshot)

    def on_connect(
        profile_id: str,
        profile_name: str,
        *,
        save_password_requested: bool = False,
    ) -> None:
        try:
            snapshot = services.session_lifecycle.connect(profile_id)
        except Exception as exc:  # pragma: no cover - depends on runtime D-Bus
            show_toast(f"Connect failed: {exc}")
            return
        handle_connect_snapshot(
            profile_id,
            profile_name,
            snapshot,
            save_password_requested=save_password_requested,
        )

    def on_disconnect(*_args) -> None:
        snapshot = services.session_lifecycle.snapshot()
        if snapshot.active_session is None:
            return
        profile_name = profile_name_for(snapshot.active_session.profile_id)

        def perform_disconnect(disable_future_confirmation: bool) -> None:
            if disable_future_confirmation:
                try:
                    services.settings.update(disconnect_confirmation=False)
                except Exception as exc:  # pragma: no cover - filesystem dependent
                    show_toast(f"Could not save preference: {exc}")
            try:
                updated = services.session_lifecycle.disconnect()
            except Exception as exc:  # pragma: no cover - depends on runtime D-Bus
                show_toast(f"Disconnect failed: {exc}")
                return
            if updated.state is SessionPhase.IDLE:
                clear_session_watch()
                show_toast(f"Disconnected from {profile_name}.")
            render_profiles(False)

        try:
            requires_confirmation = services.settings.load().disconnect_confirmation
        except Exception:  # pragma: no cover - filesystem dependent
            requires_confirmation = True

        if requires_confirmation:
            present_disconnect_confirmation_dialog(
                window,
                profile_name=profile_name,
                on_confirm=perform_disconnect,
            )
            return
        perform_disconnect(False)

    def on_summary_primary(*_args) -> None:
        snapshot = services.session_lifecycle.snapshot()
        if snapshot.state is SessionPhase.ERROR:
            if snapshot.selected_profile_id is None:
                services.session_lifecycle.reset_error()
                render_profiles(False)
                return
            on_connect(
                snapshot.selected_profile_id,
                profile_name_for(snapshot.selected_profile_id),
            )
            return
        if snapshot.active_session is None:
            return
        profile_name = profile_name_for(snapshot.active_session.profile_id)
        if snapshot.state is SessionPhase.CONNECTED:
            try:
                services.session_lifecycle.pause()
            except Exception as exc:  # pragma: no cover - depends on runtime D-Bus
                show_toast(f"Pause failed: {exc}")
                return
            show_toast(f"Paused {profile_name}.")
            render_profiles(False)
            return
        if snapshot.state is SessionPhase.PAUSED:
            try:
                resumed = services.session_lifecycle.resume()
            except Exception as exc:  # pragma: no cover - depends on runtime D-Bus
                show_toast(f"Resume failed: {exc}")
                return
            handle_connect_snapshot(
                snapshot.active_session.profile_id,
                profile_name,
                resumed,
            )
            return
        if snapshot.attention_requests:
            prompt_attention(snapshot.active_session.profile_id, profile_name, snapshot)
            return
        if snapshot.state in {SessionPhase.READY, SessionPhase.SESSION_CREATED}:
            try:
                continued = services.session_lifecycle.connect()
            except Exception as exc:  # pragma: no cover - depends on runtime D-Bus
                show_toast(f"Connect failed: {exc}")
                return
            handle_connect_snapshot(snapshot.active_session.profile_id, profile_name, continued)
            return
        try:
            updated = services.session_lifecycle.refresh_status()
        except Exception as exc:  # pragma: no cover - depends on runtime D-Bus
            show_toast(f"Refresh failed: {exc}")
            return
        if updated.attention_requests:
            show_toast(f"{profile_name} needs additional input.")
        render_profiles(False)

    def on_summary_secondary(*_args) -> None:
        snapshot = services.session_lifecycle.snapshot()
        if snapshot.state is SessionPhase.ERROR:
            services.session_lifecycle.reset_error()
            render_profiles(False)
            return
        on_disconnect()

    def on_profile_toggle(profile_id: str, profile_name: str, new_state: bool) -> bool:
        snapshot = services.session_lifecycle.snapshot()
        active_for_profile = (
            snapshot.active_session is not None
            and snapshot.active_session.profile_id == profile_id
            and snapshot.state is not SessionPhase.IDLE
        )
        if active_for_profile and not new_state:
            on_disconnect()
        elif (not active_for_profile) and new_state:
            on_connect(profile_id, profile_name)
        return True

    def on_delete(profile_id: str, profile_name: str) -> None:
        def perform_delete() -> None:
            try:
                services.profile_catalog.delete_profile(profile_id)
            except Exception as exc:  # pragma: no cover - depends on runtime D-Bus
                show_toast(f"Delete failed: {exc}")
                return

            show_toast(f"Deleted profile {profile_name}.")
            render_profiles(False)

        present_delete_confirmation_dialog(
            window,
            profile_name=profile_name,
            on_confirm=perform_delete,
        )

    def on_open_profile_details(profile: Profile) -> None:
        current_profile = {"value": profile}

        try:
            available_proxies = services.proxies.list_proxies()
        except Exception as exc:
            show_toast(f"Could not load proxies: {exc}")
            available_proxies = ()
        try:
            credential_state = services.profile_secrets.saved_state(profile.id)
        except Exception as exc:
            show_toast(f"Could not load saved password state: {exc}")
            credential_state = SavedCredentialState(profile_id=profile.id, password_saved=False)

        def persist_profile(
            profile_name: str,
            assigned_proxy_id: str | None,
            save_password_requested: bool,
        ) -> None:
            active_profile = current_profile["value"]
            current_name = active_profile.name.strip()
            current_proxy_id = active_profile.assigned_proxy_id
            normalized = profile_name.strip()
            changed = False
            if normalized != current_name:
                services.profile_catalog.rename_profile(active_profile.id, normalized)
                show_toast(f"Saved profile name as {normalized}.")
                changed = True
            if assigned_proxy_id != current_proxy_id:
                services.profile_catalog.assign_proxy(active_profile.id, assigned_proxy_id)
                proxy_name = proxy_name_for(assigned_proxy_id) or "No proxy"
                show_toast(f"Updated proxy assignment to {proxy_name}.")
                changed = True
            if credential_state.password_saved and not save_password_requested:
                services.profile_secrets.clear_password(active_profile.id)
                credential_state.password_saved = False
                show_toast("Removed saved password.")
            elif (not credential_state.password_saved) and save_password_requested:
                show_toast("Password will be saved after the next successful authentication prompt.")
            updated_profile = services.profile_catalog.get_profile(active_profile.id)
            if updated_profile is not None:
                current_profile["value"] = updated_profile
            if changed:
                render_profiles(False)

        def save_profile(
            profile_name: str,
            assigned_proxy_id: str | None,
            save_password_requested: bool,
        ) -> None:
            persist_profile(profile_name, assigned_proxy_id, save_password_requested)

        def connect_profile(
            profile_name: str,
            assigned_proxy_id: str | None,
            save_password_requested: bool,
        ) -> None:
            persist_profile(profile_name, assigned_proxy_id, save_password_requested)
            on_connect(
                current_profile["value"].id,
                profile_name,
                save_password_requested=save_password_requested,
            )

        def reset_profile() -> Profile:
            services.profile_catalog.reset_profile_overrides(current_profile["value"].id)
            updated = services.profile_catalog.get_profile(current_profile["value"].id)
            if updated is None:
                raise RuntimeError("Profile is no longer available.")
            current_profile["value"] = updated
            show_toast("Reset local profile name and proxy assignment.")
            render_profiles(False)
            return updated

        def delete_profile() -> None:
            active_profile = current_profile["value"]
            on_delete(active_profile.id, active_profile.name)

        present_profile_details_dialog(
            window,
            profile=current_profile["value"],
            proxies=available_proxies,
            credential_state=credential_state,
            secure_storage_available=services.profile_secrets.secure_storage_available(),
            on_save=save_profile,
            on_connect=connect_profile,
            on_reset=reset_profile,
            on_delete=delete_profile,
        )

    def on_manage_proxies(*_args) -> None:
        def save_proxy_definition(
            proxy: ProxyDefinition,
            credentials: ProxyCredentials | None,
            clear_credentials: bool,
        ) -> ProxyDefinition:
            return services.proxies.save_proxy(
                proxy,
                credentials=credentials,
                clear_credentials=clear_credentials,
            )

        def delete_proxy_definition(proxy_id: str) -> None:
            services.proxies.delete_proxy(proxy_id)
            services.profile_catalog.clear_proxy_assignments(proxy_id)

        present_proxy_manager_dialog(
            window,
            list_proxies=services.proxies.list_proxies,
            load_credentials=services.proxies.load_proxy_credentials,
            save_proxy=save_proxy_definition,
            delete_proxy=delete_proxy_definition,
            secure_storage_available=services.proxies.secure_storage_available(),
            on_changed=lambda: (render_proxy_summary(), render_profiles(False)),
        )

    def update_summary(
        snapshot: SessionSnapshot,
        telemetry_snapshot: SessionTelemetrySnapshot | None,
    ) -> None:
        if not _should_show_summary(snapshot):
            summary_card.set_visible(False)
            stats_heading.set_visible(False)
            stats_card.set_visible(False)
            telemetry_cache["snapshot"] = None
            return

        summary_profile_id = (
            snapshot.active_session.profile_id
            if snapshot.active_session is not None
            else snapshot.selected_profile_id
        )
        profile_name = (
            profile_name_for(summary_profile_id)
            if summary_profile_id is not None
            else "OpenVPN Connection"
        )
        summary_card.set_visible(True)
        summary_title.set_label(_summary_title_for(snapshot, profile_name))
        summary_detail.set_label(_summary_detail_for(snapshot))

        primary_label, secondary_label = _summary_action_labels(snapshot)
        summary_primary.set_visible(primary_label is not None)
        if primary_label is not None:
            summary_primary.set_label(primary_label)
        summary_secondary.set_visible(secondary_label is not None)
        if secondary_label is not None:
            summary_secondary.set_label(secondary_label)
        summary_actions.set_visible(
            summary_primary.get_visible() or summary_secondary.get_visible()
        )

        show_stats = snapshot.state in {
            SessionPhase.CONNECTED,
            SessionPhase.CONNECTING,
            SessionPhase.RECONNECTING,
            SessionPhase.PAUSED,
        }
        stats_heading.set_visible(show_stats)
        stats_card.set_visible(show_stats)
        if show_stats:
            session_suffix = snapshot.active_session.id.split("-")[-1][:8]
            stats_state_badge.set_label(snapshot.state.value.replace("_", " ").upper())
            stats_session_badge.set_label(f"SESSION {session_suffix}")
            stats_overview_title.set_label(_stats_title_for(snapshot))
            stats_overview_body.set_label(_stats_body_for(snapshot))
            stats_duration_value.set_label(_format_duration(snapshot))
            stats_phase_value.set_label(snapshot.state.value.replace("_", " ").title())
            stats_bytes_in_value.set_label(_format_bytes(_telemetry_value(telemetry_snapshot, "bytes_in")))
            stats_updated_value.set_label(_format_last_update(snapshot))
            stats_session_value.set_label(session_suffix)
            stats_bytes_out_value.set_label(_format_bytes(_telemetry_value(telemetry_snapshot, "bytes_out")))
            stats_rx_rate_value.set_label(_format_rate(_telemetry_rate(telemetry_snapshot, "rx")))
            stats_tx_rate_value.set_label(_format_rate(_telemetry_rate(telemetry_snapshot, "tx")))
            stats_latency_value.set_label(_format_latency(_telemetry_value(telemetry_snapshot, "latency_ms")))
            stats_packets_in_value.set_label(_format_packets(_telemetry_value(telemetry_snapshot, "packets_in")))
            stats_packets_out_value.set_label(_format_packets(_telemetry_value(telemetry_snapshot, "packets_out")))
            stats_packet_age_value.set_label(_format_packet_age(telemetry_snapshot))
            telemetry_cache["snapshot"] = telemetry_snapshot
            telemetry_graph_detail.set_label(_telemetry_detail(telemetry_snapshot))
            telemetry_graph.queue_draw()

    def build_profile_card(
        profile,
        snapshot: SessionSnapshot,
        *,
        proxy_names: dict[str, str],
    ) -> Gtk.Widget:
        session_open_for_profile = (
            snapshot.active_session is not None
            and snapshot.active_session.profile_id == profile.id
            and snapshot.state is not SessionPhase.IDLE
        )
        paused_for_profile = session_open_for_profile and snapshot.state is SessionPhase.PAUSED
        active_for_profile = session_open_for_profile and not paused_for_profile

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("surface-card")
        card.add_css_class("profile-card")
        if active_for_profile:
            card.add_css_class("profile-card-active")
        elif paused_for_profile:
            card.add_css_class("profile-card-paused")
        _bind_card_interactions(card)

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        toggle = Gtk.Button()
        toggle.set_valign(Gtk.Align.START)
        toggle.set_size_request(54, 30)
        toggle.add_css_class("profile-toggle")
        if active_for_profile:
            toggle.set_tooltip_text(f"Disconnect {profile.name}")
        elif paused_for_profile:
            toggle.set_tooltip_text(f"Resume {profile.name}")
        else:
            toggle.set_tooltip_text(f"Connect {profile.name}")
        if active_for_profile:
            toggle.add_css_class("profile-toggle-active")
        elif paused_for_profile:
            toggle.add_css_class("profile-toggle-paused")
        else:
            toggle.add_css_class("profile-toggle-inactive")
        toggle.connect(
            "clicked",
            lambda *_args: run_debounced_action(
                f"profile-toggle:{profile.id}",
                lambda: on_profile_toggle(
                    profile.id,
                    profile.name,
                    not session_open_for_profile,
                ),
                widgets=(toggle,),
            ),
        )
        top_row.append(toggle)

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        labels.set_hexpand(True)

        eyebrow = Gtk.Label(
            label=(
                "ACTIVE PROFILE"
                if active_for_profile
                else "PAUSED PROFILE"
                if paused_for_profile
                else "OpenVPN Profile"
            )
        )
        eyebrow.set_xalign(0)
        eyebrow.add_css_class("profile-eyebrow")

        title_label = Gtk.Label(label=profile.name)
        title_label.set_xalign(0)
        title_label.set_wrap(True)
        title_label.add_css_class("profile-name")

        if active_for_profile:
            details = [
                snapshot.state.value.replace("_", " ").title(),
                snapshot.active_session.status_message or "Currently selected profile",
            ]
        else:
            details = _inactive_profile_details(
                profile,
                proxy_name=proxy_names.get(profile.assigned_proxy_id or ""),
            )
        meta_label = Gtk.Label(label="  •  ".join(details))
        meta_label.set_xalign(0)
        meta_label.set_wrap(True)
        meta_label.add_css_class("profile-meta")

        labels.append(eyebrow)
        labels.append(title_label)
        labels.append(meta_label)
        top_row.append(labels)

        if not active_for_profile:
            details_button = Gtk.Button(icon_name="document-edit-symbolic")
            details_button.add_css_class("icon-chip")
            details_button.set_tooltip_text(f"Profile details for {profile.name}")
            details_button.connect(
                "clicked",
                lambda *_args: run_debounced_action(
                    f"profile-details:{profile.id}",
                    lambda: on_open_profile_details(profile),
                    widgets=(details_button,),
                ),
            )
            top_row.append(details_button)

        card.append(top_row)

        return card

    def render_profiles(refresh_services: bool = True) -> bool:
        services.session_lifecycle.restore_existing_session()

        while True:
            child = profiles_list.get_first_child()
            if child is None:
                break
            profiles_list.remove(child)

        catalog_snapshot = services.profile_catalog.list_profiles(search_entry.get_text())
        session_snapshot = services.session_lifecycle.snapshot()
        telemetry_snapshot = None
        if session_snapshot.active_session is not None:
            try:
                telemetry_snapshot = services.telemetry.snapshot(session_snapshot.active_session)
            except Exception:
                telemetry_snapshot = None
        try:
            proxy_names = {
                proxy.id: proxy.name
                for proxy in services.proxies.list_proxies()
            }
        except Exception:
            proxy_names = {}

        status_text, status_tone = _status_presentation(session_snapshot)
        status_label.set_label(status_text)
        status_label.remove_css_class("status-connected")
        status_label.remove_css_class("status-paused")
        status_label.remove_css_class("status-disconnected")
        status_label.add_css_class(status_tone)

        announce_session_error(session_snapshot)
        update_summary(session_snapshot, telemetry_snapshot)

        if catalog_snapshot.profiles:
            empty_page.set_visible(False)
            ordered_profiles = sorted(
                catalog_snapshot.profiles,
                key=lambda profile: (
                    not (
                        session_snapshot.active_session is not None
                        and session_snapshot.active_session.profile_id == profile.id
                        and session_snapshot.state is not SessionPhase.IDLE
                    ),
                    profile.name.lower(),
                ),
            )
            for profile in ordered_profiles:
                profiles_list.append(
                    build_profile_card(
                        profile,
                        session_snapshot,
                        proxy_names=proxy_names,
                    )
                )
        else:
            empty_page.set_visible(True)

        if refresh_services:
            refresh_service_banner()
        ensure_session_watch()
        return False

    def periodic_refresh() -> bool:
        snapshot = services.session_lifecycle.snapshot()
        if snapshot.active_session is not None:
            try:
                services.session_lifecycle.refresh_status()
            except Exception:  # pragma: no cover - runtime D-Bus dependent
                pass
        render_profiles(False)
        if visible_page_name() == "diagnostics":
            if monotonic() - last_diagnostics_render_at >= 5:
                render_diagnostics()
        return True

    def preview_profile_from_path(
        path: Path,
        source: ImportSource = ImportSource.FILE,
    ) -> ImportPreview:
        return services.profile_catalog.preview_file_import(path, source=source)

    def import_profile_from_path(
        path: Path,
        source: ImportSource = ImportSource.FILE,
        profile_name: str = "",
        connect_after: bool = False,
    ) -> None:
        try:
            preview = preview_profile_from_path(path, source)
            profile = services.profile_catalog.import_file(
                path,
                source=source,
                profile_name=profile_name,
            )
        except (OnboardingError, OSError) as exc:
            raise RuntimeError(f"Import failed: {exc}") from exc
        except Exception as exc:  # pragma: no cover - depends on runtime D-Bus
            raise RuntimeError(f"Import failed: {exc}") from exc

        if preview.duplicate_profile_id:
            duplicate_name = preview.duplicate_profile_name or preview.duplicate_profile_id
            show_toast(f"Profile imported. Matching content already existed as {duplicate_name}.")
        else:
            show_toast(f"Imported {path.name}.")

        render_profiles(False)
        if connect_after:
            on_connect(profile.id, profile.name)

    def preview_profile_from_url(url: str) -> ImportPreview:
        if url.startswith("openvpn://import-profile/"):
            return services.profile_catalog.preview_token_url_import(url)
        return services.profile_catalog.preview_url_import(url)

    def import_from_url(url: str, profile_name: str = "", connect_after: bool = False) -> None:
        if not url:
            return
        try:
            preview = preview_profile_from_url(url)
            if url.startswith("openvpn://import-profile/"):
                profile = services.profile_catalog.import_token_url(
                    url,
                    profile_name=profile_name,
                )
            else:
                profile = services.profile_catalog.import_url(
                    url,
                    profile_name=profile_name,
                )
        except OnboardingError as exc:
            raise RuntimeError(f"Import failed: {exc}") from exc
        except Exception as exc:  # pragma: no cover - depends on runtime D-Bus
            raise RuntimeError(f"Import failed: {exc}") from exc

        if preview.duplicate_profile_id:
            duplicate_name = preview.duplicate_profile_name or preview.duplicate_profile_id
            show_toast(f"Profile imported. Matching URL already existed as {duplicate_name}.")
        else:
            show_toast(f"Imported {preview.redacted_location or preview.name}.")
        render_profiles(False)
        if connect_after:
            on_connect(profile.id, profile.name)

    def open_import_dialog(initial_mode: str) -> None:
        present_import_profile_dialog(
            window,
            on_preview_url=preview_profile_from_url,
            on_preview_file=preview_profile_from_path,
            on_commit_url=import_from_url,
            on_commit_file=import_profile_from_path,
            initial_mode=initial_mode,
        )

    def build_import_popover() -> Gtk.Popover:
        popover = Gtk.Popover()
        popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        popover_box.set_margin_top(12)
        popover_box.set_margin_bottom(12)
        popover_box.set_margin_start(12)
        popover_box.set_margin_end(12)

        file_button = Gtk.Button(label="Import File")
        file_button.add_css_class("secondary-cta")
        file_button.connect(
            "clicked",
            lambda *_args: (popover.popdown(), open_import_dialog("file")),
        )

        url_button = Gtk.Button(label="Import URL")
        url_button.add_css_class("primary-cta")
        url_button.connect(
            "clicked",
            lambda *_args: (
                popover.popdown(),
                open_import_dialog("url"),
            ),
        )

        popover_box.append(file_button)
        popover_box.append(url_button)
        popover.set_child(popover_box)
        return popover

    def on_refresh(*_args) -> None:
        page_name = visible_page_name()
        if page_name == "profiles":
            try:
                services.session_lifecycle.refresh_status()
            except Exception as exc:  # pragma: no cover - depends on runtime D-Bus
                show_toast(f"Refresh failed: {exc}")
                return
            render_profiles(True)
            show_toast("Profiles refreshed.")
            return
        if page_name == "settings":
            render_settings()
            show_toast("Settings reloaded.")
            return
        render_diagnostics()
        show_toast("Diagnostics refreshed.")

    refresh_button.connect(
        "clicked",
        lambda *_args: run_debounced_action(
            "refresh",
            lambda: on_refresh(),
            widgets=(refresh_button,),
        ),
    )
    fab_button.set_popover(build_import_popover())
    page_stack.connect("notify::visible-child-name", lambda *_args: sync_shell())
    search_entry.connect("search-changed", lambda *_args: render_profiles(False))
    summary_primary.connect(
        "clicked",
        lambda *_args: run_debounced_action(
            "summary-primary",
            lambda: on_summary_primary(),
            widgets=(summary_primary,),
        ),
    )
    summary_secondary.connect(
        "clicked",
        lambda *_args: run_debounced_action(
            "summary-secondary",
            lambda: on_summary_secondary(),
            widgets=(summary_secondary,),
        ),
    )
    reload_settings_button.connect(
        "clicked",
        lambda *_args: run_debounced_action(
            "settings-reload",
            lambda: render_settings(),
            widgets=(reload_settings_button,),
        ),
    )
    manage_proxies_button.connect(
        "clicked",
        lambda *_args: run_debounced_action(
            "proxies-manage",
            lambda: on_manage_proxies(),
            widgets=(manage_proxies_button,),
        ),
    )
    protocol_combo.connect("changed", schedule_settings_save)
    timeout_spin.connect("value-changed", schedule_settings_save)
    launch_combo.connect("changed", schedule_settings_save)
    seamless_switch.connect("notify::active", schedule_settings_save)
    theme_combo.connect("changed", schedule_settings_save)
    disconnect_switch.connect("notify::active", schedule_settings_save)
    security_combo.connect("changed", schedule_settings_save)
    tls13_switch.connect("notify::active", schedule_settings_save)
    dco_switch.connect("notify::active", schedule_settings_save)
    block_ipv6_switch.connect("notify::active", schedule_settings_save)
    google_dns_switch.connect("notify::active", schedule_settings_save)
    local_dns_switch.connect("notify::active", schedule_settings_save)
    diagnostics_refresh_button.connect(
        "clicked",
        lambda *_args: run_debounced_action(
            "diagnostics-refresh",
            lambda: render_diagnostics(),
            widgets=(diagnostics_refresh_button,),
        ),
    )
    export_bundle_button.connect(
        "clicked",
        lambda *_args: run_debounced_action(
            "diagnostics-export",
            lambda: export_support_bundle(),
            widgets=(export_bundle_button,),
        ),
    )
    window.connect(
        "close-request",
        lambda *_args: (clear_session_watch(), clear_diagnostics_log_watch(), False)[2],
    )

    def draw_telemetry_graph(_area, ctx, width: int, height: int) -> None:
        snapshot = telemetry_cache.get("snapshot")
        if not isinstance(snapshot, SessionTelemetrySnapshot):
            return
        points = _normalized_telemetry_history(snapshot.history)
        if not points:
            return

        ctx.set_source_rgba(0.12, 0.16, 0.24, 0.18)
        ctx.rectangle(0, 0, width, height)
        ctx.fill()

        _draw_rate_line(ctx, width, height, points, "rx")
        _draw_rate_line(ctx, width, height, points, "tx")

    telemetry_graph.set_draw_func(draw_telemetry_graph)

    GLib.timeout_add_seconds(1, periodic_refresh)
    try:
        apply_window_theme(services.settings.load().theme)
    except Exception:
        apply_window_theme(ThemeMode.SYSTEM)
    render_profiles(True)
    sync_shell()
    return window


def _build_stat(grid: Gtk.Grid, label: str, column: int, row: int) -> Gtk.Label:
    wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    wrapper.set_hexpand(True)
    wrapper.set_halign(Gtk.Align.FILL)
    title = Gtk.Label(label=label)
    title.set_xalign(0)
    title.set_hexpand(True)
    title.add_css_class("stat-label")
    value = Gtk.Label(label="0")
    value.set_xalign(0)
    value.set_hexpand(True)
    value.add_css_class("stat-value")
    wrapper.append(title)
    wrapper.append(value)
    grid.attach(wrapper, column, row, 1, 1)
    return value


def _build_section_card(title: str, description: str):
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    card.add_css_class("surface-card")

    header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    card.append(header)

    title_label = Gtk.Label(label=title)
    title_label.set_xalign(0)
    title_label.add_css_class("card-title")
    header.append(title_label)

    description_label = Gtk.Label(label=description)
    description_label.set_xalign(0)
    description_label.set_wrap(True)
    description_label.add_css_class("card-detail")
    header.append(description_label)

    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    card.append(body)
    return card, body


def _build_setting_row(
    title: str,
    description: str,
    control,
    *,
    control_align=None,
):
    row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    row.add_css_class("setting-row")

    labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    row.append(labels)

    title_label = Gtk.Label(label=title)
    title_label.set_xalign(0)
    title_label.add_css_class("setting-title")
    labels.append(title_label)

    description_label = Gtk.Label(label=description)
    description_label.set_xalign(0)
    description_label.set_wrap(True)
    description_label.add_css_class("setting-description")
    labels.append(description_label)

    control.add_css_class("setting-control")
    if Gtk is not None and isinstance(control, Gtk.Switch):
        control.add_css_class("setting-switch")
    else:
        control.add_css_class("setting-field")
    control_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    control_box.set_hexpand(True)
    control_box.set_halign(Gtk.Align.FILL)
    control.set_halign(control_align or Gtk.Align.START)
    control.set_valign(Gtk.Align.CENTER)
    control_box.append(control)
    row.append(control_box)
    return row


def _build_diagnostic_row(title: str, status: str, detail: str | None):
    row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    row.add_css_class("diagnostic-row")

    header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    row.append(header)

    title_label = Gtk.Label(label=title)
    title_label.set_xalign(0)
    title_label.set_hexpand(True)
    title_label.add_css_class("setting-title")
    header.append(title_label)

    status_label = Gtk.Label(label=status)
    status_label.add_css_class("stats-badge")
    header.append(status_label)

    if detail:
        detail_label = Gtk.Label(label=detail)
        detail_label.set_xalign(0)
        detail_label.set_wrap(True)
        detail_label.add_css_class("setting-description")
        row.append(detail_label)

    return row


def _clear_box(box) -> None:
    while True:
        child = box.get_first_child()
        if child is None:
            break
        box.remove(child)


def _bind_card_interactions(card) -> None:
    if Gtk is None:
        return

    motion = Gtk.EventControllerMotion()
    motion.connect("enter", lambda *_args: card.add_css_class("profile-card-hover"))
    motion.connect("leave", lambda *_args: card.remove_css_class("profile-card-hover"))
    card.add_controller(motion)

    click = Gtk.GestureClick()
    click.connect("pressed", lambda *_args: card.add_css_class("profile-card-pressed"))
    click.connect("released", lambda *_args: card.remove_css_class("profile-card-pressed"))
    click.connect("cancel", lambda *_args: card.remove_css_class("profile-card-pressed"))
    card.add_controller(click)


def _format_duration(snapshot: SessionSnapshot) -> str:
    if snapshot.active_session is None:
        return "00:00:00"
    delta = datetime.now(timezone.utc) - snapshot.active_session.created_at
    total_seconds = max(0, int(delta.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _format_last_update(snapshot: SessionSnapshot) -> str:
    if snapshot.active_session is None:
        return "just now"
    delta = datetime.now(timezone.utc) - snapshot.active_session.updated_at
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 5:
        return "just now"
    return f"{seconds}s ago"


def _stats_title_for(snapshot: SessionSnapshot) -> str:
    if snapshot.state is SessionPhase.CONNECTED:
        return "Secure tunnel active"
    if snapshot.state is SessionPhase.PAUSED:
        return "Tunnel paused"
    if snapshot.state is SessionPhase.RECONNECTING:
        return "Re-establishing the secure tunnel"
    if snapshot.state is SessionPhase.CONNECTING:
        return "Negotiating connection"
    return "Session status"


def _stats_body_for(snapshot: SessionSnapshot) -> str:
    if snapshot.active_session is None:
        return "No live session is currently active."
    if snapshot.active_session.status_message:
        return snapshot.active_session.status_message
    if snapshot.state is SessionPhase.CONNECTED:
        return "The VPN tunnel is connected and being monitored live."
    if snapshot.state is SessionPhase.PAUSED:
        return "Traffic is paused until the session is resumed."
    if snapshot.state is SessionPhase.RECONNECTING:
        return "OpenVPN is attempting to restore connectivity."
    if snapshot.state is SessionPhase.CONNECTING:
        return "OpenVPN is preparing the secure session."
    return "Live session details are shown below."


def _should_show_summary(snapshot: SessionSnapshot) -> bool:
    if snapshot.state is SessionPhase.ERROR and snapshot.last_error:
        return True
    return snapshot.active_session is not None and snapshot.state is not SessionPhase.IDLE


def _summary_title_for(snapshot: SessionSnapshot, profile_name: str) -> str:
    if snapshot.state is SessionPhase.ERROR and not snapshot.selected_profile_id:
        return "Connection recovery"
    return profile_name


def _summary_detail_for(snapshot: SessionSnapshot) -> str:
    if snapshot.state is SessionPhase.ERROR and snapshot.last_error:
        if snapshot.selected_profile_id:
            return f"{snapshot.last_error} Retry the connection or dismiss this error."
        return snapshot.last_error
    if snapshot.attention_requests:
        return (
            f"{len(snapshot.attention_requests)} credential or challenge field(s) "
            "required before connection can continue."
        )
    if snapshot.state is SessionPhase.CONNECTED:
        return "Connection is active. Session details and live status are shown below."
    if snapshot.state is SessionPhase.PAUSED:
        return "Connection is paused. Resume when you are ready."
    if snapshot.state is SessionPhase.RECONNECTING:
        return (
            snapshot.active_session.status_message
            if snapshot.active_session is not None and snapshot.active_session.status_message
            else "The tunnel dropped and OpenVPN is trying to restore connectivity."
        )
    if snapshot.state is SessionPhase.CONNECTING:
        return (
            snapshot.active_session.status_message
            if snapshot.active_session is not None and snapshot.active_session.status_message
            else "OpenVPN is negotiating the secure tunnel. You can cancel if this stalls."
        )
    if snapshot.state is SessionPhase.DISCONNECTING:
        return (
            snapshot.active_session.status_message
            if snapshot.active_session is not None and snapshot.active_session.status_message
            else "OpenVPN is closing the current session."
        )
    if snapshot.active_session is not None and snapshot.active_session.status_message:
        return snapshot.active_session.status_message
    return "Session is active."


def _summary_action_labels(snapshot: SessionSnapshot) -> tuple[str | None, str | None]:
    if snapshot.state is SessionPhase.ERROR:
        if snapshot.selected_profile_id:
            return ("Retry", "Dismiss")
        return (None, "Dismiss")
    if snapshot.state is SessionPhase.CONNECTED:
        return ("Pause", "Disconnect")
    if snapshot.state is SessionPhase.PAUSED:
        return ("Resume", "Disconnect")
    if snapshot.attention_requests:
        return ("Continue", "Cancel")
    if snapshot.state in {SessionPhase.READY, SessionPhase.SESSION_CREATED}:
        return ("Connect", "Cancel")
    if snapshot.state is SessionPhase.CONNECTING:
        return ("Refresh", "Cancel")
    if snapshot.state is SessionPhase.RECONNECTING:
        return ("Refresh", "Disconnect")
    if snapshot.state is SessionPhase.DISCONNECTING:
        return ("Refresh", None)
    if snapshot.active_session is not None:
        return ("Refresh", "Disconnect")
    return (None, None)


def _status_presentation(snapshot: SessionSnapshot) -> tuple[str, str]:
    if snapshot.state is SessionPhase.CONNECTED:
        return ("CONNECTED", "status-connected")
    if snapshot.state is SessionPhase.CONNECTING:
        return ("CONNECTING", "status-connected")
    if snapshot.state is SessionPhase.RECONNECTING:
        return ("RECONNECTING", "status-paused")
    if snapshot.state is SessionPhase.PAUSED:
        return ("PAUSED", "status-paused")
    if snapshot.state is SessionPhase.WAITING_FOR_INPUT:
        return ("ACTION REQUIRED", "status-paused")
    if snapshot.state is SessionPhase.DISCONNECTING:
        return ("DISCONNECTING", "status-paused")
    if snapshot.state is SessionPhase.ERROR:
        return ("NEEDS RECOVERY", "status-disconnected")
    if snapshot.state is SessionPhase.IDLE:
        return ("DISCONNECTED", "status-disconnected")
    return (snapshot.state.value.replace("_", " ").upper(), "status-connected")


def _telemetry_value(
    snapshot: SessionTelemetrySnapshot | None,
    key: str,
) -> int | float | None:
    if snapshot is None:
        return None
    return getattr(snapshot.sample, key)


def _telemetry_rate(
    snapshot: SessionTelemetrySnapshot | None,
    direction: str,
) -> float | None:
    if snapshot is None:
        return None
    return snapshot.rx_rate_bps if direction == "rx" else snapshot.tx_rate_bps


def _format_bytes(value: int | float | None) -> str:
    if value is None:
        return "N/A"
    amount = float(value)
    unit = "B"
    for candidate in ("KB", "MB", "GB", "TB"):
        if amount < 1024:
            break
        amount /= 1024
        unit = candidate
    if unit == "B":
        return f"{int(amount)} {unit}"
    return f"{amount:.1f} {unit}"


def _format_rate(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{_format_bytes(value)}/s"


def _format_packets(value: int | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:,}"


def _format_latency(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value < 10:
        return f"{value:.1f} ms"
    return f"{int(round(value))} ms"


def _format_packet_age(snapshot: SessionTelemetrySnapshot | None) -> str:
    if snapshot is None:
        return "N/A"
    times = [
        item
        for item in (
            snapshot.sample.last_packet_received_at,
            snapshot.sample.last_packet_sent_at,
        )
        if item is not None
    ]
    if not times:
        return "N/A"
    delta = datetime.now(timezone.utc) - max(times)
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 2:
        return "just now"
    return f"{seconds}s ago"


def _telemetry_detail(snapshot: SessionTelemetrySnapshot | None) -> str:
    if snapshot is None:
        return "Live telemetry is unavailable."
    if snapshot.sample.available:
        return "Rates are calculated from cumulative backend counters over recent refreshes."
    return snapshot.sample.detail or "Live telemetry is unavailable."


def _normalized_telemetry_history(
    history: tuple[SessionTelemetryPoint, ...],
) -> tuple[tuple[float, float], ...]:
    if not history:
        return ()
    max_rate = max(
        1.0,
        max(
            max(point.rx_rate_bps, point.tx_rate_bps)
            for point in history
        ),
    )
    return tuple(
        (
            min(1.0, point.rx_rate_bps / max_rate),
            min(1.0, point.tx_rate_bps / max_rate),
        )
        for point in history
    )


def _draw_rate_line(
    ctx,
    width: int,
    height: int,
    points: tuple[tuple[float, float], ...],
    direction: str,
) -> None:
    if not points:
        return
    index = 0 if direction == "rx" else 1
    if direction == "rx":
        ctx.set_source_rgba(0.14, 0.63, 0.42, 0.95)
    else:
        ctx.set_source_rgba(0.12, 0.44, 0.90, 0.95)
    ctx.set_line_width(2.0)
    denominator = max(1, len(points) - 1)
    for offset, point in enumerate(points):
        x = 8 + ((width - 16) * offset / denominator)
        y = (height - 8) - ((height - 16) * point[index])
        if offset == 0:
            ctx.move_to(x, y)
        else:
            ctx.line_to(x, y)
    ctx.stroke()


def _subtitle_for_page(page_name: str) -> str:
    return {
        "profiles": "Profiles",
        "settings": "Settings",
        "diagnostics": "Diagnostics",
    }.get(page_name, "OpenVPN Client")


def _refresh_tooltip_for_page(page_name: str) -> str:
    return {
        "profiles": "Refresh profiles and session status",
        "settings": "Reload settings from disk",
        "diagnostics": "Refresh diagnostics snapshot",
    }.get(page_name, "Refresh current view")


def _display_capability_name(key: str) -> str:
    return {
        "dco": "Data Channel Offload",
        "posture": "Device Posture",
    }.get(key, key.replace("-", " ").replace("_", " ").title())


def _capability_detail(capability: CapabilityState) -> str:
    if capability.available:
        return capability.reason or "Detected on this system."
    return capability.reason or "Unavailable on this system."


def _short_service_name(service_name: str) -> str:
    return service_name.rsplit(".", maxsplit=1)[-1].replace("-", " ").title()


def _diagnostic_status_label(status: DiagnosticStatus) -> str:
    return {
        DiagnosticStatus.PASS: "Pass",
        DiagnosticStatus.WARN: "Warning",
        DiagnosticStatus.FAIL: "Action",
        DiagnosticStatus.INFO: "Info",
    }[status]


def _diagnostics_summary(snapshot) -> str:
    issue_count = sum(
        1
        for item in snapshot.troubleshooting_items
        if item.status in {DiagnosticStatus.WARN, DiagnosticStatus.FAIL}
    )
    issue_suffix = (
        "no immediate issues detected"
        if issue_count == 0
        else f"{issue_count} diagnostic issue(s) need attention"
    )
    return (
        f"App {snapshot.app_version} running on {snapshot.os_release} with kernel "
        f"{snapshot.kernel}; {issue_suffix}."
    )


def _diagnostic_workflow_detail(workflow) -> str:
    lines = [workflow.summary]
    for index, step in enumerate(workflow.steps, start=1):
        lines.append(f"{index}. {step.title}: {step.detail}")
    return "\n".join(lines)


def _default_support_bundle_path(
    now: datetime | None = None,
    *,
    app_name: str = "openvpn3-client-linux",
) -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return root / app_name / "support-bundles" / f"support-{stamp}.json"


def _settings_signature(settings: AppSettings) -> tuple[tuple[str, object], ...]:
    return tuple(sorted(settings.to_mapping().items()))


def _inactive_profile_details(
    profile: Profile,
    *,
    proxy_name: str | None = None,
) -> list[str]:
    details = []
    hostname = profile.metadata.get("server_hostname")
    username = profile.metadata.get("username")
    if not hostname or not username:
        inferred_username, inferred_hostname = _infer_identity_from_profile_name(profile.name)
        hostname = hostname or inferred_hostname
        username = username or inferred_username

    if hostname:
        details.append(str(hostname))
    if username:
        details.append(str(username))
    details.append(f"Source: {profile.source.value}")
    if profile.assigned_proxy_id:
        details.append(f"Proxy: {proxy_name or profile.assigned_proxy_id}")
    return details


def _infer_identity_from_profile_name(name: str) -> tuple[str | None, str | None]:
    if "@" not in name:
        return None, None
    user_and_host = name.split("[", maxsplit=1)[0].strip()
    if "@" not in user_and_host:
        return None, None
    username, hostname = user_and_host.split("@", maxsplit=1)
    if not username or not hostname:
        return None, None
    return username.strip(), hostname.strip()


def _should_run_debounced_action(
    recent_actions: dict[str, float],
    action_name: str,
    now: float,
    *,
    cooldown_seconds: float = _ACTION_DEBOUNCE_SECONDS,
) -> bool:
    last_run = recent_actions.get(action_name)
    if last_run is None:
        return True
    return now - last_run >= cooldown_seconds


def _set_widgets_sensitive(widgets: tuple[object, ...], sensitive: bool) -> None:
    for widget in widgets:
        if widget is None:
            continue
        try:
            widget.set_sensitive(sensitive)
        except Exception:
            continue
