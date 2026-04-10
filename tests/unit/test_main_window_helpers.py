from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.windows.main_window import (
    _diagnostic_workflow_detail,
    _capability_detail,
    _diagnostic_status_label,
    _default_support_bundle_path,
    _diagnostics_summary,
    _display_capability_name,
    _format_bytes,
    _format_duration,
    _format_last_update,
    _format_latency,
    _format_packet_age,
    _format_packets,
    _format_rate,
    _inactive_profile_details,
    _infer_identity_from_profile_name,
    _is_window_maximized,
    _maximize_window,
    _minimize_window,
    _normalized_telemetry_history,
    _refresh_tooltip_for_page,
    _settings_signature,
    _unmaximize_window,
    _should_run_debounced_action,
    _should_show_summary,
    _short_service_name,
    _status_presentation,
    _summary_action_labels,
    _summary_detail_for,
    _summary_title_for,
    _subtitle_for_page,
    _telemetry_detail,
    _stats_body_for,
    _stats_title_for,
)
from core.models import (
    AppSettings,
    CapabilityState,
    DiagnosticCheck,
    DiagnosticStatus,
    DiagnosticWorkflow,
    DiagnosticWorkflowStep,
    DiagnosticsSnapshot,
    ImportSource,
    Profile,
    SessionDescriptor,
    SessionPhase,
    SessionTelemetryPoint,
    SessionTelemetrySample,
    SessionTelemetrySnapshot,
)
from core.session_manager import SessionSnapshot


def _snapshot(
    *,
    state: SessionPhase,
    status_message: str = "",
    created_offset: int = 0,
    updated_offset: int = 0,
) -> SessionSnapshot:
    now = datetime.now(timezone.utc)
    session = SessionDescriptor(
        id="session-12345678",
        profile_id="profile-1",
        state=state,
        status_message=status_message,
        created_at=now - timedelta(seconds=created_offset),
        updated_at=now - timedelta(seconds=updated_offset),
    )
    return SessionSnapshot(
        state=state,
        selected_profile_id="profile-1",
        active_session=session,
        attention_requests=(),
        last_error=None,
    )


def test_format_duration_uses_elapsed_session_age() -> None:
    snapshot = _snapshot(state=SessionPhase.CONNECTED, created_offset=3723)
    assert _format_duration(snapshot) == "01:02:03"


def test_format_last_update_uses_humanized_recent_text() -> None:
    snapshot = _snapshot(state=SessionPhase.CONNECTED, updated_offset=19)
    assert _format_last_update(snapshot) == "19s ago"


def test_stats_copy_prefers_connected_messages() -> None:
    snapshot = _snapshot(state=SessionPhase.CONNECTED)
    assert _stats_title_for(snapshot) == "Secure tunnel active"
    assert _stats_body_for(snapshot) == "The VPN tunnel is connected and being monitored live."


def test_stats_copy_prefers_backend_status_when_available() -> None:
    snapshot = _snapshot(
        state=SessionPhase.RECONNECTING,
        status_message="Waiting for server response.",
    )
    assert _stats_title_for(snapshot) == "Re-establishing the secure tunnel"
    assert _stats_body_for(snapshot) == "Waiting for server response."


def test_summary_visibility_allows_persistent_error_state() -> None:
    snapshot = SessionSnapshot(
        state=SessionPhase.ERROR,
        selected_profile_id="profile-1",
        active_session=None,
        attention_requests=(),
        last_error="Connection timed out after 5 seconds.",
    )

    assert _should_show_summary(snapshot) is True


def test_summary_copy_guides_recovery_for_error_state() -> None:
    snapshot = SessionSnapshot(
        state=SessionPhase.ERROR,
        selected_profile_id="profile-1",
        active_session=None,
        attention_requests=(),
        last_error="Connection timed out after 5 seconds.",
    )

    assert _summary_title_for(snapshot, "Office VPN") == "Office VPN"
    assert (
        _summary_detail_for(snapshot)
        == "Connection timed out after 5 seconds. Retry the connection or dismiss this error."
    )
    assert _summary_action_labels(snapshot) == ("Retry", "Dismiss")


def test_summary_copy_guides_connecting_state() -> None:
    snapshot = _snapshot(state=SessionPhase.CONNECTING)

    assert (
        _summary_detail_for(snapshot)
        == "OpenVPN is negotiating the secure tunnel. You can cancel if this stalls."
    )
    assert _summary_action_labels(snapshot) == ("Refresh", "Cancel")


def test_status_presentation_uses_recovery_and_action_required_labels() -> None:
    waiting = _snapshot(state=SessionPhase.WAITING_FOR_INPUT)
    error = SessionSnapshot(
        state=SessionPhase.ERROR,
        selected_profile_id="profile-1",
        active_session=None,
        attention_requests=(),
        last_error="TLS 1.3 is unavailable.",
    )

    assert _status_presentation(waiting) == ("ACTION REQUIRED", "status-paused")
    assert _status_presentation(error) == ("NEEDS RECOVERY", "status-disconnected")


def test_format_bytes_uses_human_units() -> None:
    assert _format_bytes(1536) == "1.5 KB"


def test_format_rate_uses_byte_units_per_second() -> None:
    assert _format_rate(2048.0) == "2.0 KB/s"


def test_format_latency_rounds_reasonably() -> None:
    assert _format_latency(25.4) == "25 ms"


def test_format_packets_uses_grouping() -> None:
    assert _format_packets(12345) == "12,345"


def test_format_packet_age_uses_latest_packet_timestamp() -> None:
    now = datetime.now(timezone.utc)
    snapshot = SessionTelemetrySnapshot(
        sample=SessionTelemetrySample(
            session_id="session-1",
            last_packet_received_at=now - timedelta(seconds=6),
            last_packet_sent_at=now - timedelta(seconds=3),
            updated_at=now,
            available=True,
        )
    )

    assert _format_packet_age(snapshot) == "3s ago"


def test_telemetry_detail_prefers_backend_message_when_unavailable() -> None:
    snapshot = SessionTelemetrySnapshot(
        sample=SessionTelemetrySample(
            session_id="session-1",
            updated_at=datetime.now(timezone.utc),
            available=False,
            detail="Session telemetry is not exposed by the backend.",
        )
    )

    assert _telemetry_detail(snapshot) == "Session telemetry is not exposed by the backend."


def test_normalized_telemetry_history_scales_to_peak_rate() -> None:
    points = (
        SessionTelemetryPoint(
            captured_at=datetime.now(timezone.utc),
            rx_rate_bps=100.0,
            tx_rate_bps=50.0,
        ),
        SessionTelemetryPoint(
            captured_at=datetime.now(timezone.utc),
            rx_rate_bps=200.0,
            tx_rate_bps=150.0,
        ),
    )

    assert _normalized_telemetry_history(points) == (
        (0.5, 0.25),
        (1.0, 0.75),
    )


def test_infer_identity_from_profile_name_extracts_username_and_host() -> None:
    assert _infer_identity_from_profile_name("openvpn@vpn.example.com [profile-6]") == (
        "openvpn",
        "vpn.example.com",
    )


def test_inactive_profile_details_prefers_inferred_windows_style_identity() -> None:
    profile = Profile(
        id="profile-1",
        name="openvpn@vpn.example.com [profile-6]",
        source=ImportSource.FILE,
    )

    assert _inactive_profile_details(profile) == [
        "vpn.example.com",
        "openvpn",
        "Source: file",
    ]


def test_inactive_profile_details_prefers_proxy_name_over_raw_identifier() -> None:
    profile = Profile(
        id="profile-1",
        name="openvpn@vpn.example.com [profile-6]",
        source=ImportSource.FILE,
        assigned_proxy_id="proxy-1",
    )

    assert _inactive_profile_details(profile, proxy_name="Office Proxy") == [
        "vpn.example.com",
        "openvpn",
        "Source: file",
        "Proxy: Office Proxy",
    ]


def test_should_run_debounced_action_blocks_rapid_repeat() -> None:
    recent_actions = {"refresh": 10.0}

    assert (
        _should_run_debounced_action(
            recent_actions,
            "refresh",
            10.2,
            cooldown_seconds=0.75,
        )
        is False
    )


def test_should_run_debounced_action_allows_after_cooldown() -> None:
    recent_actions = {"refresh": 10.0}

    assert (
        _should_run_debounced_action(
            recent_actions,
            "refresh",
            10.8,
            cooldown_seconds=0.75,
        )
        is True
    )


def test_subtitle_for_page_matches_shell_sections() -> None:
    assert _subtitle_for_page("profiles") == "Profiles"
    assert _subtitle_for_page("settings") == "Settings"
    assert _subtitle_for_page("diagnostics") == "Diagnostics"


def test_refresh_tooltip_for_page_matches_current_view() -> None:
    assert _refresh_tooltip_for_page("settings") == "Reload settings from disk"


def test_display_capability_name_prefers_friendly_labels() -> None:
    assert _display_capability_name("dco") == "Data Channel Offload"
    assert _display_capability_name("posture") == "Device Posture"


def test_capability_detail_prefers_reason_text() -> None:
    capability = CapabilityState(
        key="dco",
        available=False,
        reason="Kernel DCO module not detected.",
    )

    assert _capability_detail(capability) == "Kernel DCO module not detected."


def test_short_service_name_uses_last_dbus_segment() -> None:
    assert _short_service_name("net.openvpn.v3.configuration") == "Configuration"


def test_diagnostics_summary_includes_platform_details() -> None:
    snapshot = DiagnosticsSnapshot(
        app_version="0.1.0",
        os_release="Fedora Linux 42",
        kernel="6.8.0",
        desktop_environment="GNOME",
        reachable_services={},
        capabilities=(),
        environment_checks=(),
        troubleshooting_items=(
            DiagnosticCheck(
                key="resolver",
                label="Resolver",
                status=DiagnosticStatus.WARN,
                detail="systemd-resolved missing",
            ),
        ),
        guided_workflows=(),
        recent_logs=(),
        profiles=(),
        settings=AppSettings(),
    )
    assert (
        _diagnostics_summary(snapshot)
        == "App 0.1.0 running on Fedora Linux 42 with kernel 6.8.0; 1 diagnostic issue(s) need attention."
    )


def test_diagnostic_status_label_uses_short_ui_copy() -> None:
    assert _diagnostic_status_label(DiagnosticStatus.PASS) == "Pass"
    assert _diagnostic_status_label(DiagnosticStatus.FAIL) == "Action"


def test_diagnostic_workflow_detail_formats_summary_and_steps() -> None:
    workflow = DiagnosticWorkflow(
        key="resolver",
        label="Repair VPN DNS handling",
        status=DiagnosticStatus.WARN,
        summary="Resolver support is missing.",
        steps=(
            DiagnosticWorkflowStep(
                title="Use local DNS",
                detail="Avoid the global resolver dependency.",
            ),
            DiagnosticWorkflowStep(
                title="Install resolver integration",
                detail="Enable systemd-resolved support before retrying.",
            ),
        ),
    )

    assert _diagnostic_workflow_detail(workflow) == (
        "Resolver support is missing.\n"
        "1. Use local DNS: Avoid the global resolver dependency.\n"
        "2. Install resolver integration: Enable systemd-resolved support before retrying."
    )


def test_default_support_bundle_path_uses_xdg_state_home(monkeypatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", "/tmp/ovpn-state")

    path = _default_support_bundle_path(
        datetime(2026, 4, 8, 12, 30, 0),
        app_name="ovpn-demo",
    )

    assert path == Path("/tmp/ovpn-state/ovpn-demo/support-bundles/support-20260408-123000.json")


def test_settings_signature_changes_when_settings_change() -> None:
    baseline = AppSettings()
    changed = AppSettings(connection_timeout=45)

    assert _settings_signature(baseline) != _settings_signature(changed)


def test_is_window_maximized_prefers_explicit_accessor() -> None:
    class FakeWindow:
        def is_maximized(self) -> bool:
            return True

    assert _is_window_maximized(FakeWindow()) is True


def test_window_helpers_delegate_to_available_methods() -> None:
    calls: list[str] = []

    class FakeWindow:
        def minimize(self) -> None:
            calls.append("minimize")

        def maximize(self) -> None:
            calls.append("maximize")

        def unmaximize(self) -> None:
            calls.append("unmaximize")

    window = FakeWindow()
    _minimize_window(window)
    _maximize_window(window)
    _unmaximize_window(window)

    assert calls == ["minimize", "maximize", "unmaximize"]
