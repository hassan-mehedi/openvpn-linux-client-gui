import json
from pathlib import Path

from core.diagnostics import DiagnosticsService
from core.models import AppSettings, CapabilityState, ImportSource, Profile


class FakeReachability:
    def reachable_services(self) -> dict[str, bool]:
        return {"net.openvpn.v3.configuration": True}


class FakeCapabilities:
    def detect_capabilities(self) -> tuple[CapabilityState, ...]:
        return (CapabilityState(key="dco", available=False, reason="kernel module missing"),)


class FakeLogs:
    def recent_logs(self, limit: int = 200) -> tuple[str, ...]:
        return (
            "password=hunter2",
            "Authorization: Bearer topsecret",
            "openvpn://import-profile/https://vpn.example.com/tokenized",
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

