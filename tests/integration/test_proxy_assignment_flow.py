"""Integration tests for the proxy assignment subsystem.

Exercises the full ProxyService lifecycle using a real MemorySecretStore and a
real temporary config directory (no mocks).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.models import ProxyCredentials, ProxyDefinition, ProxyType
from core.proxies import ProxyService, ProxyValidationError
from core.secrets import MemorySecretStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(tmp_path: Path) -> ProxyService:
    return ProxyService(MemorySecretStore(), config_dir=tmp_path)


def _http_proxy(name: str = "CorpProxy", host: str = "proxy.corp.example.com", port: int = 8080) -> ProxyDefinition:
    return ProxyDefinition(id="", name=name, type=ProxyType.HTTP, host=host, port=port)


def _socks_proxy(name: str = "HomeProxy", host: str = "socks.home.example.com", port: int = 1080) -> ProxyDefinition:
    return ProxyDefinition(id="", name=name, type=ProxyType.SOCKS5, host=host, port=port)


# ---------------------------------------------------------------------------
# 1. Full CRUD lifecycle
# ---------------------------------------------------------------------------


def test_crud_lifecycle_create_read_update_delete(tmp_path: Path) -> None:
    """Creating, reading, updating, and deleting a proxy round-trips correctly."""
    service = _make_service(tmp_path)

    # CREATE
    saved = service.save_proxy(_http_proxy())
    assert saved.id, "save_proxy must assign a non-empty id"
    assert saved.name == "CorpProxy"
    assert saved.type == ProxyType.HTTP
    assert saved.host == "proxy.corp.example.com"
    assert saved.port == 8080

    # READ via list
    proxies = service.list_proxies()
    assert len(proxies) == 1
    assert proxies[0].id == saved.id

    # READ via get
    fetched = service.get_proxy(saved.id)
    assert fetched is not None
    assert fetched.id == saved.id
    assert fetched.name == "CorpProxy"

    # UPDATE: change host and port
    updated_def = ProxyDefinition(
        id=saved.id,
        name="CorpProxy",
        type=ProxyType.HTTP,
        host="proxy-new.corp.example.com",
        port=3128,
    )
    updated = service.save_proxy(updated_def)
    assert updated.id == saved.id
    assert updated.host == "proxy-new.corp.example.com"
    assert updated.port == 3128

    # Verify only one proxy still exists
    assert len(service.list_proxies()) == 1

    # DELETE
    service.delete_proxy(saved.id)
    assert service.list_proxies() == ()
    assert service.get_proxy(saved.id) is None


# ---------------------------------------------------------------------------
# 2. Multiple proxies and persistence in proxies.json
# ---------------------------------------------------------------------------


def test_multiple_proxies_persist_to_disk(tmp_path: Path) -> None:
    """Saving multiple proxies writes them all to proxies.json on disk."""
    service = _make_service(tmp_path)

    first = service.save_proxy(_http_proxy(name="Alpha", host="alpha.example.com"))
    second = service.save_proxy(_socks_proxy(name="Beta", host="beta.example.com"))

    proxy_file = tmp_path / "proxies.json"
    assert proxy_file.exists(), "proxies.json must be created"

    payload = json.loads(proxy_file.read_text(encoding="utf-8"))
    assert len(payload) == 2

    ids_on_disk = {item["id"] for item in payload}
    assert first.id in ids_on_disk
    assert second.id in ids_on_disk

    # list_proxies returns both, sorted by name
    listed = service.list_proxies()
    assert len(listed) == 2
    assert listed[0].name.lower() <= listed[1].name.lower()


# ---------------------------------------------------------------------------
# 3. Credential storage via MemorySecretStore
# ---------------------------------------------------------------------------


def test_credential_storage_and_retrieval(tmp_path: Path) -> None:
    """Credentials are stored in the secret store and can be loaded back."""
    store = MemorySecretStore()
    service = ProxyService(store, config_dir=tmp_path)
    creds = ProxyCredentials(username="alice", password="s3cr3t")

    saved = service.save_proxy(_http_proxy(), credentials=creds)

    assert saved.credential_ref is not None, "credential_ref must be set after saving with credentials"

    # Credentials must NOT appear in the JSON file
    raw = (tmp_path / "proxies.json").read_text(encoding="utf-8")
    assert "s3cr3t" not in raw, "plaintext password must not be written to disk"

    # Credentials must be recoverable via the service
    loaded = service.load_proxy_credentials(saved.id)
    assert loaded is not None
    assert loaded.username == "alice"
    assert loaded.password == "s3cr3t"

    # Credentials are also accessible directly via the secret store
    assert store.load_proxy_credentials(saved.credential_ref) == creds


# ---------------------------------------------------------------------------
# 4. Validation — duplicate names are rejected
# ---------------------------------------------------------------------------


def test_validation_rejects_duplicate_proxy_names(tmp_path: Path) -> None:
    """Saving two proxies with the same name (case-insensitive) raises ProxyValidationError."""
    service = _make_service(tmp_path)

    service.save_proxy(_http_proxy(name="Office"))

    with pytest.raises(ProxyValidationError, match="unique"):
        # Same name, different casing — must still be rejected
        service.save_proxy(_socks_proxy(name="office"))


# ---------------------------------------------------------------------------
# 5. Validation — missing required fields
# ---------------------------------------------------------------------------


def test_validation_rejects_blank_name(tmp_path: Path) -> None:
    """A proxy with a blank name raises ProxyValidationError."""
    service = _make_service(tmp_path)
    blank_name = ProxyDefinition(id="", name="   ", type=ProxyType.HTTP, host="proxy.example.com", port=8080)

    with pytest.raises(ProxyValidationError, match="name"):
        service.save_proxy(blank_name)


def test_validation_rejects_blank_host(tmp_path: Path) -> None:
    """A proxy with a blank host raises ProxyValidationError."""
    service = _make_service(tmp_path)
    blank_host = ProxyDefinition(id="", name="MyProxy", type=ProxyType.HTTP, host="   ", port=8080)

    with pytest.raises(ProxyValidationError, match="host"):
        service.save_proxy(blank_host)


def test_validation_rejects_invalid_port(tmp_path: Path) -> None:
    """A proxy port outside 1–65535 raises ProxyValidationError."""
    service = _make_service(tmp_path)

    with pytest.raises(ProxyValidationError):
        service.save_proxy(ProxyDefinition(id="", name="X", type=ProxyType.HTTP, host="h.example.com", port=0))

    with pytest.raises(ProxyValidationError):
        service.save_proxy(ProxyDefinition(id="", name="Y", type=ProxyType.HTTP, host="h.example.com", port=99999))


# ---------------------------------------------------------------------------
# 6. Clearing credentials
# ---------------------------------------------------------------------------


def test_clearing_credentials_removes_them_from_store(tmp_path: Path) -> None:
    """Using clear_credentials=True removes stored credentials and unsets credential_ref."""
    store = MemorySecretStore()
    service = ProxyService(store, config_dir=tmp_path)

    saved = service.save_proxy(
        _http_proxy(),
        credentials=ProxyCredentials(username="bob", password="hunter2"),
    )
    assert saved.credential_ref is not None

    cleared = service.save_proxy(
        ProxyDefinition(
            id=saved.id,
            name=saved.name,
            type=saved.type,
            host=saved.host,
            port=saved.port,
            credential_ref=saved.credential_ref,
        ),
        clear_credentials=True,
    )

    assert cleared.credential_ref is None
    assert store.load_proxy_credentials(saved.credential_ref or "") is None
    assert service.load_proxy_credentials(cleared.id) is None


# ---------------------------------------------------------------------------
# 7. Deleting a proxy also removes its credentials
# ---------------------------------------------------------------------------


def test_delete_proxy_removes_associated_credentials(tmp_path: Path) -> None:
    """Deleting a proxy that has credentials removes them from the secret store."""
    store = MemorySecretStore()
    service = ProxyService(store, config_dir=tmp_path)

    saved = service.save_proxy(
        _http_proxy(),
        credentials=ProxyCredentials(username="carol", password="pass123"),
    )
    cred_ref = saved.credential_ref
    assert cred_ref is not None
    assert store.load_proxy_credentials(cred_ref) is not None

    service.delete_proxy(saved.id)

    assert store.load_proxy_credentials(cred_ref) is None
    assert service.get_proxy(saved.id) is None


# ---------------------------------------------------------------------------
# 8. Updating a proxy preserves existing credentials when none are supplied
# ---------------------------------------------------------------------------


def test_update_proxy_preserves_credentials_when_not_changed(tmp_path: Path) -> None:
    """Updating proxy metadata without passing credentials keeps the existing credential_ref."""
    store = MemorySecretStore()
    service = ProxyService(store, config_dir=tmp_path)

    saved = service.save_proxy(
        _http_proxy(),
        credentials=ProxyCredentials(username="dave", password="secret99"),
    )
    original_ref = saved.credential_ref
    assert original_ref is not None

    # Update only the port — no credentials argument
    updated = service.save_proxy(
        ProxyDefinition(
            id=saved.id,
            name=saved.name,
            type=saved.type,
            host=saved.host,
            port=9090,
        )
    )

    assert updated.port == 9090
    assert updated.credential_ref == original_ref, "credential_ref must be preserved across metadata-only updates"

    loaded = service.load_proxy_credentials(updated.id)
    assert loaded is not None
    assert loaded.username == "dave"
