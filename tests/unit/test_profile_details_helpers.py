from datetime import datetime, timezone

from app.dialogs.profile_details_dialog import (
    _format_profile_timestamp,
    _normalize_profile_name,
    _normalize_proxy_id,
    _password_hint_text,
    _profile_backend_state,
    _profile_origin_label,
    _profile_tags_label,
)
from core.models import ImportSource, Profile


def test_normalize_profile_name_trims_outer_whitespace() -> None:
    assert _normalize_profile_name("  ifreturns  ") == "ifreturns"


def test_normalize_proxy_id_returns_none_for_empty_values() -> None:
    assert _normalize_proxy_id("   ") is None


def test_password_hint_text_reports_saved_state() -> None:
    assert (
        _password_hint_text(
            password_saved=True,
            save_password_requested=True,
            secure_storage_available=True,
        )
        == "A password is already stored securely for this profile."
    )


def test_profile_origin_label_redacts_query_string() -> None:
    profile = Profile(
        id="profile-1",
        name="Demo",
        source=ImportSource.URL,
        metadata={"canonical_url": "https://vpn.example.com/profile.ovpn?token=secret"},
    )

    assert _profile_origin_label(profile) == "https://vpn.example.com/profile.ovpn"


def test_profile_backend_state_summarizes_metadata_flags() -> None:
    profile = Profile(
        id="profile-1",
        name="Demo",
        source=ImportSource.FILE,
        metadata={"valid": True, "persistent": True, "readonly": True},
    )

    assert _profile_backend_state(profile) == "Valid, Persistent, Read-only"


def test_profile_tags_label_formats_tuple_values() -> None:
    profile = Profile(
        id="profile-1",
        name="Demo",
        source=ImportSource.FILE,
        metadata={"tags": ("corp", "prod")},
    )

    assert _profile_tags_label(profile) == "corp, prod"


def test_format_profile_timestamp_uses_local_style() -> None:
    formatted = _format_profile_timestamp(datetime(2026, 4, 9, 8, 30, tzinfo=timezone.utc))

    assert formatted.startswith("2026-04-09 ")
