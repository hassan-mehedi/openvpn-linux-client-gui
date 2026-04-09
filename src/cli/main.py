"""Companion CLI entry point."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from core.bootstrap import ServiceContainer, build_live_services
from core.models import (
    AppSettings,
    ConnectionProtocol,
    ImportPreview,
    LaunchBehavior,
    Profile,
    ProxyCredentials,
    ProxyDefinition,
    ProxyType,
    SecurityLevel,
    SessionDescriptor,
    ThemeMode,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ovpn-gui")
    subparsers = parser.add_subparsers(dest="group", required=True)

    profiles = subparsers.add_parser("profiles")
    profiles_sub = profiles.add_subparsers(dest="action", required=True)
    profiles_list = profiles_sub.add_parser("list")
    profiles_list.add_argument("--json", action="store_true")
    profiles_show = profiles_sub.add_parser("show")
    profiles_show.add_argument("profile_id")
    profiles_show.add_argument("--json", action="store_true")
    preview_file = profiles_sub.add_parser("preview-file")
    preview_file.add_argument("path", type=Path)
    preview_url = profiles_sub.add_parser("preview-url")
    preview_url.add_argument("url")
    import_file = profiles_sub.add_parser("import-file")
    import_file.add_argument("path", type=Path)
    import_file.add_argument("--name")
    import_url = profiles_sub.add_parser("import-url")
    import_url.add_argument("url")
    import_url.add_argument("--name")
    rename_profile = profiles_sub.add_parser("rename")
    rename_profile.add_argument("profile_id")
    rename_profile.add_argument("name")
    remove_profile = profiles_sub.add_parser("remove")
    remove_profile.add_argument("profile_id")
    assign_proxy = profiles_sub.add_parser("assign-proxy")
    assign_proxy.add_argument("profile_id")
    assign_proxy.add_argument("proxy_id", nargs="?")

    sessions = subparsers.add_parser("sessions")
    sessions_sub = sessions.add_subparsers(dest="action", required=True)
    sessions_list = sessions_sub.add_parser("list")
    sessions_list.add_argument("--json", action="store_true")
    status = sessions_sub.add_parser("status")
    status.add_argument("session_id")
    status.add_argument("--json", action="store_true")
    connect = sessions_sub.add_parser("connect")
    connect.add_argument("profile_id")
    disconnect = sessions_sub.add_parser("disconnect")
    disconnect.add_argument("session_id")
    pause = sessions_sub.add_parser("pause")
    pause.add_argument("session_id")
    resume = sessions_sub.add_parser("resume")
    resume.add_argument("session_id")
    restart = sessions_sub.add_parser("restart")
    restart.add_argument("session_id")

    settings = subparsers.add_parser("settings")
    settings_sub = settings.add_subparsers(dest="action", required=True)
    settings_sub.add_parser("list")
    settings_get = settings_sub.add_parser("get")
    settings_get.add_argument("key")
    set_command = settings_sub.add_parser("set")
    set_command.add_argument("key")
    set_command.add_argument("value")
    settings_sub.add_parser("path")

    config = subparsers.add_parser("config")
    config_sub = config.add_subparsers(dest="action", required=True)
    config_import = config_sub.add_parser("import")
    config_import.add_argument("path", type=Path)
    config_import.add_argument("--name")
    config_sub.add_parser("show")

    proxies = subparsers.add_parser("proxies")
    proxies_sub = proxies.add_subparsers(dest="action", required=True)
    proxies_list = proxies_sub.add_parser("list")
    proxies_list.add_argument("--json", action="store_true")
    proxy_show = proxies_sub.add_parser("show")
    proxy_show.add_argument("proxy_id")
    proxy_show.add_argument("--json", action="store_true")
    proxy_add = proxies_sub.add_parser("add")
    proxy_add.add_argument("name")
    proxy_add.add_argument("type", choices=[item.value for item in ProxyType])
    proxy_add.add_argument("host")
    proxy_add.add_argument("port", type=int)
    proxy_add.add_argument("--username")
    proxy_add.add_argument("--password")
    proxy_add.add_argument("--disabled", action="store_true")
    proxy_remove = proxies_sub.add_parser("remove")
    proxy_remove.add_argument("proxy_id")

    doctor = subparsers.add_parser("doctor")
    doctor_sub = doctor.add_subparsers(dest="action")
    doctor.set_defaults(action="summary")
    doctor_summary = doctor_sub.add_parser("summary")
    doctor_summary.add_argument("--session-id")
    doctor_summary.add_argument("--limit", type=int, default=200)
    doctor_logs = doctor_sub.add_parser("logs")
    doctor_logs.add_argument("--session-id")
    doctor_logs.add_argument("--limit", type=int, default=200)
    doctor_sub.add_parser("workflows")
    doctor_export = doctor_sub.add_parser("export")
    doctor_export.add_argument("path", nargs="?", type=Path)
    doctor_export.add_argument("--session-id")
    doctor_export.add_argument("--limit", type=int, default=200)
    doctor_sub.add_parser("dbus-surface")

    return parser


def main(argv: Sequence[str] | None = None, services: ServiceContainer | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    container = services or build_live_services()

    if args.group == "profiles":
        return _handle_profiles(args, container)
    if args.group == "sessions":
        return _handle_sessions(args, container)
    if args.group == "settings":
        return _handle_settings(args, container)
    if args.group == "config":
        return _handle_config(args, container)
    if args.group == "proxies":
        return _handle_proxies(args, container)
    if args.group == "doctor":
        return _handle_doctor(args, container)
    parser.error("Unknown command group")
    return 2


def _handle_profiles(args: argparse.Namespace, services: ServiceContainer) -> int:
    if args.action == "list":
        profiles = services.profile_catalog.list_profiles().profiles
        if args.json:
            _print_json([_profile_payload(profile) for profile in profiles])
        else:
            for profile in profiles:
                print(f"{profile.id}\t{profile.name}\t{profile.source.value}")
        return 0
    if args.action == "show":
        profile = services.profile_catalog.get_profile(args.profile_id)
        if profile is None:
            raise KeyError(f"Unknown profile: {args.profile_id}")
        if args.json:
            _print_json(_profile_payload(profile))
        else:
            print(json.dumps(_profile_payload(profile), indent=2, sort_keys=True))
        return 0
    if args.action == "preview-file":
        preview = services.profile_catalog.preview_file_import(args.path)
        _print_json(_preview_payload(preview))
        return 0
    if args.action == "preview-url":
        preview = (
            services.profile_catalog.preview_token_url_import(args.url)
            if args.url.startswith("openvpn://import-profile/")
            else services.profile_catalog.preview_url_import(args.url)
        )
        _print_json(_preview_payload(preview))
        return 0
    if args.action == "import-file":
        profile = services.profile_catalog.import_file(args.path, profile_name=args.name)
        print(profile.id)
        return 0
    if args.action == "import-url":
        importer = (
            services.profile_catalog.import_token_url
            if args.url.startswith("openvpn://import-profile/")
            else services.profile_catalog.import_url
        )
        profile = importer(args.url, profile_name=args.name)
        print(profile.id)
        return 0
    if args.action == "rename":
        services.profile_catalog.rename_profile(args.profile_id, args.name)
        print(args.profile_id)
        return 0
    if args.action == "remove":
        services.profile_catalog.delete_profile(args.profile_id)
        return 0
    if args.action == "assign-proxy":
        services.profile_catalog.assign_proxy(args.profile_id, args.proxy_id)
        return 0
    raise ValueError(f"Unsupported profiles action: {args.action}")


def _handle_sessions(args: argparse.Namespace, services: ServiceContainer) -> int:
    if args.action == "list":
        sessions = services.session.list_sessions()
        if args.json:
            _print_json([_session_payload(session) for session in sessions])
        else:
            for session in sessions:
                print(
                    f"{session.id}\t{session.profile_id}\t{session.state.value}\t{session.status_message}"
                )
        return 0
    if args.action == "status":
        session = services.session.get_session_status(args.session_id)
        if args.json:
            _print_json(_session_payload(session))
        else:
            print(json.dumps(_session_payload(session), indent=2, sort_keys=True))
        return 0
    if args.action == "connect":
        snapshot = services.session_lifecycle.connect(args.profile_id)
        session = snapshot.active_session
        if session is None:
            raise RuntimeError("Connect did not produce an active session.")
        print(f"{session.id}\t{snapshot.state.value}")
        return 0
    if args.action == "disconnect":
        session = services.session.disconnect(args.session_id)
        print(f"{session.id}\t{session.state.value}")
        return 0
    if args.action == "pause":
        session = services.session.pause(args.session_id)
        print(f"{session.id}\t{session.state.value}")
        return 0
    if args.action == "resume":
        session = services.session.resume(args.session_id)
        print(f"{session.id}\t{session.state.value}")
        return 0
    if args.action == "restart":
        session = services.session.restart(args.session_id)
        print(f"{session.id}\t{session.state.value}")
        return 0
    raise ValueError(f"Unsupported sessions action: {args.action}")


def _handle_settings(args: argparse.Namespace, services: ServiceContainer) -> int:
    if args.action == "list":
        _print_json(services.settings.load().to_mapping())
        return 0
    if args.action == "get":
        payload = services.settings.load().to_mapping()
        if args.key not in payload:
            raise KeyError(f"Unknown setting: {args.key}")
        print(payload[args.key])
        return 0
    if args.action == "set":
        current = services.settings.load()
        updated = _apply_setting(current, args.key, args.value)
        services.settings.save(updated)
        return 0
    if args.action == "path":
        print(services.settings.settings_path)
        return 0
    raise ValueError(f"Unsupported settings action: {args.action}")


def _handle_config(args: argparse.Namespace, services: ServiceContainer) -> int:
    if args.action == "import":
        profile = services.profile_catalog.import_file(args.path, profile_name=args.name)
        print(profile.id)
        return 0
    if args.action == "show":
        config_root = services.settings.settings_path.parent
        _print_json(
            {
                "config_dir": str(config_root),
                "settings_path": str(services.settings.settings_path),
                "profiles_path": str(config_root / "profiles.json"),
                "proxies_path": str(config_root / "proxies.json"),
            }
        )
        return 0
    raise ValueError(f"Unsupported config action: {args.action}")


def _handle_proxies(args: argparse.Namespace, services: ServiceContainer) -> int:
    if args.action == "list":
        proxies = services.proxies.list_proxies()
        if args.json:
            _print_json([_proxy_payload(proxy) for proxy in proxies])
        else:
            for proxy in proxies:
                print(f"{proxy.id}\t{proxy.name}\t{proxy.type.value}\t{proxy.host}:{proxy.port}")
        return 0
    if args.action == "show":
        proxy = services.proxies.get_proxy(args.proxy_id)
        if proxy is None:
            raise KeyError(f"Unknown proxy: {args.proxy_id}")
        if args.json:
            _print_json(_proxy_payload(proxy))
        else:
            print(json.dumps(_proxy_payload(proxy), indent=2, sort_keys=True))
        return 0
    if args.action == "add":
        credentials = _proxy_credentials_from_args(args)
        proxy = ProxyDefinition(
            id="",
            name=args.name,
            type=ProxyType(args.type),
            host=args.host,
            port=args.port,
            enabled=not args.disabled,
        )
        saved = services.proxies.save_proxy(proxy, credentials=credentials)
        print(saved.id)
        return 0
    if args.action == "remove":
        services.proxies.delete_proxy(args.proxy_id)
        services.profile_catalog.clear_proxy_assignments(args.proxy_id)
        return 0
    raise ValueError(f"Unsupported proxies action: {args.action}")


def _handle_doctor(args: argparse.Namespace, services: ServiceContainer) -> int:
    if args.action == "dbus-surface":
        report = services.introspection.validate_surface()
        _print_json(_dbus_validation_payload(report))
        return 0

    snapshot = services.diagnostics.build_snapshot(
        profiles=services.profile_catalog.list_profiles().profiles,
        settings=services.settings.load(),
        session_id=getattr(args, "session_id", None),
        recent_log_limit=getattr(args, "limit", 200),
    )
    if args.action == "summary":
        _print_json(
            {
                "reachable_services": snapshot.reachable_services,
                "capabilities": [
                    {
                        "key": item.key,
                        "available": item.available,
                        "reason": item.reason,
                    }
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
                "guided_workflows": [_workflow_payload(workflow) for workflow in snapshot.guided_workflows],
                "recent_logs": list(snapshot.recent_logs),
                "dbus_validation": (
                    None
                    if snapshot.dbus_validation is None
                    else _dbus_validation_payload(snapshot.dbus_validation)
                ),
            }
        )
        return 0
    if args.action == "logs":
        for line in snapshot.recent_logs:
            print(line)
        return 0
    if args.action == "workflows":
        _print_json([_workflow_payload(workflow) for workflow in snapshot.guided_workflows])
        return 0
    if args.action == "export":
        target = args.path or _default_support_bundle_path()
        exported = services.diagnostics.export_support_bundle(target, snapshot)
        print(exported)
        return 0
    raise ValueError(f"Unsupported doctor action: {args.action}")


def _apply_setting(settings: AppSettings, key: str, value: str) -> AppSettings:
    mapping = settings.to_mapping()
    if key not in mapping:
        raise KeyError(f"Unknown setting: {key}")

    if key == "protocol":
        settings.protocol = ConnectionProtocol(value)
    elif key == "launch_behavior":
        settings.launch_behavior = LaunchBehavior(value)
    elif key == "theme":
        settings.theme = ThemeMode(value)
    elif key == "security_level":
        settings.security_level = SecurityLevel(value)
    elif key == "connection_timeout":
        settings.connection_timeout = int(value)
    else:
        settings_value = value.lower() in {"1", "true", "yes", "on"}
        setattr(settings, key, settings_value)
    return settings


def _profile_payload(profile: Profile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "name": profile.name,
        "source": profile.source.value,
        "assigned_proxy_id": profile.assigned_proxy_id,
        "metadata": profile.metadata,
    }


def _preview_payload(preview: ImportPreview) -> dict[str, Any]:
    return {
        "name": preview.name,
        "source": preview.source.value,
        "canonical_location": preview.canonical_location,
        "redacted_location": preview.redacted_location,
        "content_hash": preview.content_hash,
        "duplicate_profile_id": preview.duplicate_profile_id,
        "duplicate_profile_name": preview.duplicate_profile_name,
        "duplicate_reason": preview.duplicate_reason,
        "warnings": list(preview.warnings),
        "details": (
            None
            if preview.details is None
            else {
                "profile_name": preview.details.profile_name,
                "server_hostname": preview.details.server_hostname,
                "username": preview.details.username,
                "server_locked": preview.details.server_locked,
                "username_locked": preview.details.username_locked,
                "auth_requires_password": preview.details.auth_requires_password,
            }
        ),
    }


def _session_payload(session: SessionDescriptor) -> dict[str, Any]:
    return {
        "id": session.id,
        "profile_id": session.profile_id,
        "state": session.state.value,
        "status_message": session.status_message,
        "requires_input": session.requires_input,
    }


def _proxy_payload(proxy: ProxyDefinition) -> dict[str, Any]:
    return {
        "id": proxy.id,
        "name": proxy.name,
        "type": proxy.type.value,
        "host": proxy.host,
        "port": proxy.port,
        "enabled": proxy.enabled,
        "credential_ref": proxy.credential_ref,
    }


def _workflow_payload(workflow) -> dict[str, Any]:
    return {
        "key": workflow.key,
        "label": workflow.label,
        "status": workflow.status.value,
        "summary": workflow.summary,
        "steps": [
            {"title": step.title, "detail": step.detail}
            for step in workflow.steps
        ],
    }


def _dbus_validation_payload(report) -> dict[str, Any]:
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


def _proxy_credentials_from_args(args: argparse.Namespace) -> ProxyCredentials | None:
    if args.username is None and args.password is None:
        return None
    if args.username is None or args.password is None:
        raise ValueError("Proxy credentials require both --username and --password.")
    return ProxyCredentials(username=args.username, password=args.password)


def _default_support_bundle_path(
    now: datetime | None = None,
    *,
    app_name: str = "openvpn3-client-linux",
) -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return root / app_name / "support-bundles" / f"support-{stamp}.json"


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
