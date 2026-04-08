"""Desktop application entry point."""

from __future__ import annotations

from app.application import OpenVPNApplication


def main() -> int:
    application = OpenVPNApplication()
    return application.run()


if __name__ == "__main__":
    raise SystemExit(main())

