"""Minimal libadwaita application bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.bootstrap import build_live_services
from core.models import AppSettings, LaunchBehavior, ThemeMode

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Gdk", "4.0")

    from gi.repository import Adw, Gdk, Gio, Gtk
except (ImportError, ValueError) as exc:  # pragma: no cover - depends on system libs
    Adw = None
    Gdk = None
    Gio = None
    Gtk = None
    _IMPORT_ERROR = exc
else:  # pragma: no cover - UI boot is not exercised in unit tests
    _IMPORT_ERROR = None

from app.windows.main_window import OpenVPNMainWindow
from app.theme import apply_theme_mode
from app.tray import TrayIntegration, TraySupport


@dataclass(slots=True)
class OpenVPNApplication:
    """Thin desktop application wrapper.

    The UI layer stays intentionally small at this stage. Core behavior lives
    outside the GTK package so the CLI and tests can reuse it.
    """

    application_id: str = "com.openvpn3.clientlinux"

    def run(self) -> int:
        if Adw is None or Gdk is None or Gio is None or Gtk is None:
            raise RuntimeError(
                "PyGObject with GTK4/libadwaita is required to launch the GUI."
            ) from _IMPORT_ERROR

        app = Adw.Application(application_id=self.application_id)
        services = build_live_services()
        window: Adw.ApplicationWindow | None = None
        startup_behavior_applied = False
        force_window_close = False
        background_notification_id = "app-running-in-background"
        tray = TrayIntegration(
            app_id="openvpn3-client-linux",
            title="OpenVPN Connect",
            icon_name=self.application_id,
        )

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

            show_action = Gio.SimpleAction.new("show", None)
            show_action.connect("activate", lambda *_args: present_window())
            app.add_action(show_action)

            quit_action = Gio.SimpleAction.new("quit-now", None)
            quit_action.connect("activate", lambda *_args: quit_application())
            app.add_action(quit_action)

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

        def show_background_notification() -> None:
            notification = Gio.Notification.new("OpenVPN Connect is still running")
            notification.set_body(
                "The window was closed, but the VPN client is still running in the background."
            )
            notification.add_button("Open", "app.show")
            notification.add_button("Quit", "app.quit-now")
            app.send_notification(background_notification_id, notification)

        def on_window_destroyed(_window: Adw.ApplicationWindow) -> None:
            nonlocal window
            window = None
            app.withdraw_notification(background_notification_id)

        def is_window_visible() -> bool:
            if window is None:
                return False
            for attribute in ("is_visible", "get_visible"):
                method = getattr(window, attribute, None)
                if callable(method):
                    return bool(method())
            return False

        def hide_window() -> None:
            if window is not None:
                window.set_visible(False)

        def toggle_window_visibility() -> None:
            if is_window_visible():
                hide_window()
                return
            present_window()

        def sync_tray(settings: AppSettings) -> TraySupport:
            try:
                support = tray.sync(
                    enabled=settings.close_to_tray,
                    toggle_window_visibility=toggle_window_visibility,
                    show_window=present_window,
                    quit_application=quit_application,
                    is_window_visible=is_window_visible,
                )
            except Exception as exc:
                return TraySupport(
                    available=False,
                    message=f"Tray registration failed: {exc}",
                )
            return support

        def handle_background_close() -> None:
            if tray.is_active():
                app.withdraw_notification(background_notification_id)
                return
            show_background_notification()

        def present_window() -> None:
            nonlocal window, startup_behavior_applied
            app.withdraw_notification(background_notification_id)
            if window is None:
                window = OpenVPNMainWindow(
                    app,
                    services,
                    on_background_close=handle_background_close,
                    should_force_close=lambda: force_window_close,
                    tray_support_provider=tray.support,
                    on_settings_changed=sync_tray,
                )
                window.connect("destroy", on_window_destroyed)
            window.present()

            if startup_behavior_applied:
                return
            startup_behavior_applied = True
            try:
                settings = services.settings.load()
                sync_tray(settings)
                behavior = settings.launch_behavior
                if behavior is LaunchBehavior.CONNECT_LATEST:
                    _connect_latest(services)
                elif behavior is LaunchBehavior.RESTORE_CONNECTION:
                    _restore_connection(services)
            except Exception:
                pass  # startup behavior is best-effort

        def quit_application() -> None:
            nonlocal force_window_close
            force_window_close = True
            tray.stop()
            if window is not None:
                window.close()
            app.quit()

        def on_activate(_application: Adw.Application) -> None:
            present_window()

        app.connect("startup", on_startup)
        app.connect("activate", on_activate)
        return app.run(None)
