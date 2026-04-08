"""Profile onboarding orchestration."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, unquote, urlsplit

from core.models import ImportPreview, ImportProfileDetails, ImportSource, Profile


class OnboardingError(ValueError):
    """Raised when onboarding input cannot be processed safely."""


class ProfileImportBackend(Protocol):
    def list_profiles(self) -> tuple[Profile, ...]:
        """Return known profiles."""

    def import_profile_from_bytes(
        self, name: str, payload: bytes, *, source: ImportSource
    ) -> Profile:
        """Import a profile from bytes."""

    def import_profile_from_url(
        self,
        url: str,
        *,
        source: ImportSource,
        name: str | None = None,
    ) -> Profile:
        """Import a profile from a URL."""


class OnboardingService:
    def __init__(self, backend: ProfileImportBackend) -> None:
        self._backend = backend

    def prepare_file_import(
        self, path: Path, *, source: ImportSource = ImportSource.FILE
    ) -> ImportPreview:
        if path.suffix.lower() != ".ovpn":
            raise OnboardingError("Only .ovpn profiles can be imported.")

        payload = path.read_bytes()
        if not payload.strip():
            raise OnboardingError("Profile file is empty.")

        content_hash = hashlib.sha256(payload).hexdigest()
        duplicate_profile_id = self._find_duplicate(content_hash=content_hash)
        details = self.inspect_profile_bytes(path.name, payload)
        return ImportPreview(
            name=path.name,
            source=source,
            canonical_location=str(path),
            redacted_location=str(path),
            content_hash=content_hash,
            duplicate_profile_id=duplicate_profile_id,
            details=details,
        )

    def prepare_url_import(self, url: str) -> ImportPreview:
        canonical_url = self._validate_https_url(url)
        duplicate_profile_id = self._find_duplicate(canonical_url=canonical_url)
        redacted_url = self._redact_url(canonical_url)
        return ImportPreview(
            name=Path(urlsplit(canonical_url).path).name or "remote-profile.ovpn",
            source=ImportSource.URL,
            canonical_location=canonical_url,
            redacted_location=redacted_url,
            duplicate_profile_id=duplicate_profile_id,
            details=ImportProfileDetails(
                profile_name=Path(urlsplit(canonical_url).path).name or "remote-profile.ovpn"
            ),
        )

    def prepare_token_url_import(self, token_url: str) -> ImportPreview:
        canonical_url = self._normalize_token_url(token_url)
        duplicate_profile_id = self._find_duplicate(canonical_url=canonical_url)
        return ImportPreview(
            name=Path(urlsplit(canonical_url).path).name or "token-profile.ovpn",
            source=ImportSource.TOKEN_URL,
            canonical_location=canonical_url,
            redacted_location=self._redact_url(canonical_url),
            duplicate_profile_id=duplicate_profile_id,
            warnings=("Token URL was normalized into a secure HTTPS import.",),
            details=ImportProfileDetails(
                profile_name=Path(urlsplit(canonical_url).path).name or "token-profile.ovpn"
            ),
        )

    def import_file(
        self,
        path: Path,
        *,
        source: ImportSource = ImportSource.FILE,
        profile_name: str | None = None,
    ) -> Profile:
        preview = self.prepare_file_import(path, source=source)
        import_name = (profile_name or preview.details.profile_name or preview.name).strip()
        profile = self._backend.import_profile_from_bytes(
            import_name,
            path.read_bytes(),
            source=preview.source,
        )
        profile.metadata["content_hash"] = preview.content_hash
        if preview.details is not None:
            profile.metadata["profile_name"] = import_name
            profile.metadata["server_hostname"] = preview.details.server_hostname
            profile.metadata["username"] = preview.details.username
        return profile

    def import_url(self, url: str, *, profile_name: str | None = None) -> Profile:
        preview = self.prepare_url_import(url)
        import_name = (profile_name or preview.details.profile_name or preview.name).strip()
        profile = self._backend.import_profile_from_url(
            preview.canonical_location or url,
            source=preview.source,
            name=import_name,
        )
        profile.metadata["canonical_url"] = preview.canonical_location
        profile.metadata["profile_name"] = import_name
        return profile

    def import_token_url(self, token_url: str, *, profile_name: str | None = None) -> Profile:
        preview = self.prepare_token_url_import(token_url)
        import_name = (profile_name or preview.details.profile_name or preview.name).strip()
        profile = self._backend.import_profile_from_url(
            preview.canonical_location or token_url,
            source=preview.source,
            name=import_name,
        )
        profile.metadata["canonical_url"] = preview.canonical_location
        profile.metadata["profile_name"] = import_name
        return profile

    def _find_duplicate(
        self,
        *,
        canonical_url: str | None = None,
        content_hash: str | None = None,
    ) -> str | None:
        for profile in self._backend.list_profiles():
            if canonical_url and profile.metadata.get("canonical_url") == canonical_url:
                return profile.id
            if content_hash and profile.metadata.get("content_hash") == content_hash:
                return profile.id
        return None

    def inspect_profile_bytes(self, name: str, payload: bytes) -> ImportProfileDetails:
        text = payload.decode("utf-8", errors="replace")
        directives = _parse_profile_directives(text)
        profile_name = (
            directives.get("friendly_name")
            or directives.get("client_name")
            or name
        )
        server_hostname = directives.get("remote")
        username = directives.get("username")
        auth_requires_password = bool(
            directives.get("auth_user_pass") or directives.get("embedded_auth_user_pass")
        )
        return ImportProfileDetails(
            profile_name=profile_name,
            server_hostname=server_hostname,
            username=username,
            server_locked=server_hostname is not None,
            username_locked=username is not None,
            auth_requires_password=auth_requires_password,
        )

    def _normalize_token_url(self, token_url: str) -> str:
        prefix = "openvpn://import-profile/"
        if not token_url.startswith(prefix):
            raise OnboardingError("Unsupported token URL format.")

        raw_target = unquote(token_url[len(prefix) :])
        canonical_target = self._validate_https_url(raw_target)
        return canonical_target

    def _validate_https_url(self, url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme != "https":
            raise OnboardingError("Only HTTPS import URLs are allowed.")
        if not parts.netloc:
            raise OnboardingError("Import URL must include a host.")
        return parts.geturl()

    def _redact_url(self, url: str) -> str:
        parts = urlsplit(url)
        path = parts.path
        if parts.query:
            return f"{parts.scheme}://{parts.netloc}{path}?redacted"
        if "token" in path.lower():
            return f"{parts.scheme}://{parts.netloc}{quote(path)}"
        return parts.geturl()


_DIRECTIVE_PATTERN = re.compile(r"^\s*([A-Za-z0-9_.-]+)(?:\s+(.*?))?\s*$")


def _parse_profile_directives(payload: str) -> dict[str, str | bool]:
    metadata: dict[str, str | bool] = {}
    lines = payload.splitlines()
    embedded_user_pass = _extract_embedded_auth(lines)
    if embedded_user_pass:
        metadata["embedded_auth_user_pass"] = True
        metadata["username"] = embedded_user_pass[0]

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        match = _DIRECTIVE_PATTERN.match(line)
        if not match:
            continue
        key = match.group(1).lower()
        value = (match.group(2) or "").strip()
        if key == "setenv":
            env_key, env_value = _split_first_token(value)
            if env_key in {"FRIENDLY_NAME", "CLIENT_NAME"} and env_value:
                metadata[env_key.lower()] = _strip_quotes(env_value)
            continue
        if key == "remote" and value and "remote" not in metadata:
            host, _remainder = _split_first_token(value)
            if host:
                metadata["remote"] = _strip_quotes(host)
            continue
        if key == "auth-user-pass":
            metadata["auth_user_pass"] = True
            if value and value != "[inline]" and "username" not in metadata:
                metadata["username"] = Path(_strip_quotes(value)).stem
            continue
        if key in {"username", "user"} and value and "username" not in metadata:
            metadata["username"] = _strip_quotes(value)
    return metadata


def _extract_embedded_auth(lines: list[str]) -> tuple[str, str | None] | None:
    for index, raw_line in enumerate(lines):
        if raw_line.strip().lower() != "<auth-user-pass>":
            continue
        username: str | None = None
        password: str | None = None
        for embedded_line in lines[index + 1 :]:
            stripped = embedded_line.strip()
            if stripped.lower() == "</auth-user-pass>":
                return (username or "", password)
            if stripped and username is None:
                username = stripped
            elif stripped and password is None:
                password = stripped
        return None
    return None


def _split_first_token(value: str) -> tuple[str, str]:
    if not value:
        return "", ""
    parts = value.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _strip_quotes(value: str) -> str:
    return value.strip().strip('"').strip("'")
