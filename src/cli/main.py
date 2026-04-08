"""Companion CLI entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from core.bootstrap import ServiceContainer, build_live_services
from core.models import (
    AppSettings,
    ConnectionProtocol,
    LaunchBehavior,
    ProxyDefinition,
    ProxyType,
    SecurityLevel,
    ThemeMode,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ovpn-gui")
    subparsers = parser.add_subparsers(dest="group", required=True)

    profiles = subparsers.add_parser("profiles")
    profiles_sub = profiles.add_subparsers(dest="action", required=True)
    profiles_sub.add_parser("list")

    import_file = profiles_sub.add_parser("import-file")
    import_file.add_argument("path", type=Path)

    import_url = profiles_sub.add_parser("import-url")
    import_url.add_argument("url")

    remove_profile = profiles_sub.add_parser("remove")
    remove_profile.add_argument("profile_id")
    assign_proxy = profiles_sub.add_parser("assign-proxy")
    assign_proxy.add_argument("profile_id")
    assign_proxy.add_argument("proxy_id", nargs="?")

    sessions = subparsers.add_parser("sessions")
    sessions_sub = sessions.add_subparsers(dest="action", required=True)
    connect = sessions_sub.add_parser("connect")
    connect.add_argument("profile_id")
    disconnect = sessions_sub.add_parser("disconnect")
    disconnect.add_argument("session_id")

    settings = subparsers.add_parser("settings")
    settings_sub = settings.add_subparsers(dest="action", required=True)
    settings_sub.add_parser("list")
    set_command = settings_sub.add_parser("set")
    set_command.add_argument("key")
    set_command.add_argument("value")

    config = subparsers.add_parser("config")
    config_sub = config.add_subparsers(dest="action", required=True)
    config_import = config_sub.add_parser("import")
    config_import.add_argument("path", type=Path)

    proxies = subparsers.add_parser("proxies")
    proxies_sub = proxies.add_subparsers(dest="action", required=True)
    proxies_sub.add_parser("list")
    proxy_add = proxies_sub.add_parser("add")
    proxy_add.add_argument("name")
    proxy_add.add_argument("type", choices=[item.value for item in ProxyType])
    proxy_add.add_argument("host")
    proxy_add.add_argument("port", type=int)
    proxy_remove = proxies_sub.add_parser("remove")
    proxy_remove.add_argument("proxy_id")

    subparsers.add_parser("doctor")
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
        return _handle_doctor(container)
    parser.error("Unknown command group")
    return 2


def _handle_profiles(args: argparse.Namespace, services: ServiceContainer) -> int:
    if args.action == "list":
        for profile in services.profile_catalog.list_profiles().profiles:
            print(f"{profile.id}\t{profile.name}\t{profile.source.value}")
        return 0
    if args.action == "import-file":
        profile = services.profile_catalog.import_file(args.path)
        print(profile.id)
        return 0
    if args.action == "import-url":
        importer = (
            services.profile_catalog.import_token_url
            if args.url.startswith("openvpn://import-profile/")
            else services.profile_catalog.import_url
        )
        profile = importer(args.url)
        print(profile.id)
        return 0
    if args.action == "remove":
        services.profile_catalog.delete_profile(args.profile_id)
        return 0
    if args.action == "assign-proxy":
        services.profile_catalog.assign_proxy(args.profile_id, args.proxy_id)
        return 0
    raise ValueError(f"Unsupported profiles action: {args.action}")


def _handle_sessions(args: argparse.Namespace, services: ServiceContainer) -> int:
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
    raise ValueError(f"Unsupported sessions action: {args.action}")


def _handle_settings(args: argparse.Namespace, services: ServiceContainer) -> int:
    if args.action == "list":
        payload = services.settings.load().to_mapping()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.action == "set":
        current = services.settings.load()
        updated = _apply_setting(current, args.key, args.value)
        services.settings.save(updated)
        return 0
    raise ValueError(f"Unsupported settings action: {args.action}")


def _handle_config(args: argparse.Namespace, services: ServiceContainer) -> int:
    if args.action == "import":
        profile = services.profile_catalog.import_file(args.path)
        print(profile.id)
        return 0
    raise ValueError(f"Unsupported config action: {args.action}")


def _handle_proxies(args: argparse.Namespace, services: ServiceContainer) -> int:
    if args.action == "list":
        for proxy in services.proxies.list_proxies():
            print(f"{proxy.id}\t{proxy.name}\t{proxy.type.value}\t{proxy.host}:{proxy.port}")
        return 0
    if args.action == "add":
        proxy = ProxyDefinition(
            id="",
            name=args.name,
            type=ProxyType(args.type),
            host=args.host,
            port=args.port,
        )
        saved = services.proxies.save_proxy(proxy)
        print(saved.id)
        return 0
    if args.action == "remove":
        services.proxies.delete_proxy(args.proxy_id)
        services.profile_catalog.clear_proxy_assignments(args.proxy_id)
        return 0
    raise ValueError(f"Unsupported proxies action: {args.action}")


def _handle_doctor(services: ServiceContainer) -> int:
    snapshot = services.diagnostics.build_snapshot(
        profiles=services.profile_catalog.list_profiles().profiles,
        settings=services.settings.load(),
    )
    print(
        json.dumps(
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
                "recent_logs": list(snapshot.recent_logs),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


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
        setattr(settings, key, value.lower() in {"1", "true", "yes", "on"})
    return settings


if __name__ == "__main__":
    raise SystemExit(main())
