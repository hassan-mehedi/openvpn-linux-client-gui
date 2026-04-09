"""Shared live service construction."""

from __future__ import annotations

from dataclasses import dataclass

from core.app_state import AppStateService
from core.autostart import AutostartService
from core.catalog import ProfileCatalogService
from core.connection_preparation import ConnectionPreparationService
from core.diagnostics import DiagnosticsService
from core.onboarding import OnboardingService
from core.proxies import ProxyService
from core.secrets import ProfileSecretsService, create_secret_store
from core.session_manager import SessionLifecycleService
from core.settings import SettingsService
from core.telemetry import SessionTelemetryService
from openvpn3.attention_service import AttentionService
from openvpn3.backend_service import BackendService
from openvpn3.configuration_service import ConfigurationService
from openvpn3.dbus_client import DBusClient, create_default_transport
from openvpn3.introspection_service import IntrospectionService
from openvpn3.log_service import LogService
from openvpn3.netcfg_service import NetCfgService
from openvpn3.session_service import SessionService


class _DiagnosticLogSource:
    def __init__(self, log_service: LogService) -> None:
        self._log_service = log_service

    def recent_logs(self, session_id: str | None = None, limit: int = 200) -> tuple[str, ...]:
        return self._log_service.recent_logs(session_id=session_id, limit=limit)

    def subscribe_logs(
        self,
        session_id: str,
        callback,
    ):
        return self._log_service.subscribe_logs(session_id, callback)


@dataclass(slots=True)
class ServiceContainer:
    configuration: ConfigurationService
    session: SessionService
    attention: AttentionService
    log: LogService
    backend: BackendService
    netcfg: NetCfgService
    introspection: IntrospectionService
    onboarding: OnboardingService
    settings: SettingsService
    proxies: ProxyService
    profile_secrets: ProfileSecretsService
    telemetry: SessionTelemetryService
    diagnostics: DiagnosticsService
    profile_catalog: ProfileCatalogService
    session_lifecycle: SessionLifecycleService
    app_state: AppStateService
    autostart: AutostartService


def build_live_services() -> ServiceContainer:
    client = DBusClient(create_default_transport())
    configuration = ConfigurationService(client)
    session = SessionService(
        client,
        profile_resolver=configuration.resolve_object_path,
        profile_id_from_path=configuration.resolve_profile_id,
    )
    attention = AttentionService(client, session_resolver=session.resolve_object_path)
    log = LogService(client, session_resolver=session.resolve_object_path)
    backend = BackendService(client)
    netcfg = NetCfgService(client)
    introspection = IntrospectionService(client)
    onboarding = OnboardingService(configuration)
    settings = SettingsService()
    secret_store = create_secret_store()
    proxies = ProxyService(secret_store)
    profile_secrets = ProfileSecretsService(secret_store)
    telemetry = SessionTelemetryService(session)
    diagnostics = DiagnosticsService(
        reachability_probe=backend,
        capability_probe=netcfg,
        log_source=_DiagnosticLogSource(log),
        dbus_validation_probe=introspection,
    )
    profile_catalog = ProfileCatalogService(
        configuration,
        onboarding,
        proxy_backend=proxies,
    )
    connection_preparation = ConnectionPreparationService(
        settings,
        profile_catalog,
        proxies,
        configuration,
    )
    app_state = AppStateService()
    autostart = AutostartService()
    session_lifecycle = SessionLifecycleService(
        session,
        attention,
        settings_backend=settings,
        profile_credentials=profile_secrets,
        connection_preparation=connection_preparation,
        app_state=app_state,
    )
    return ServiceContainer(
        configuration=configuration,
        session=session,
        attention=attention,
        log=log,
        backend=backend,
        netcfg=netcfg,
        introspection=introspection,
        onboarding=onboarding,
        settings=settings,
        proxies=proxies,
        profile_secrets=profile_secrets,
        telemetry=telemetry,
        diagnostics=diagnostics,
        profile_catalog=profile_catalog,
        session_lifecycle=session_lifecycle,
        app_state=app_state,
        autostart=autostart,
    )
