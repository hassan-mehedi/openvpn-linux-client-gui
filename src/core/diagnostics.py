"""Diagnostics and support bundle logic."""

from __future__ import annotations

import json
import platform
import re
from pathlib import Path
from typing import Protocol

from core.models import AppSettings, CapabilityState, DiagnosticsSnapshot, Profile


class ReachabilityProbe(Protocol):
    def reachable_services(self) -> dict[str, bool]:
        """Return reachability per D-Bus service."""


class CapabilityProbe(Protocol):
    def detect_capabilities(self) -> tuple[CapabilityState, ...]:
        """Return feature capability states."""


class LogSource(Protocol):
    def recent_logs(self, limit: int = 200) -> tuple[str, ...]:
        """Return recent log lines."""


class DiagnosticsService:
    _SECRET_PATTERNS = (
        re.compile(r"(?i)(password|passphrase|token)=([^&\s]+)"),
        re.compile(r"(?i)(authorization:\s*bearer\s+)(\S+)"),
        re.compile(r"openvpn://import-profile/\S+"),
    )

    def __init__(
        self,
        *,
        reachability_probe: ReachabilityProbe,
        capability_probe: CapabilityProbe,
        log_source: LogSource,
        app_version: str = "0.1.0",
        desktop_environment: str | None = None,
        os_release: str | None = None,
        kernel: str | None = None,
    ) -> None:
        self._reachability_probe = reachability_probe
        self._capability_probe = capability_probe
        self._log_source = log_source
        self._app_version = app_version
        self._desktop_environment = desktop_environment or "unknown"
        self._os_release = os_release or platform.platform()
        self._kernel = kernel or platform.release()

    def build_snapshot(
        self,
        *,
        profiles: tuple[Profile, ...],
        settings: AppSettings,
        recent_log_limit: int = 200,
    ) -> DiagnosticsSnapshot:
        logs = tuple(
            self.redact_sensitive_values(line)
            for line in self._log_source.recent_logs(limit=recent_log_limit)
        )
        return DiagnosticsSnapshot(
            app_version=self._app_version,
            os_release=self._os_release,
            kernel=self._kernel,
            desktop_environment=self._desktop_environment,
            reachable_services=self._reachability_probe.reachable_services(),
            capabilities=self._capability_probe.detect_capabilities(),
            recent_logs=logs,
            profiles=profiles,
            settings=settings,
        )

    def export_support_bundle(self, target: Path, snapshot: DiagnosticsSnapshot) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "app_version": snapshot.app_version,
            "os_release": snapshot.os_release,
            "kernel": snapshot.kernel,
            "desktop_environment": snapshot.desktop_environment,
            "reachable_services": snapshot.reachable_services,
            "capabilities": [
                {"key": item.key, "available": item.available, "reason": item.reason}
                for item in snapshot.capabilities
            ],
            "recent_logs": list(snapshot.recent_logs),
            "profiles": [
                {
                    "id": profile.id,
                    "name": profile.name,
                    "source": profile.source.value,
                    "assigned_proxy_id": profile.assigned_proxy_id,
                    "metadata": {
                        key: value
                        for key, value in profile.metadata.items()
                        if "token" not in key.lower()
                    },
                }
                for profile in snapshot.profiles
            ],
            "settings": snapshot.settings.to_mapping(),
        }
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return target

    def redact_sensitive_values(self, value: str) -> str:
        redacted = value
        for pattern in self._SECRET_PATTERNS:
            redacted = pattern.sub(self._replacement, redacted)
        return redacted

    @staticmethod
    def _replacement(match: re.Match[str]) -> str:
        if match.re.pattern.startswith("openvpn://"):
            return "openvpn://import-profile/redacted"
        if match.lastindex and match.lastindex >= 2:
            separator = "" if match.group(1).endswith(" ") else "="
            return f"{match.group(1)}{separator}<redacted>"
        return "<redacted>"
