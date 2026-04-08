from app.dialogs.profile_details_dialog import _normalize_profile_name


def test_normalize_profile_name_trims_outer_whitespace() -> None:
    assert _normalize_profile_name("  ifreturns  ") == "ifreturns"
