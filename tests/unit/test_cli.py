import json
from pathlib import Path
from types import SimpleNamespace

from cli.main import main
from core.models import (
    AppSettings,
    DBusInterfaceValidation,
    DBusValidationReport,
    DiagnosticCheck,
    DiagnosticStatus,
    DiagnosticWorkflow,
    DiagnosticWorkflowStep,
    DiagnosticsSnapshot,
    ImportPreview,
    ImportProfileDetails,
    ImportSource,
    Profile,
    ProxyDefinition,
    ProxyType,
    SessionDescriptor,
    SessionPhase,
)
from core.session_manager import SessionSnapshot


class FakeProfileCatalog:
    def __init__(self) -> None:
        self.profiles = [
            Profile(
                id="profile-1",
                name="Office VPN",
                source=ImportSource.URL,
                metadata={"canonical_url": "https://vpn.example.com/profile.ovpn"},
            )
        ]
        self.renamed: tuple[str, str] | None = None

    def list_profiles(self, search: str = ""):
        return SimpleNamespace(profiles=tuple(self.profiles), search=search)

    def get_profile(self, profile_id: str) -> Profile | None:
        return next((item for item in self.profiles if item.id == profile_id), None)

    def preview_file_import(self, path: Path) -> ImportPreview:
        return ImportPreview(
            name=path.name,
            source=ImportSource.FILE,
            canonical_location=str(path),
            redacted_location=str(path),
            details=ImportProfileDetails(profile_name=path.name),
        )

    def preview_url_import(self, url: str) -> ImportPreview:
        return ImportPreview(
            name="download",
            source=ImportSource.URL,
            canonical_location=url,
            redacted_location="https://vpn.example.com/download?redacted",
            duplicate_profile_id="profile-1",
            duplicate_profile_name="Office VPN",
            duplicate_reason="Matching import URL",
            warnings=("Sensitive query parameters are redacted in previews and support bundles.",),
            details=ImportProfileDetails(
                profile_name="download",
                server_hostname="vpn.example.com",
                server_locked=True,
            ),
        )

    def preview_token_url_import(self, token_url: str) -> ImportPreview:
        return self.preview_url_import(token_url)

    def import_file(self, path: Path, *, profile_name: str | None = None) -> Profile:
        return Profile(
            id="profile-2",
            name=profile_name or path.name,
            source=ImportSource.FILE,
        )

    def import_url(self, url: str, *, profile_name: str | None = None) -> Profile:
        return Profile(
            id="profile-3",
            name=profile_name or "download",
            source=ImportSource.URL,
        )

    def import_token_url(self, url: str, *, profile_name: str | None = None) -> Profile:
        return self.import_url(url, profile_name=profile_name)

    def rename_profile(self, profile_id: str, profile_name: str) -> None:
        self.renamed = (profile_id, profile_name)

    def assign_proxy(self, profile_id: str, proxy_id: str | None) -> None:
        profile = self.get_profile(profile_id)
        if profile is not None:
            profile.assigned_proxy_id = proxy_id

    def clear_proxy_assignments(self, proxy_id: str) -> None:
        for profile in self.profiles:
            if profile.assigned_proxy_id == proxy_id:
                profile.assigned_proxy_id = None

    def delete_profile(self, profile_id: str) -> None:
        self.profiles = [item for item in self.profiles if item.id != profile_id]


class FakeSessionBackend:
    def __init__(self) -> None:
        self.session = SessionDescriptor(
            id="session-1",
            profile_id="profile-1",
            state=SessionPhase.CONNECTED,
            status_message="Connected",
        )

    def list_sessions(self) -> tuple[SessionDescriptor, ...]:
        return (self.session,)

    def get_session_status(self, session_id: str) -> SessionDescriptor:
        assert session_id == self.session.id
        return self.session

    def disconnect(self, session_id: str) -> SessionDescriptor:
        assert session_id == self.session.id
        return SessionDescriptor(
            id=session_id,
            profile_id=self.session.profile_id,
            state=SessionPhase.IDLE,
            status_message="Disconnected",
        )

    def pause(self, session_id: str) -> SessionDescriptor:
        assert session_id == self.session.id
        return SessionDescriptor(
            id=session_id,
            profile_id=self.session.profile_id,
            state=SessionPhase.PAUSED,
            status_message="Paused",
        )

    def resume(self, session_id: str) -> SessionDescriptor:
        assert session_id == self.session.id
        return self.session

    def restart(self, session_id: str) -> SessionDescriptor:
        assert session_id == self.session.id
        return SessionDescriptor(
            id=session_id,
            profile_id=self.session.profile_id,
            state=SessionPhase.RECONNECTING,
            status_message="Restarting",
        )


class FakeLifecycle:
    def connect(self, profile_id: str) -> SessionSnapshot:
        session = SessionDescriptor(
            id="session-1",
            profile_id=profile_id,
            state=SessionPhase.CONNECTING,
            status_message="Connecting",
        )
        return SessionSnapshot(
            state=SessionPhase.CONNECTING,
            selected_profile_id=profile_id,
            active_session=session,
            attention_requests=(),
            last_error=None,
        )


class FakeSettings:
    def __init__(self, tmp_path: Path) -> None:
        self.current = AppSettings(connection_timeout=45)
        self.settings_path = tmp_path / "settings.json"

    def load(self) -> AppSettings:
        return self.current

    def save(self, settings: AppSettings) -> AppSettings:
        self.current = settings
        return settings


class FakeProxies:
    def __init__(self) -> None:
        self.proxies = (
            ProxyDefinition(
                id="proxy-1",
                name="Office Proxy",
                type=ProxyType.HTTP,
                host="proxy.example.com",
                port=8080,
            ),
        )

    def list_proxies(self) -> tuple[ProxyDefinition, ...]:
        return self.proxies

    def get_proxy(self, proxy_id: str) -> ProxyDefinition | None:
        return next((item for item in self.proxies if item.id == proxy_id), None)

    def save_proxy(self, proxy: ProxyDefinition, credentials=None) -> ProxyDefinition:
        return proxy

    def delete_proxy(self, proxy_id: str) -> None:
        self.proxies = tuple(item for item in self.proxies if item.id != proxy_id)


class FakeDiagnostics:
    def build_snapshot(
        self,
        *,
        profiles,
        settings,
        session_id=None,
        recent_log_limit=200,
    ) -> DiagnosticsSnapshot:
        return DiagnosticsSnapshot(
            app_version="0.1.0",
            os_release="Test Linux",
            kernel="6.8.0",
            desktop_environment="GNOME",
            reachable_services={"net.openvpn.v3.configuration": True},
            capabilities=(),
            environment_checks=(
                DiagnosticCheck(
                    key="session_bus",
                    label="Session D-Bus environment",
                    status=DiagnosticStatus.PASS,
                    detail="Looks good.",
                ),
            ),
            troubleshooting_items=(
                DiagnosticCheck(
                    key="resolver",
                    label="Resolver integration",
                    status=DiagnosticStatus.WARN,
                    detail="systemd-resolved missing",
                ),
            ),
            guided_workflows=(
                DiagnosticWorkflow(
                    key="repair_dns_scope",
                    label="Repair VPN DNS handling",
                    status=DiagnosticStatus.WARN,
                    summary="Resolver support is missing.",
                    steps=(
                        DiagnosticWorkflowStep(
                            title="Use local DNS",
                            detail="Avoid the resolver dependency.",
                        ),
                    ),
                ),
            ),
            recent_logs=tuple(f"log-{index}" for index in range(min(recent_log_limit, 2))),
            profiles=profiles,
            settings=settings,
        )

    def export_support_bundle(self, target: Path, snapshot: DiagnosticsSnapshot) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"guided_workflows": len(snapshot.guided_workflows)}) + "\n",
            encoding="utf-8",
        )
        return target


class FakeIntrospection:
    def validate_surface(self) -> DBusValidationReport:
        return DBusValidationReport(
            status=DiagnosticStatus.PASS,
            summary="Live D-Bus validation matched the current adapter surface.",
            interfaces=(
                DBusInterfaceValidation(
                    label="Configuration manager",
                    service="net.openvpn.v3.configuration",
                    object_path="/net/openvpn/v3/configuration",
                    interface="net.openvpn.v3.configuration",
                    status=DiagnosticStatus.PASS,
                    detail="Validated against live introspection data.",
                    methods=("FetchAvailableConfigs", "Import", "LookupConfigName"),
                ),
            ),
        )


def _services(tmp_path: Path):
    return SimpleNamespace(
        profile_catalog=FakeProfileCatalog(),
        session=FakeSessionBackend(),
        session_lifecycle=FakeLifecycle(),
        settings=FakeSettings(tmp_path),
        proxies=FakeProxies(),
        diagnostics=FakeDiagnostics(),
        introspection=FakeIntrospection(),
    )


def test_profiles_preview_url_outputs_richer_preview_json(tmp_path: Path, capsys) -> None:
    result = main(
        ["profiles", "preview-url", "https://vpn.example.com/download?token=abc"],
        services=_services(tmp_path),
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["duplicate_profile_name"] == "Office VPN"
    assert payload["duplicate_reason"] == "Matching import URL"
    assert payload["details"]["server_hostname"] == "vpn.example.com"


def test_sessions_list_and_status_commands_support_json(tmp_path: Path, capsys) -> None:
    services = _services(tmp_path)

    result = main(["sessions", "list", "--json"], services=services)
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["state"] == "connected"

    result = main(["sessions", "status", "session-1", "--json"], services=services)
    assert result == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["id"] == "session-1"


def test_settings_get_and_config_show_commands(tmp_path: Path, capsys) -> None:
    services = _services(tmp_path)

    result = main(["settings", "get", "connection_timeout"], services=services)
    assert result == 0
    assert capsys.readouterr().out.strip() == "45"

    result = main(["config", "show"], services=services)
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["settings_path"].endswith("settings.json")
    assert payload["profiles_path"].endswith("profiles.json")


def test_doctor_workflows_and_export_commands(tmp_path: Path, capsys) -> None:
    services = _services(tmp_path)
    export_target = tmp_path / "support.json"

    result = main(["doctor", "workflows"], services=services)
    assert result == 0
    workflows = json.loads(capsys.readouterr().out)
    assert workflows[0]["key"] == "repair_dns_scope"

    result = main(["doctor", "export", str(export_target)], services=services)
    assert result == 0
    assert Path(capsys.readouterr().out.strip()) == export_target
    assert export_target.exists()


def test_doctor_dbus_surface_command(tmp_path: Path, capsys) -> None:
    services = _services(tmp_path)

    result = main(["doctor", "dbus-surface"], services=services)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "pass"
    assert payload["interfaces"][0]["label"] == "Configuration manager"
