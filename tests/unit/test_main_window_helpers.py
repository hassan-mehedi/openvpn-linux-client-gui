from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.windows.main_window import (
    _capability_detail,
    _default_support_bundle_path,
    _diagnostics_summary,
    _display_capability_name,
    _format_duration,
    _format_last_update,
    _inactive_profile_details,
    _infer_identity_from_profile_name,
    _refresh_tooltip_for_page,
    _settings_signature,
    _should_run_debounced_action,
    _short_service_name,
    _subtitle_for_page,
    _stats_body_for,
    _stats_title_for,
)
from core.models import AppSettings, CapabilityState, ImportSource, Profile, SessionDescriptor, SessionPhase
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
    assert (
        _diagnostics_summary("0.1.0", "Fedora Linux 42", "6.8.0")
        == "App 0.1.0 running on Fedora Linux 42 with kernel 6.8.0."
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
