from core.connection_preparation import (
    ConnectionPreparationError,
    ConnectionPreparationService,
)
from core.models import (
    AppSettings,
    ImportSource,
    Profile,
    ProxyCredentials,
    ProxyDefinition,
    ProxyType,
)


class FakeSettingsBackend:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or AppSettings()

    def load(self) -> AppSettings:
        return self.settings


class FakeProfileCatalog:
    def __init__(self, profile: Profile | None) -> None:
        self.profile = profile

    def get_profile(self, profile_id: str) -> Profile | None:
        if self.profile is None or self.profile.id != profile_id:
            return None
        return self.profile


class FakeProxyBackend:
    def __init__(
        self,
        proxy: ProxyDefinition | None = None,
        credentials: ProxyCredentials | None = None,
    ) -> None:
        self.proxy = proxy
        self.credentials = credentials

    def get_proxy(self, proxy_id: str) -> ProxyDefinition | None:
        if self.proxy is None or self.proxy.id != proxy_id:
            return None
        return self.proxy

    def load_proxy_credentials(self, proxy_id: str) -> ProxyCredentials | None:
        if self.proxy is None or self.proxy.id != proxy_id:
            return None
        return self.credentials


class FakeConfigurationBackend:
    def __init__(self) -> None:
        self.settings_calls: list[tuple[str, AppSettings]] = []
        self.proxy_calls: list[
            tuple[str, ProxyDefinition | None, ProxyCredentials | None]
        ] = []

    def apply_connection_settings(self, profile_id: str, settings: AppSettings) -> None:
        self.settings_calls.append((profile_id, settings))

    def apply_proxy_assignment(
        self,
        profile_id: str,
        proxy: ProxyDefinition | None,
        credentials: ProxyCredentials | None,
    ) -> None:
        self.proxy_calls.append((profile_id, proxy, credentials))


def test_connection_preparation_applies_settings_and_assigned_proxy() -> None:
    proxy = ProxyDefinition(
        id="proxy-1",
        name="Office",
        type=ProxyType.HTTP,
        host="proxy.example.com",
        port=8080,
        credential_ref="proxy:proxy-1",
    )
    profile = Profile(
        id="profile-1",
        name="Demo",
        source=ImportSource.FILE,
        assigned_proxy_id=proxy.id,
    )
    configuration = FakeConfigurationBackend()
    service = ConnectionPreparationService(
        FakeSettingsBackend(AppSettings(dco=True)),
        FakeProfileCatalog(profile),
        FakeProxyBackend(
            proxy,
            ProxyCredentials(username="alice", password="secret"),
        ),
        configuration,
    )

    service.prepare_profile("profile-1")

    assert configuration.settings_calls == [("profile-1", AppSettings(dco=True))]
    assert configuration.proxy_calls == [
        (
            "profile-1",
            proxy,
            ProxyCredentials(username="alice", password="secret"),
        )
    ]


def test_connection_preparation_clears_proxy_when_profile_has_no_assignment() -> None:
    configuration = FakeConfigurationBackend()
    service = ConnectionPreparationService(
        FakeSettingsBackend(),
        FakeProfileCatalog(
            Profile(id="profile-1", name="Demo", source=ImportSource.FILE)
        ),
        FakeProxyBackend(),
        configuration,
    )

    service.prepare_profile("profile-1")

    assert configuration.proxy_calls == [("profile-1", None, None)]


def test_connection_preparation_rejects_missing_proxy_credentials() -> None:
    proxy = ProxyDefinition(
        id="proxy-1",
        name="Office",
        type=ProxyType.HTTP,
        host="proxy.example.com",
        port=8080,
        credential_ref="proxy:proxy-1",
    )
    profile = Profile(
        id="profile-1",
        name="Demo",
        source=ImportSource.FILE,
        assigned_proxy_id=proxy.id,
    )
    service = ConnectionPreparationService(
        FakeSettingsBackend(),
        FakeProfileCatalog(profile),
        FakeProxyBackend(proxy),
        FakeConfigurationBackend(),
    )

    try:
        service.prepare_profile("profile-1")
    except ConnectionPreparationError as exc:
        assert "Stored credentials are unavailable" in str(exc)
    else:  # pragma: no cover - defensive branch for a missing exception
        raise AssertionError("Expected missing proxy credentials to fail.")
