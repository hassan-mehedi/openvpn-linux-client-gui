from app.dialogs.profile_details_dialog import (
    _normalize_profile_name,
    _normalize_proxy_id,
    _password_hint_text,
)


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
