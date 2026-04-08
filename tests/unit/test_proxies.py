import json
from pathlib import Path

import pytest

from core.models import ProxyCredentials, ProxyDefinition, ProxyType
from core.proxies import ProxyService, ProxyValidationError
from core.secrets import MemorySecretStore


def test_proxy_save_persists_metadata_without_plaintext_secret(tmp_path: Path) -> None:
    store = MemorySecretStore()
    service = ProxyService(store, config_dir=tmp_path)
    proxy = ProxyDefinition(
        id="",
        name="Office",
        type=ProxyType.HTTP,
        host="proxy.example.com",
        port=8080,
    )

    saved = service.save_proxy(
        proxy,
        credentials=ProxyCredentials(username="alice", password="secret"),
    )

    payload = json.loads((tmp_path / "proxies.json").read_text(encoding="utf-8"))
    assert payload[0]["credential_ref"] == saved.credential_ref
    assert "secret" not in json.dumps(payload)
    assert store.load_proxy_credentials(saved.credential_ref or "") is not None


def test_proxy_validation_rejects_invalid_port(tmp_path: Path) -> None:
    service = ProxyService(MemorySecretStore(), config_dir=tmp_path)
    invalid = ProxyDefinition(
        id="",
        name="Broken",
        type=ProxyType.SOCKS5,
        host="proxy.example.com",
        port=70000,
    )

    with pytest.raises(ProxyValidationError):
        service.save_proxy(invalid)


def test_proxy_validation_rejects_duplicate_names(tmp_path: Path) -> None:
    service = ProxyService(MemorySecretStore(), config_dir=tmp_path)
    first = ProxyDefinition(
        id="",
        name="Office",
        type=ProxyType.HTTP,
        host="proxy-a.example.com",
        port=8080,
    )
    second = ProxyDefinition(
        id="",
        name="office",
        type=ProxyType.SOCKS5,
        host="proxy-b.example.com",
        port=1080,
    )

    service.save_proxy(first)

    with pytest.raises(ProxyValidationError):
        service.save_proxy(second)


def test_proxy_save_can_clear_saved_credentials(tmp_path: Path) -> None:
    store = MemorySecretStore()
    service = ProxyService(store, config_dir=tmp_path)
    proxy = service.save_proxy(
        ProxyDefinition(
            id="",
            name="Office",
            type=ProxyType.HTTP,
            host="proxy.example.com",
            port=8080,
        ),
        credentials=ProxyCredentials(username="alice", password="secret"),
    )

    cleared = service.save_proxy(
        ProxyDefinition(
            id=proxy.id,
            name="Office",
            type=ProxyType.HTTP,
            host="proxy.example.com",
            port=8080,
            credential_ref=proxy.credential_ref,
        ),
        clear_credentials=True,
    )

    assert cleared.credential_ref is None
    assert store.load_proxy_credentials(proxy.credential_ref or "") is None


def test_proxy_load_credentials_returns_saved_value(tmp_path: Path) -> None:
    service = ProxyService(MemorySecretStore(), config_dir=tmp_path)
    saved = service.save_proxy(
        ProxyDefinition(
            id="",
            name="Office",
            type=ProxyType.HTTP,
            host="proxy.example.com",
            port=8080,
        ),
        credentials=ProxyCredentials(username="alice", password="secret"),
    )

    credentials = service.load_proxy_credentials(saved.id)

    assert credentials == ProxyCredentials(username="alice", password="secret")
