"""Diagnostics and support bundle logic."""

from __future__ import annotations

import json
import os
import platform
import re
from pathlib import Path
from shutil import which
from typing import Callable, Mapping, Protocol

from core.models import (
    AppSettings,
    CapabilityState,
    DBusValidationReport,
    DiagnosticCheck,
    DiagnosticStatus,
    DiagnosticWorkflow,
    DiagnosticWorkflowStep,
    DiagnosticsSnapshot,
    Profile,
)


class ReachabilityProbe(Protocol):
    def reachable_services(self) -> dict[str, bool]:
        """Return reachability per D-Bus service."""


class CapabilityProbe(Protocol):
    def detect_capabilities(self) -> tuple[CapabilityState, ...]:
        """Return feature capability states."""


class LogSource(Protocol):
    def recent_logs(self, session_id: str | None = None, limit: int = 200) -> tuple[str, ...]:
        """Return recent log lines."""

    def subscribe_logs(
        self,
        session_id: str,
        callback: Callable[[str], None],
    ) -> Callable[[], None]:
        """Subscribe to live log lines for a session."""


class DBusValidationProbe(Protocol):
    def validate_surface(self) -> DBusValidationReport:
        """Validate the live D-Bus adapter surface."""


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
        dbus_validation_probe: DBusValidationProbe | None = None,
        app_version: str = "0.1.0",
        desktop_environment: str | None = None,
        os_release: str | None = None,
        kernel: str | None = None,
        environment: Mapping[str, str] | None = None,
        path_exists: Callable[[Path], bool] | None = None,
        command_exists: Callable[[str], bool] | None = None,
    ) -> None:
        self._reachability_probe = reachability_probe
        self._capability_probe = capability_probe
        self._log_source = log_source
        self._dbus_validation_probe = dbus_validation_probe
        self._app_version = app_version
        self._desktop_environment = desktop_environment or "unknown"
        self._os_release = os_release or platform.platform()
        self._kernel = kernel or platform.release()
        self._environment = os.environ if environment is None else environment
        self._path_exists = path_exists or Path.exists
        self._command_exists = command_exists or (lambda name: which(name) is not None)

    def build_snapshot(
        self,
        *,
        profiles: tuple[Profile, ...],
        settings: AppSettings,
        session_id: str | None = None,
        recent_log_limit: int = 200,
    ) -> DiagnosticsSnapshot:
        reachable_services = self._reachability_probe.reachable_services()
        capabilities = self._capability_probe.detect_capabilities()
        dbus_validation = (
            self._dbus_validation_probe.validate_surface()
            if self._dbus_validation_probe is not None
            else None
        )
        logs = tuple(
            self.redact_sensitive_values(line)
            for line in self._log_source.recent_logs(
                session_id=session_id,
                limit=recent_log_limit,
            )
        )
        environment_checks = self._build_environment_checks(
            settings=settings,
            capabilities=capabilities,
            reachable_services=reachable_services,
            dbus_validation=dbus_validation,
        )
        troubleshooting_items = self._build_troubleshooting_items(
            settings=settings,
            capabilities=capabilities,
            reachable_services=reachable_services,
            checks=environment_checks,
            dbus_validation=dbus_validation,
        )
        return DiagnosticsSnapshot(
            app_version=self._app_version,
            os_release=self._os_release,
            kernel=self._kernel,
            desktop_environment=self._desktop_environment,
            reachable_services=reachable_services,
            capabilities=capabilities,
            environment_checks=environment_checks,
            troubleshooting_items=troubleshooting_items,
            guided_workflows=self._build_guided_workflows(
                settings=settings,
                capabilities=capabilities,
                reachable_services=reachable_services,
                checks=environment_checks,
                troubleshooting_items=troubleshooting_items,
            ),
            recent_logs=logs,
            profiles=profiles,
            settings=settings,
            dbus_validation=dbus_validation,
        )

    def subscribe_live_logs(
        self,
        *,
        session_id: str | None,
        callback: Callable[[tuple[str, ...]], None],
        limit: int = 200,
    ) -> Callable[[], None]:
        if not session_id:
            callback(())
            return lambda: None

        buffered = list(
            self.redact_sensitive_values(line)
            for line in self._log_source.recent_logs(session_id=session_id, limit=limit)
        )[-limit:]
        callback(tuple(buffered))

        def on_log_line(line: str) -> None:
            redacted = self.redact_sensitive_values(line)
            buffered.append(redacted)
            del buffered[:-limit]
            callback(tuple(buffered))

        return self._log_source.subscribe_logs(session_id, on_log_line)

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
            "environment_checks": [
                {
                    "key": item.key,
                    "label": item.label,
                    "status": item.status.value,
                    "detail": item.detail,
                }
                for item in snapshot.environment_checks
            ],
            "troubleshooting_items": [
                {
                    "key": item.key,
                    "label": item.label,
                    "status": item.status.value,
                    "detail": item.detail,
                }
                for item in snapshot.troubleshooting_items
            ],
            "guided_workflows": [
                {
                    "key": workflow.key,
                    "label": workflow.label,
                    "status": workflow.status.value,
                    "summary": workflow.summary,
                    "steps": [
                        {"title": step.title, "detail": step.detail}
                        for step in workflow.steps
                    ],
                }
                for workflow in snapshot.guided_workflows
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
        if snapshot.dbus_validation is not None:
            payload["dbus_validation"] = _dbus_validation_payload(snapshot.dbus_validation)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return target

    def redact_sensitive_values(self, value: str) -> str:
        redacted = value
        for pattern in self._SECRET_PATTERNS:
            redacted = pattern.sub(self._replacement, redacted)
        return redacted

    def _build_environment_checks(
        self,
        *,
        settings: AppSettings,
        capabilities: tuple[CapabilityState, ...],
        reachable_services: dict[str, bool],
        dbus_validation: DBusValidationReport | None,
    ) -> tuple[DiagnosticCheck, ...]:
        capability_index = {item.key: item for item in capabilities}
        session_bus_address = self._environment.get("DBUS_SESSION_BUS_ADDRESS", "").strip()
        xdg_runtime_dir = self._environment.get("XDG_RUNTIME_DIR", "").strip()
        resolver_paths = (
            Path("/run/systemd/resolve"),
            Path("/run/systemd/resolve/stub-resolv.conf"),
        )
        resolver_available = any(self._path_exists(path) for path in resolver_paths)
        posture_helpers = (
            "openvpn3-addon-devposture",
            "openvpn3-dpc-openvpninc",
        )
        posture_helpers_available = all(self._command_exists(name) for name in posture_helpers)

        checks = [
            DiagnosticCheck(
                key="session_bus",
                label="Session D-Bus environment",
                status=(
                    DiagnosticStatus.PASS
                    if session_bus_address or xdg_runtime_dir
                    else DiagnosticStatus.WARN
                ),
                detail=(
                    "A desktop session bus is advertised for GTK and OpenVPN D-Bus traffic."
                    if session_bus_address or xdg_runtime_dir
                    else (
                        "No session bus environment was detected. Launch the desktop app inside a "
                        "graphical login session or a shell that exports the user D-Bus environment."
                    )
                ),
            ),
            DiagnosticCheck(
                key="service_activation",
                label="OpenVPN 3 service activation",
                status=(
                    DiagnosticStatus.PASS
                    if reachable_services and all(reachable_services.values())
                    else DiagnosticStatus.FAIL
                ),
                detail=(
                    "All required OpenVPN 3 D-Bus services responded."
                    if reachable_services and all(reachable_services.values())
                    else "One or more OpenVPN 3 D-Bus services could not be reached."
                ),
            ),
            DiagnosticCheck(
                key="resolver_support",
                label="Resolver integration",
                status=(
                    DiagnosticStatus.PASS
                    if settings.local_dns or resolver_available
                    else DiagnosticStatus.WARN
                ),
                detail=(
                    "Local DNS remains enabled, so no global resolver override is required."
                    if settings.local_dns
                    else (
                        "systemd-resolved integration was detected for global VPN DNS scope."
                        if resolver_available
                        else (
                            "Global VPN DNS scope was requested, but systemd-resolved support was "
                            "not detected on this machine."
                        )
                    )
                ),
            ),
            DiagnosticCheck(
                key="posture_prerequisites",
                label="Device posture prerequisites",
                status=(
                    DiagnosticStatus.PASS
                    if posture_helpers_available
                    else DiagnosticStatus.INFO
                ),
                detail=(
                    "Device posture helper components were detected on this host."
                    if posture_helpers_available
                    else (
                        "Posture helper components were not detected. Posture-aware access usually "
                        "needs the devposture and DPC helpers installed."
                    )
                ),
            ),
        ]

        posture_capability = capability_index.get("posture")
        if posture_capability is not None:
            checks.append(
                DiagnosticCheck(
                    key="posture_capability",
                    label="Device posture capability",
                    status=(
                        DiagnosticStatus.PASS
                        if posture_capability.available
                        else DiagnosticStatus.INFO
                    ),
                    detail=(
                        posture_capability.reason or "Capability detection completed."
                    ),
                )
            )

        if dbus_validation is None:
            checks.append(
                DiagnosticCheck(
                    key="dbus_surface_validation",
                    label="Live D-Bus surface validation",
                    status=DiagnosticStatus.INFO,
                    detail=(
                        "Live introspection validation has not been captured on this machine yet. "
                        "Run the CLI doctor D-Bus validation workflow before treating the adapters as production-validated."
                    ),
                )
            )
        else:
            checks.append(
                DiagnosticCheck(
                    key="dbus_surface_validation",
                    label="Live D-Bus surface validation",
                    status=dbus_validation.status,
                    detail=dbus_validation.summary,
                )
            )

        return tuple(checks)

    def _build_troubleshooting_items(
        self,
        *,
        settings: AppSettings,
        capabilities: tuple[CapabilityState, ...],
        reachable_services: dict[str, bool],
        checks: tuple[DiagnosticCheck, ...],
        dbus_validation: DBusValidationReport | None,
    ) -> tuple[DiagnosticCheck, ...]:
        items: list[DiagnosticCheck] = []
        unreachable = [name for name, reachable in reachable_services.items() if not reachable]
        if unreachable:
            items.append(
                DiagnosticCheck(
                    key="services_unreachable",
                    label="Restore OpenVPN 3 D-Bus services",
                    status=DiagnosticStatus.FAIL,
                    detail=(
                        "Unavailable services: "
                        + ", ".join(sorted(unreachable))
                        + ". Verify the OpenVPN 3 Linux packages are installed and that the user bus can activate them."
                    ),
                )
            )

        capability_index = {item.key: item for item in capabilities}
        dco_capability = capability_index.get("dco")
        if settings.dco and dco_capability is not None and not dco_capability.available:
            items.append(
                DiagnosticCheck(
                    key="dco_requested_but_unavailable",
                    label="Disable DCO or install the kernel module",
                    status=DiagnosticStatus.WARN,
                    detail=dco_capability.reason or "DCO was enabled in settings but is unavailable.",
                )
            )

        posture_capability = capability_index.get("posture")
        if posture_capability is not None and not posture_capability.available:
            items.append(
                DiagnosticCheck(
                    key="posture_unavailable",
                    label="Install posture prerequisites before enabling posture-aware access",
                    status=DiagnosticStatus.INFO,
                    detail=posture_capability.reason
                    or "Device posture support is not available on this machine.",
                )
            )

        resolver_check = next((item for item in checks if item.key == "resolver_support"), None)
        if resolver_check is not None and resolver_check.status is DiagnosticStatus.WARN:
            items.append(
                DiagnosticCheck(
                    key="resolver_support_missing",
                    label="Use local DNS or install resolver integration",
                    status=DiagnosticStatus.WARN,
                    detail=resolver_check.detail,
                )
            )

        dbus_validation_check = next(
            (item for item in checks if item.key == "dbus_surface_validation"),
            None,
        )
        if dbus_validation_check is not None and dbus_validation_check.status in {
            DiagnosticStatus.FAIL,
            DiagnosticStatus.WARN,
        }:
            items.append(
                DiagnosticCheck(
                    key="dbus_surface_mismatch",
                    label="Validate adapter assumptions against the live OpenVPN 3 D-Bus surface",
                    status=dbus_validation_check.status,
                    detail=dbus_validation_check.detail,
                )
            )
        elif dbus_validation is None:
            items.append(
                DiagnosticCheck(
                    key="dbus_surface_unvalidated",
                    label="Capture live D-Bus introspection before production rollout",
                    status=DiagnosticStatus.INFO,
                    detail=(
                        "The adapters still need a live introspection pass on a real OpenVPN 3 Linux installation."
                    ),
                )
            )

        if not items:
            items.append(
                DiagnosticCheck(
                    key="no_issues_detected",
                    label="No immediate environment issues detected",
                    status=DiagnosticStatus.PASS,
                    detail="Service reachability, capability checks, and current settings did not raise any obvious blockers.",
                )
            )
        return tuple(items)

    def _build_guided_workflows(
        self,
        *,
        settings: AppSettings,
        capabilities: tuple[CapabilityState, ...],
        reachable_services: dict[str, bool],
        checks: tuple[DiagnosticCheck, ...],
        troubleshooting_items: tuple[DiagnosticCheck, ...],
    ) -> tuple[DiagnosticWorkflow, ...]:
        workflows: list[DiagnosticWorkflow] = []
        check_index = {item.key: item for item in checks}
        item_index = {item.key: item for item in troubleshooting_items}
        capability_index = {item.key: item for item in capabilities}
        unreachable = tuple(
            name for name, reachable in sorted(reachable_services.items()) if not reachable
        )

        if unreachable:
            workflows.append(
                DiagnosticWorkflow(
                    key="recover_dbus_services",
                    label="Recover OpenVPN 3 D-Bus services",
                    status=DiagnosticStatus.FAIL,
                    summary=(
                        "One or more OpenVPN 3 services did not respond. Restore service activation first "
                        "before troubleshooting profile-specific failures."
                    ),
                    steps=(
                        DiagnosticWorkflowStep(
                            title="Verify the OpenVPN 3 Linux packages are installed",
                            detail=(
                                "Make sure the configuration, session, log, backend, and netcfg services are "
                                "present on the system and match the desktop app build."
                            ),
                        ),
                        DiagnosticWorkflowStep(
                            title="Launch the desktop app from a graphical login session",
                            detail=(
                                "OpenVPN 3 service activation depends on the user D-Bus environment. "
                                "A bare root shell or detached service session will usually fail here."
                            ),
                        ),
                        DiagnosticWorkflowStep(
                            title="Refresh diagnostics after service activation succeeds",
                            detail=(
                                "When all services become reachable, continue with connection or posture-specific "
                                "workflows instead of retrying blind."
                            ),
                        ),
                    ),
                )
            )

        session_bus_check = check_index.get("session_bus")
        if session_bus_check is not None and session_bus_check.status is DiagnosticStatus.WARN:
            workflows.append(
                DiagnosticWorkflow(
                    key="restore_session_bus",
                    label="Restore the desktop session bus",
                    status=DiagnosticStatus.WARN,
                    summary=session_bus_check.detail,
                    steps=(
                        DiagnosticWorkflowStep(
                            title="Use a user login session",
                            detail=(
                                "Start the GUI from the desktop session that owns the user bus rather than from a "
                                "minimal TTY, cron, or root shell."
                            ),
                        ),
                        DiagnosticWorkflowStep(
                            title="Confirm the bus environment is exported",
                            detail=(
                                "The process should see DBUS_SESSION_BUS_ADDRESS or a valid XDG_RUNTIME_DIR before "
                                "it tries to talk to OpenVPN 3 services."
                            ),
                        ),
                    ),
                )
            )

        resolver_check = check_index.get("resolver_support")
        if resolver_check is not None and resolver_check.status is DiagnosticStatus.WARN:
            workflows.append(
                DiagnosticWorkflow(
                    key="repair_dns_scope",
                    label="Repair VPN DNS handling",
                    status=DiagnosticStatus.WARN,
                    summary=resolver_check.detail,
                    steps=(
                        DiagnosticWorkflowStep(
                            title="Switch to local DNS if global DNS is not required",
                            detail=(
                                "Keeping local DNS enabled avoids the resolver integration requirement and matches "
                                "the least invasive Linux setup."
                            ),
                        ),
                        DiagnosticWorkflowStep(
                            title="Install or enable resolver integration",
                            detail=(
                                "If global VPN DNS scope is required, make sure systemd-resolved support is "
                                "available before retrying the connection."
                            ),
                        ),
                    ),
                )
            )

        dbus_validation_check = check_index.get("dbus_surface_validation")
        if dbus_validation_check is not None and dbus_validation_check.status in {
            DiagnosticStatus.FAIL,
            DiagnosticStatus.WARN,
            DiagnosticStatus.INFO,
        }:
            workflows.append(
                DiagnosticWorkflow(
                    key="validate_dbus_surface",
                    label="Validate the live OpenVPN 3 D-Bus surface",
                    status=dbus_validation_check.status,
                    summary=dbus_validation_check.detail,
                    steps=(
                        DiagnosticWorkflowStep(
                            title="Run the CLI D-Bus validation command on a live OpenVPN 3 Linux system",
                            detail=(
                                "Capture the live configuration, session, backend, log, and netcfg interfaces from the same machine "
                                "that will run the desktop client."
                            ),
                        ),
                        DiagnosticWorkflowStep(
                            title="Compare any missing members to the current adapter methods",
                            detail=(
                                "Update the typed adapters instead of compensating in the UI or core layers if the real surface differs."
                            ),
                        ),
                        DiagnosticWorkflowStep(
                            title="Keep the validated report with the repo or release notes",
                            detail=(
                                "Do not treat this slice as complete until the project has a preserved live validation artifact."
                            ),
                        ),
                    ),
                )
            )

        dco_capability = capability_index.get("dco")
        if settings.dco and dco_capability is not None and not dco_capability.available:
            workflows.append(
                DiagnosticWorkflow(
                    key="resolve_dco_gap",
                    label="Resolve Data Channel Offload gating",
                    status=DiagnosticStatus.WARN,
                    summary=(
                        item_index.get("dco_requested_but_unavailable", None).detail
                        if item_index.get("dco_requested_but_unavailable", None) is not None
                        else (dco_capability.reason or "DCO is unavailable.")
                    ),
                    steps=(
                        DiagnosticWorkflowStep(
                            title="Decide whether DCO is required for this machine",
                            detail=(
                                "Leave DCO disabled on hosts that do not have the kernel module or do not need the "
                                "performance path yet."
                            ),
                        ),
                        DiagnosticWorkflowStep(
                            title="Install the matching kernel support if you need DCO",
                            detail=(
                                "After the ovpn-dco kernel module is available, refresh diagnostics and then re-enable "
                                "the DCO setting."
                            ),
                        ),
                    ),
                )
            )

        posture_capability = capability_index.get("posture")
        posture_check = check_index.get("posture_prerequisites")
        if posture_capability is not None and not posture_capability.available:
            workflows.append(
                DiagnosticWorkflow(
                    key="prepare_posture_support",
                    label="Prepare device posture support",
                    status=DiagnosticStatus.INFO,
                    summary=posture_capability.reason or "Posture support is not available.",
                    steps=(
                        DiagnosticWorkflowStep(
                            title="Install the Linux posture helper components",
                            detail=(
                                posture_check.detail
                                if posture_check is not None
                                else "Install the devposture and DPC helper packages required by posture-aware access."
                            ),
                        ),
                        DiagnosticWorkflowStep(
                            title="Refresh capability detection",
                            detail=(
                                "Do not surface posture-driven UX until diagnostics report the capability as available "
                                "on this machine."
                            ),
                        ),
                    ),
                )
            )

        if not workflows:
            workflows.append(
                DiagnosticWorkflow(
                    key="baseline_ok",
                    label="Baseline diagnostics passed",
                    status=DiagnosticStatus.PASS,
                    summary=(
                        "The current environment, settings, and capability checks did not expose immediate blockers."
                    ),
                    steps=(
                        DiagnosticWorkflowStep(
                            title="Capture a support bundle before escalating",
                            detail=(
                                "If users still report failures, export a redacted bundle and attach the recent "
                                "diagnostics state instead of reproducing from memory."
                            ),
                        ),
                    ),
                )
            )

        return tuple(workflows)

    @staticmethod
    def _replacement(match: re.Match[str]) -> str:
        if match.re.pattern.startswith("openvpn://"):
            return "openvpn://import-profile/redacted"
        if match.lastindex and match.lastindex >= 2:
            separator = "" if match.group(1).endswith(" ") else "="
            return f"{match.group(1)}{separator}<redacted>"
        return "<redacted>"


def _dbus_validation_payload(report: DBusValidationReport) -> dict[str, object]:
    return {
        "status": report.status.value,
        "summary": report.summary,
        "validated_at": report.validated_at.isoformat(),
        "interfaces": [
            {
                "label": item.label,
                "service": item.service,
                "object_path": item.object_path,
                "interface": item.interface,
                "status": item.status.value,
                "detail": item.detail,
                "methods": list(item.methods),
                "properties": list(item.properties),
                "signals": list(item.signals),
                "missing_methods": list(item.missing_methods),
                "missing_properties": list(item.missing_properties),
                "missing_signals": list(item.missing_signals),
            }
            for item in report.interfaces
        ],
    }
