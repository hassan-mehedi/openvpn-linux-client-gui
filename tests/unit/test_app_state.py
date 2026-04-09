from pathlib import Path
from core.app_state import AppStateService


def test_last_connected_profile_roundtrip(tmp_path: Path) -> None:
    service = AppStateService(state_dir=tmp_path)
    assert service.last_connected_profile_id() is None

    service.record_connected_profile("profile-abc")
    assert service.last_connected_profile_id() == "profile-abc"


def test_last_connected_profile_persists_across_instances(tmp_path: Path) -> None:
    AppStateService(state_dir=tmp_path).record_connected_profile("profile-xyz")
    assert AppStateService(state_dir=tmp_path).last_connected_profile_id() == "profile-xyz"


def test_clear_last_connected_profile(tmp_path: Path) -> None:
    service = AppStateService(state_dir=tmp_path)
    service.record_connected_profile("profile-1")
    service.clear_last_connected_profile()
    assert service.last_connected_profile_id() is None
