"""Shared dialog chrome helpers."""

from __future__ import annotations

from app.theme import sync_theme_css_classes

try:
    import gi

    gi.require_version("Gtk", "4.0")

    from gi.repository import Gtk
except (ImportError, ValueError):  # pragma: no cover - depends on system libs
    Gtk = None


def configure_dialog_chrome(dialog, *, title: str):
    """Apply the shared dialog header and theme hooks."""

    if Gtk is None:  # pragma: no cover - depends on system libs
        raise RuntimeError("GTK4 is required to configure dialog chrome.")

    dialog.set_title(title)
    dialog.add_css_class("connect-dialog")

    headerbar = Gtk.HeaderBar()
    headerbar.add_css_class("dialog-headerbar")
    headerbar.set_show_title_buttons(True)

    title_label = Gtk.Label(label=title)
    title_label.add_css_class("dialog-header-title")
    headerbar.set_title_widget(title_label)
    dialog.set_titlebar(headerbar)

    area = dialog.get_content_area()
    area.add_css_class("dialog-shell")
    sync_theme_css_classes(dialog, headerbar, area)
    return area
