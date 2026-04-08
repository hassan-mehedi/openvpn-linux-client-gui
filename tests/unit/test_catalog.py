from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.catalog import ProfileCatalogService
from core.models import ImportPreview, ImportSource, Profile


class FakeProfileBackend:
    def __init__(self, profiles: tuple[Profile, ...]) -> None:
        self._profiles = list(profiles)
        self.deleted: list[str] = []

    def list_profiles(self) -> tuple[Profile, ...]:
        return tuple(self._profiles)

    def delete_profile(self, profile_id: str) -> None:
        self.deleted.append(profile_id)
        self._profiles = [item for item in self._profiles if item.id != profile_id]


class FakeOnboarding:
    def prepare_file_import(
        self,
        path: Path,
        *,
        source: ImportSource = ImportSource.FILE,
    ) -> ImportPreview:
        return ImportPreview(
            name=path.name,
            source=source,
            canonical_location=str(path),
            redacted_location=str(path),
            content_hash="abc",
        )

    def prepare_url_import(self, url: str) -> ImportPreview:
        return ImportPreview(
            name="remote.ovpn",
            source=ImportSource.URL,
            canonical_location=url,
            redacted_location=url,
        )

    def prepare_token_url_import(self, token_url: str) -> ImportPreview:
        return ImportPreview(
            name="remote.ovpn",
            source=ImportSource.TOKEN_URL,
            canonical_location=token_url,
            redacted_location="openvpn://import-profile/redacted",
        )

    def import_file(
        self,
        path: Path,
        *,
        source: ImportSource = ImportSource.FILE,
        profile_name: str | None = None,
    ) -> Profile:
        return Profile(
            id="profile-imported",
            name=profile_name or path.name,
            source=source,
        )

    def import_url(self, url: str, *, profile_name: str | None = None) -> Profile:
        return Profile(
            id="profile-url",
            name=profile_name or "remote.ovpn",
            source=ImportSource.URL,
        )

    def import_token_url(
        self,
        token_url: str,
        *,
        profile_name: str | None = None,
    ) -> Profile:
        return Profile(
            id="profile-token",
            name=profile_name or "remote.ovpn",
            source=ImportSource.TOKEN_URL,
        )


def test_catalog_filters_and_sorts_profiles() -> None:
    now = datetime.now(timezone.utc)
    backend = FakeProfileBackend(
        (
            Profile(
                id="profile-1",
                name="Beta",
                source=ImportSource.FILE,
                imported_at=now - timedelta(days=2),
            ),
            Profile(
                id="profile-2",
                name="Alpha",
                source=ImportSource.URL,
                imported_at=now,
            ),
        )
    )
    service = ProfileCatalogService(backend, FakeOnboarding())

    snapshot = service.list_profiles("alp")

    assert [profile.id for profile in snapshot.profiles] == ["profile-2"]


def test_catalog_deletes_through_backend() -> None:
    profile = Profile(id="profile-1", name="Alpha", source=ImportSource.FILE)
    backend = FakeProfileBackend((profile,))
    service = ProfileCatalogService(backend, FakeOnboarding())

    service.delete_profile("profile-1")

    assert backend.deleted == ["profile-1"]


def test_catalog_renames_profile_via_local_override(tmp_path: Path) -> None:
    profile = Profile(id="profile-1", name="Alpha", source=ImportSource.FILE)
    backend = FakeProfileBackend((profile,))
    service = ProfileCatalogService(backend, FakeOnboarding(), config_dir=tmp_path)

    service.rename_profile("profile-1", "Renamed")

    snapshot = service.list_profiles()
    assert snapshot.profiles[0].name == "Renamed"


def test_catalog_import_file_uses_custom_profile_name(tmp_path: Path) -> None:
    backend = FakeProfileBackend(())
    service = ProfileCatalogService(backend, FakeOnboarding(), config_dir=tmp_path)
    profile_path = tmp_path / "client.ovpn"
    profile_path.write_text("client\n", encoding="utf-8")

    imported = service.import_file(profile_path, profile_name="Office VPN")

    assert imported.name == "Office VPN"
