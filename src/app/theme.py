"""Theme application helpers for the desktop shell."""

from __future__ import annotations

from core.models import ThemeMode

try:
    import gi

    gi.require_version("Adw", "1")

    from gi.repository import Adw
except (ImportError, ValueError):  # pragma: no cover - depends on system libs
    Adw = None


def apply_theme_mode(theme_mode: ThemeMode) -> None:
    if Adw is None:  # pragma: no cover - depends on system libs
        return

    manager = Adw.StyleManager.get_default()
    if manager is None:  # pragma: no cover - depends on runtime display
        return
    manager.set_color_scheme(_color_scheme_for(theme_mode))


def _color_scheme_for(theme_mode: ThemeMode):
    if Adw is None:  # pragma: no cover - depends on system libs
        return None
    if theme_mode is ThemeMode.DARK:
        return getattr(Adw.ColorScheme, "FORCE_DARK", Adw.ColorScheme.PREFER_DARK)
    if theme_mode is ThemeMode.LIGHT:
        return getattr(Adw.ColorScheme, "FORCE_LIGHT", Adw.ColorScheme.PREFER_LIGHT)
    return Adw.ColorScheme.DEFAULT
