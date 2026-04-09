from pathlib import Path

import pytest

from core.models import ImportProfileDetails, ImportSource, Profile
from core.onboarding import OnboardingError, OnboardingService


class FakeBackend:
    def __init__(self, profiles: tuple[Profile, ...] = ()) -> None:
        self._profiles = list(profiles)
        self.imported_urls: list[str] = []

    def list_profiles(self) -> tuple[Profile, ...]:
        return tuple(self._profiles)

    def import_profile_from_bytes(
        self, name: str, payload: bytes, *, source: ImportSource
    ) -> Profile:
        profile = Profile(
            id=f"profile-{len(self._profiles) + 1}",
            name=name,
            source=source,
            metadata={"content_hash": "imported"},
        )
        self._profiles.append(profile)
        return profile

    def import_profile_from_url(
        self,
        url: str,
        *,
        source: ImportSource,
        name: str | None = None,
    ) -> Profile:
        self.imported_urls.append(url)
        profile = Profile(
            id=f"profile-{len(self._profiles) + 1}",
            name=name or Path(url).name or "remote.ovpn",
            source=source,
            metadata={"canonical_url": url},
        )
        self._profiles.append(profile)
        return profile


def test_prepare_url_import_detects_duplicates() -> None:
    backend = FakeBackend(
        (
            Profile(
                id="profile-1",
                name="Existing",
                source=ImportSource.URL,
                metadata={"canonical_url": "https://vpn.example.com/profile.ovpn"},
            ),
        )
    )
    service = OnboardingService(backend)

    preview = service.prepare_url_import("https://vpn.example.com/profile.ovpn")

    assert preview.duplicate_profile_id == "profile-1"
    assert preview.duplicate_profile_name == "Existing"
    assert preview.duplicate_reason == "Matching import URL"


def test_prepare_token_url_import_normalizes_and_redacts() -> None:
    backend = FakeBackend()
    service = OnboardingService(backend)

    preview = service.prepare_token_url_import(
        "openvpn://import-profile/https%3A%2F%2Fvpn.example.com%2Fdownload%3Ftoken%3Dabc123"
    )

    assert preview.canonical_location == "https://vpn.example.com/download?token=abc123"
    assert preview.redacted_location == "https://vpn.example.com/download?redacted"
    assert preview.source is ImportSource.TOKEN_URL
    assert preview.details == ImportProfileDetails(
        profile_name="download",
        server_hostname="vpn.example.com",
        username=None,
        server_locked=True,
        username_locked=False,
        auth_requires_password=False,
    )
    assert "Token URL was normalized into a secure HTTPS import." in preview.warnings


def test_prepare_url_import_rejects_non_https() -> None:
    service = OnboardingService(FakeBackend())

    with pytest.raises(OnboardingError):
        service.prepare_url_import("http://vpn.example.com/profile.ovpn")


def test_prepare_url_import_rejects_embedded_credentials() -> None:
    service = OnboardingService(FakeBackend())

    with pytest.raises(OnboardingError):
        service.prepare_url_import("https://alice:secret@vpn.example.com/profile.ovpn")


def test_prepare_url_import_infers_remote_details_and_warnings() -> None:
    service = OnboardingService(FakeBackend())

    preview = service.prepare_url_import("https://vpn.example.com/download?token=secret")

    assert preview.name == "download"
    assert preview.details == ImportProfileDetails(
        profile_name="download",
        server_hostname="vpn.example.com",
        username=None,
        server_locked=True,
        username_locked=False,
        auth_requires_password=False,
    )
    assert preview.warnings == (
        "Sensitive query parameters are redacted in previews and support bundles.",
        "The final profile name may change after download because the URL does not end with .ovpn.",
    )


def test_prepare_file_import_hashes_payload(tmp_path: Path) -> None:
    profile = tmp_path / "profile.ovpn"
    profile.write_text("client\nremote vpn.example.com 1194\n", encoding="utf-8")
    service = OnboardingService(FakeBackend())

    preview = service.prepare_file_import(profile)

    assert preview.content_hash
    assert preview.canonical_location == str(profile)
    assert preview.details == ImportProfileDetails(
        profile_name="profile.ovpn",
        server_hostname="vpn.example.com",
        username=None,
        server_locked=True,
        username_locked=False,
        auth_requires_password=False,
    )


def test_prepare_file_import_extracts_windows_style_profile_details(tmp_path: Path) -> None:
    profile = tmp_path / "access.ovpn"
    profile.write_text(
        (
            'setenv FRIENDLY_NAME "Corp VPN"\n'
            "remote vpn.example.com 443\n"
            "<auth-user-pass>\n"
            "openvpn\n"
            "secret\n"
            "</auth-user-pass>\n"
        ),
        encoding="utf-8",
    )
    service = OnboardingService(FakeBackend())

    preview = service.prepare_file_import(profile)

    assert preview.details == ImportProfileDetails(
        profile_name="Corp VPN",
        server_hostname="vpn.example.com",
        username="openvpn",
        server_locked=True,
        username_locked=True,
        auth_requires_password=True,
    )
    assert preview.warnings == (
        "This profile still requires authentication during connection.",
    )
