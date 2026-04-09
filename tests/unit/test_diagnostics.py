import json
from pathlib import Path

from core.diagnostics import DiagnosticsService
from core.models import (
    AppSettings,
    CapabilityState,
    DBusInterfaceValidation,
    DBusValidationReport,
    DiagnosticStatus,
    ImportSource,
    Profile,
)


class FakeReachability:
    def reachable_services(self) -> dict[str, bool]:
        return {"net.openvpn.v3.configuration": True}


class FakeCapabilities:
    def detect_capabilities(self) -> tuple[CapabilityState, ...]:
        return (
            CapabilityState(key="dco", available=False, reason="kernel module missing"),
            CapabilityState(key="posture", available=False, reason="posture helper missing"),
        )


class FakeLogs:
    def __init__(self) -> None:
        self.subscriber = None

    def recent_logs(
        self,
        session_id: str | None = None,
        limit: int = 200,
    ) -> tuple[str, ...]:
        return (
            "password=hunter2",
            "Authorization: Bearer topsecret",
            "openvpn://import-profile/https://vpn.example.com/tokenized",
        )[:limit]

    def subscribe_logs(self, session_id: str, callback):
        self.subscriber = callback
        return lambda: None


class FakeDBusValidation:
    def validate_surface(self) -> DBusValidationReport:
        return DBusValidationReport(
            status=DiagnosticStatus.FAIL,
            summary="Live D-Bus validation found mismatches: Session object",
            interfaces=(
                DBusInterfaceValidation(
                    label="Session object",
                    service="net.openvpn.v3.sessions",
                    object_path="/net/openvpn/v3/sessions/session1",
                    interface="net.openvpn.v3.sessions",
                    status=DiagnosticStatus.FAIL,
                    detail="Missing expected signals: AttentionRequired",
                    missing_signals=("AttentionRequired",),
                ),
            ),
        )


def test_diagnostics_redacts_sensitive_values() -> None:
    service = DiagnosticsService(
        reachability_probe=FakeReachability(),
        capability_probe=FakeCapabilities(),
        log_source=FakeLogs(),
    )
    snapshot = service.build_snapshot(profiles=(), settings=AppSettings())

    assert snapshot.recent_logs[0] == "password=<redacted>"
    assert "topsecret" not in snapshot.recent_logs[1]
    assert snapshot.recent_logs[2] == "openvpn://import-profile/redacted"


def test_diagnostics_live_log_stream_redacts_and_appends() -> None:
    logs = FakeLogs()
    service = DiagnosticsService(
        reachability_probe=FakeReachability(),
        capability_probe=FakeCapabilities(),
        log_source=logs,
    )
    updates: list[tuple[str, ...]] = []

    unsubscribe = service.subscribe_live_logs(
        session_id="session-1",
        callback=updates.append,
        limit=4,
    )

    assert updates[0][0] == "password=<redacted>"
    assert logs.subscriber is not None

    logs.subscriber("Authorization: Bearer anothersecret")

    assert "anothersecret" not in updates[-1][-1]
    assert updates[-1][-1] == "Authorization: Bearer <redacted>"
    unsubscribe()


def test_diagnostics_builds_environment_checks_and_troubleshooting() -> None:
    service = DiagnosticsService(
        reachability_probe=FakeReachability(),
        capability_probe=FakeCapabilities(),
        log_source=FakeLogs(),
        environment={},
        path_exists=lambda path: False,
        command_exists=lambda _name: False,
    )

    snapshot = service.build_snapshot(
        profiles=(),
        settings=AppSettings(local_dns=False, dco=True),
    )

    checks = {item.key: item for item in snapshot.environment_checks}
    assert checks["session_bus"].status is DiagnosticStatus.WARN
    assert checks["resolver_support"].status is DiagnosticStatus.WARN
    assert checks["posture_capability"].detail == "posture helper missing"
    assert checks["dbus_surface_validation"].status is DiagnosticStatus.INFO

    troubleshooting = {item.key: item for item in snapshot.troubleshooting_items}
    assert troubleshooting["dco_requested_but_unavailable"].status is DiagnosticStatus.WARN
    assert troubleshooting["resolver_support_missing"].status is DiagnosticStatus.WARN
    assert troubleshooting["posture_unavailable"].status is DiagnosticStatus.INFO
    assert troubleshooting["dbus_surface_unvalidated"].status is DiagnosticStatus.INFO

    workflows = {item.key: item for item in snapshot.guided_workflows}
    assert workflows["restore_session_bus"].status is DiagnosticStatus.WARN
    assert workflows["repair_dns_scope"].status is DiagnosticStatus.WARN
    assert workflows["prepare_posture_support"].status is DiagnosticStatus.INFO
    assert workflows["validate_dbus_surface"].status is DiagnosticStatus.INFO
    assert workflows["resolve_dco_gap"].steps[0].title == "Decide whether DCO is required for this machine"


def test_diagnostics_surfaces_dbus_validation_results() -> None:
    service = DiagnosticsService(
        reachability_probe=FakeReachability(),
        capability_probe=FakeCapabilities(),
        log_source=FakeLogs(),
        dbus_validation_probe=FakeDBusValidation(),
    )

    snapshot = service.build_snapshot(profiles=(), settings=AppSettings())

    checks = {item.key: item for item in snapshot.environment_checks}
    assert checks["dbus_surface_validation"].status is DiagnosticStatus.FAIL
    troubleshooting = {item.key: item for item in snapshot.troubleshooting_items}
    assert troubleshooting["dbus_surface_mismatch"].status is DiagnosticStatus.FAIL
    assert snapshot.dbus_validation is not None
    assert snapshot.dbus_validation.interfaces[0].missing_signals == ("AttentionRequired",)


def test_export_support_bundle_excludes_token_metadata(tmp_path: Path) -> None:
    service = DiagnosticsService(
        reachability_probe=FakeReachability(),
        capability_probe=FakeCapabilities(),
        log_source=FakeLogs(),
    )
    snapshot = service.build_snapshot(
        profiles=(
            Profile(
                id="profile-1",
                name="Demo",
                source=ImportSource.URL,
                metadata={"token_url": "sensitive", "canonical_url": "https://vpn.example.com/profile.ovpn"},
            ),
        ),
        settings=AppSettings(),
    )

    bundle = service.export_support_bundle(tmp_path / "support.json", snapshot)
    payload = json.loads(bundle.read_text(encoding="utf-8"))

    assert "token_url" not in payload["profiles"][0]["metadata"]
    assert "environment_checks" in payload
    assert "troubleshooting_items" in payload
    assert "guided_workflows" in payload
