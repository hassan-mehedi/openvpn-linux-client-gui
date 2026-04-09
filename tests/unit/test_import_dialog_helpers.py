from app.dialogs.import_url_dialog import _coerce_dropped_files, _review_hint
from core.models import ImportPreview, ImportProfileDetails, ImportSource


class _FakeListModel:
    def __init__(self, items):
        self._items = items

    def get_n_items(self):
        return len(self._items)

    def get_item(self, index):
        return self._items[index]


class _FakeDropValue:
    def __init__(self, items):
        self._items = items

    def get_files(self):
        return self._items


def test_coerce_dropped_files_accepts_plain_python_list() -> None:
    assert _coerce_dropped_files(["a", "b"]) == ["a", "b"]


def test_coerce_dropped_files_accepts_list_model_like_object() -> None:
    files = _FakeListModel(["a", "b"])

    assert _coerce_dropped_files(files) == ["a", "b"]


def test_coerce_dropped_files_unwraps_value_with_get_files() -> None:
    value = _FakeDropValue(["a"])

    assert _coerce_dropped_files(value) == ["a"]


def test_review_hint_prefers_token_url_copy() -> None:
    preview = ImportPreview(
        name="remote.ovpn",
        source=ImportSource.TOKEN_URL,
        canonical_location="https://vpn.example.com/profile.ovpn",
        redacted_location="https://vpn.example.com/profile.ovpn",
        details=ImportProfileDetails(profile_name="remote.ovpn"),
    )

    assert _review_hint(preview) == (
        "Token onboarding was normalized into a standard HTTPS import for review."
    )
