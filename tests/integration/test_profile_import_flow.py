from pathlib import Path

from core.models import ImportSource, Profile
from core.onboarding import OnboardingService


class RecordingBackend:
    def __init__(self) -> None:
        self.profiles: list[Profile] = []

    def list_profiles(self) -> tuple[Profile, ...]:
        return tuple(self.profiles)

    def import_profile_from_bytes(
        self, name: str, payload: bytes, *, source: ImportSource
    ) -> Profile:
        profile = Profile(
            id=f"profile-{len(self.profiles) + 1}",
            name=name,
            source=source,
            metadata={"content_hash": "fixture"},
        )
        self.profiles.append(profile)
        return profile

    def import_profile_from_url(
        self,
        url: str,
        *,
        source: ImportSource,
        name: str | None = None,
    ) -> Profile:
        profile = Profile(
            id=f"profile-{len(self.profiles) + 1}",
            name=name or Path(url).name or "imported.ovpn",
            source=source,
            metadata={"canonical_url": url},
        )
        self.profiles.append(profile)
        return profile


def test_file_import_and_duplicate_detection(tmp_path: Path) -> None:
    backend = RecordingBackend()
    service = OnboardingService(backend)
    profile_path = tmp_path / "demo.ovpn"
    profile_path.write_text("client\nremote vpn.example.com 1194\n", encoding="utf-8")

    first = service.import_file(profile_path)
    preview = service.prepare_file_import(profile_path)

    assert first.source is ImportSource.FILE
    assert preview.duplicate_profile_id == first.id
