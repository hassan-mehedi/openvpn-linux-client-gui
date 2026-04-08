from core.models import AttentionFieldType, AttentionRequest, ProxyCredentials
from core.secrets import MemorySecretStore, ProfileSecretsService, saved_password_request_id


def test_profile_secrets_service_persists_password_and_proxy_credentials() -> None:
    store = MemorySecretStore()
    service = ProfileSecretsService(store)

    service.save_password("profile-1", "secret")
    store.store_proxy_credentials(
        "proxy:office",
        ProxyCredentials(username="alice", password="proxy-secret"),
    )

    assert service.saved_state("profile-1").password_saved is True
    assert service.load_password("profile-1") == "secret"
    assert store.load_proxy_credentials("proxy:office") == ProxyCredentials(
        username="alice",
        password="proxy-secret",
    )


def test_saved_password_request_id_selects_single_password_prompt() -> None:
    request = AttentionRequest(
        session_id="session-1",
        field_id="password",
        label="Password",
        field_type=AttentionFieldType.SECRET,
        secret=True,
    )

    assert saved_password_request_id((request,)) == "password"


def test_saved_password_request_id_rejects_multiple_secret_prompts() -> None:
    requests = (
        AttentionRequest(
            session_id="session-1",
            field_id="password",
            label="Password",
            field_type=AttentionFieldType.SECRET,
            secret=True,
        ),
        AttentionRequest(
            session_id="session-1",
            field_id="challenge",
            label="Challenge password",
            field_type=AttentionFieldType.SECRET,
            secret=True,
        ),
    )

    assert saved_password_request_id(requests) is None
