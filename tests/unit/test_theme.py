from app import theme


class _FakeWidget:
    def __init__(self) -> None:
        self.classes: list[str] = []

    def add_css_class(self, css_class: str) -> None:
        if css_class not in self.classes:
            self.classes.append(css_class)

    def remove_css_class(self, css_class: str) -> None:
        self.classes = [item for item in self.classes if item != css_class]


class _FakeStyleManager:
    def __init__(self, *, dark: bool) -> None:
        self._dark = dark

    def get_dark(self) -> bool:
        return self._dark


class _FakeAdw:
    class StyleManager:
        manager = None

        @classmethod
        def get_default(cls):
            return cls.manager


def test_sync_theme_css_classes_marks_widgets_dark(monkeypatch) -> None:
    widget = _FakeWidget()
    _FakeAdw.StyleManager.manager = _FakeStyleManager(dark=True)
    monkeypatch.setattr(theme, "Adw", _FakeAdw)

    theme.sync_theme_css_classes(widget)

    assert widget.classes == ["theme-dark"]


def test_sync_theme_css_classes_replaces_existing_theme_class(monkeypatch) -> None:
    widget = _FakeWidget()
    widget.add_css_class("theme-dark")
    _FakeAdw.StyleManager.manager = _FakeStyleManager(dark=False)
    monkeypatch.setattr(theme, "Adw", _FakeAdw)

    theme.sync_theme_css_classes(widget)

    assert widget.classes == ["theme-light"]
