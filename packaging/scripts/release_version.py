#!/usr/bin/env python3
"""Release metadata helpers for CI/CD packaging workflows."""

from __future__ import annotations

import argparse
import re
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = ROOT / "pyproject.toml"
RPM_SPEC_PATH = ROOT / "packaging" / "rpm" / "openvpn3-client-linux.spec"
DEBIAN_CHANGELOG_PATH = ROOT / "debian" / "changelog"


@dataclass(frozen=True, slots=True)
class ReleasePlan:
    python_version: str
    deb_version: str
    rpm_version: str
    rpm_release: str
    tag: str
    title: str
    prerelease: bool
    changelog_message: str


def load_base_version() -> str:
    with PYPROJECT_PATH.open("rb") as handle:
        project = tomllib.load(handle)["project"]
    version = project["version"]
    if not isinstance(version, str) or not version:
        raise ValueError("Project version is missing from pyproject.toml")
    return version


def build_release_plan(
    *,
    channel: str,
    sha: str | None = None,
    timestamp: str | None = None,
    release_version: str | None = None,
) -> ReleasePlan:
    if channel not in {"stable", "snapshot"}:
        raise ValueError(f"Unsupported channel: {channel}")

    base_version = load_base_version()
    if channel == "stable":
        version = release_version or base_version
        return ReleasePlan(
            python_version=version,
            deb_version=f"{version}-1",
            rpm_version=version,
            rpm_release="1%{?dist}",
            tag=f"v{version}",
            title=f"OpenVPN 3 Linux Client {version}",
            prerelease=False,
            changelog_message=f"Automated stable release {version}.",
        )

    stamp = timestamp or datetime.now(UTC).strftime("%Y%m%d%H%M")
    short_sha = (sha or "local")[:7]
    return ReleasePlan(
        python_version=f"{base_version}.dev{stamp}",
        deb_version=f"{base_version}~dev{stamp}-1",
        rpm_version=base_version,
        rpm_release=f"0.1.dev{stamp}%{{?dist}}",
        tag=f"main-{stamp}-{short_sha}",
        title=f"Main snapshot {stamp} ({short_sha})",
        prerelease=True,
        changelog_message=(
            f"Automated snapshot build from main at {stamp} ({short_sha})."
        ),
    )


def apply_release_plan(
    plan: ReleasePlan,
    *,
    maintainer_name: str,
    maintainer_email: str,
    release_date: datetime | None = None,
) -> None:
    update_pyproject_version(plan.python_version)
    update_rpm_spec(plan.rpm_version, plan.rpm_release)
    update_debian_changelog(
        deb_version=plan.deb_version,
        message=plan.changelog_message,
        maintainer_name=maintainer_name,
        maintainer_email=maintainer_email,
        release_date=release_date,
    )


def update_pyproject_version(version: str) -> None:
    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'(?m)^version = "[^"]+"$',
        f'version = "{version}"',
        content,
        count=1,
    )
    if count != 1:
        raise ValueError("Unable to update project version in pyproject.toml")
    PYPROJECT_PATH.write_text(updated, encoding="utf-8")


def update_rpm_spec(version: str, release: str) -> None:
    content = RPM_SPEC_PATH.read_text(encoding="utf-8")
    content, version_count = re.subn(
        r"(?m)^Version:\s+.+$",
        f"Version:        {version}",
        content,
        count=1,
    )
    content, release_count = re.subn(
        r"(?m)^Release:\s+.+$",
        f"Release:        {release}",
        content,
        count=1,
    )
    if version_count != 1 or release_count != 1:
        raise ValueError("Unable to update RPM spec version metadata")
    RPM_SPEC_PATH.write_text(content, encoding="utf-8")


def update_debian_changelog(
    *,
    deb_version: str,
    message: str,
    maintainer_name: str,
    maintainer_email: str,
    release_date: datetime | None = None,
) -> None:
    when = (release_date or datetime.now(UTC)).strftime("%a, %d %b %Y %H:%M:%S %z")
    entry = "\n".join(
        (
            f"openvpn3-client-linux ({deb_version}) unstable; urgency=medium",
            "",
            f"  * {message}",
            "",
            f" -- {maintainer_name} <{maintainer_email}>  {when}",
            "",
        )
    )
    DEBIAN_CHANGELOG_PATH.write_text(entry, encoding="utf-8")


def add_plan_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--channel",
        choices=("snapshot", "stable"),
        default="snapshot",
        help="Release channel to generate metadata for.",
    )
    parser.add_argument("--sha", help="Source commit SHA for snapshot tagging.")
    parser.add_argument(
        "--timestamp",
        help="UTC timestamp in YYYYMMDDHHMM format for snapshot builds.",
    )
    parser.add_argument(
        "--release-version",
        help="Explicit stable version. Defaults to the version in pyproject.toml.",
    )


def command_base_version(_args: argparse.Namespace) -> int:
    print(load_base_version())
    return 0


def command_plan(args: argparse.Namespace) -> int:
    plan = build_release_plan(
        channel=args.channel,
        sha=args.sha,
        timestamp=args.timestamp,
        release_version=args.release_version,
    )
    values = {
        "python_version": plan.python_version,
        "deb_version": plan.deb_version,
        "rpm_version": plan.rpm_version,
        "rpm_release": plan.rpm_release,
        "tag": plan.tag,
        "title": plan.title,
        "prerelease": str(plan.prerelease).lower(),
        "changelog_message": plan.changelog_message,
    }
    for key, value in values.items():
        print(f"{key}={value}")
    return 0


def command_apply(args: argparse.Namespace) -> int:
    plan = ReleasePlan(
        python_version=args.python_version,
        deb_version=args.deb_version,
        rpm_version=args.rpm_version,
        rpm_release=args.rpm_release,
        tag=args.tag,
        title=args.title,
        prerelease=args.prerelease,
        changelog_message=args.changelog_message,
    )
    release_date = (
        datetime.strptime(args.release_date, "%Y-%m-%dT%H:%M:%S%z")
        if args.release_date
        else None
    )
    apply_release_plan(
        plan,
        maintainer_name=args.maintainer_name,
        maintainer_email=args.maintainer_email,
        release_date=release_date,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    base_version = subparsers.add_parser("base-version", help="Print the base project version.")
    base_version.set_defaults(func=command_base_version)

    plan = subparsers.add_parser("plan", help="Render release metadata as key=value pairs.")
    add_plan_arguments(plan)
    plan.set_defaults(func=command_plan)

    apply_parser = subparsers.add_parser(
        "apply",
        help="Apply explicit release metadata to pyproject, RPM, and Debian files.",
    )
    apply_parser.add_argument("--python-version", required=True)
    apply_parser.add_argument("--deb-version", required=True)
    apply_parser.add_argument("--rpm-version", required=True)
    apply_parser.add_argument("--rpm-release", required=True)
    apply_parser.add_argument("--tag", required=True)
    apply_parser.add_argument("--title", required=True)
    apply_parser.add_argument(
        "--prerelease",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    apply_parser.add_argument("--changelog-message", required=True)
    apply_parser.add_argument("--maintainer-name", required=True)
    apply_parser.add_argument("--maintainer-email", required=True)
    apply_parser.add_argument(
        "--release-date",
        help="Release date in ISO 8601 format, for example 2026-04-10T12:30:00+0000.",
    )
    apply_parser.set_defaults(func=command_apply)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
