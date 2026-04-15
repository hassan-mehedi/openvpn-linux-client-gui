#!/usr/bin/env python3
"""Install a wheel into a staged filesystem using distro-friendly paths."""

from __future__ import annotations

import argparse
import sys
import sysconfig

from installer import install
from installer.destinations import SchemeDictionaryDestination
from installer.sources import WheelFile

INSTALL_PREFIX = "/usr"


def build_scheme_dict() -> dict[str, str]:
    scheme_names = set(sysconfig.get_scheme_names())
    if "deb_system" in scheme_names:
        scheme_name = "deb_system"
        vars = None
    else:
        scheme_name = "posix_prefix"
        vars = {"base": INSTALL_PREFIX, "platbase": INSTALL_PREFIX}

    return sysconfig.get_paths(scheme=scheme_name, vars=vars)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destdir", required=True, help="Staging directory root.")
    parser.add_argument("wheel", help="Wheel file to install.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    destination = SchemeDictionaryDestination(
        build_scheme_dict(),
        interpreter=sys.executable,
        script_kind="posix",
        destdir=args.destdir,
    )

    with WheelFile.open(args.wheel) as source:
        install(
            source=source,
            destination=destination,
            additional_metadata={"INSTALLER": b"openvpn3-client-linux deb helper"},
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
