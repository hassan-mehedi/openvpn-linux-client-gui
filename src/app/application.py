"""Minimal libadwaita application bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.bootstrap import build_live_services
from core.models import LaunchBehavior, ThemeMode

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Gdk", "4.0")

    from gi.repository import Adw, Gdk, Gtk
except (ImportError, ValueError) as exc:  # pragma: no cover - depends on system libs
    Adw = None
    Gdk = None
    Gtk = None
    _IMPORT_ERROR = exc
else:  # pragma: no cover - UI boot is not exercised in unit tests
    _IMPORT_ERROR = None

from app.windows.main_window import OpenVPNMainWindow
from app.theme import apply_theme_mode


@dataclass(slots=True)
class OpenVPNApplication:
    """Thin desktop application wrapper.

    The UI layer stays intentionally small at this stage. Core behavior lives
    outside the GTK package so the CLI and tests can reuse it.
    """

    application_id: str = "com.openvpn3.clientlinux"

    def run(self) -> int:
        if Adw is None or Gdk is None or Gtk is None:
            raise RuntimeError(
                "PyGObject with GTK4/libadwaita is required to launch the GUI."
            ) from _IMPORT_ERROR

        app = Adw.Application(application_id=self.application_id)
        services = build_live_services()

        def on_startup(_application: Adw.Application) -> None:
            try:
                apply_theme_mode(services.settings.load().theme)
            except Exception:
                apply_theme_mode(ThemeMode.SYSTEM)
            provider = Gtk.CssProvider()
            provider.load_from_path(str(Path(__file__).with_name("styles.css")))
            display = Gdk.Display.get_default()
            if display is not None:
                Gtk.StyleContext.add_provider_for_display(
                    display,
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
                )

        def _connect_latest(svc):
            result = svc.profile_catalog.list_profiles()
            if result.profiles:
                sorted_profiles = sorted(
                    result.profiles,
                    key=lambda p: p.last_used or p.imported_at,
                    reverse=True,
                )
                svc.session_lifecycle.connect(sorted_profiles[0].id)

        def _restore_connection(svc):
            profile_id = svc.app_state.last_connected_profile_id()
            if profile_id is not None:
                svc.session_lifecycle.connect(profile_id)

        def on_activate(application: Adw.Application) -> None:
            window = OpenVPNMainWindow(application, services)
            window.present()

            try:
                settings = services.settings.load()
                behavior = settings.launch_behavior
                if behavior is LaunchBehavior.CONNECT_LATEST:
                    _connect_latest(services)
                elif behavior is LaunchBehavior.RESTORE_CONNECTION:
                    _restore_connection(services)
            except Exception:
                pass  # startup behavior is best-effort

        app.connect("startup", on_startup)
        app.connect("activate", on_activate)
        return app.run(None)
