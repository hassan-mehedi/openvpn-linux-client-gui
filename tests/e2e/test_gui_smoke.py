import json
from pathlib import Path
from types import SimpleNamespace

import pytest


gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from app.dialogs.import_url_dialog import present_import_profile_dialog  # noqa: E402
from app.windows.main_window import OpenVPNMainWindow  # noqa: E402
from core.models import (  # noqa: E402
    AppSettings,
    DiagnosticCheck,
    DiagnosticStatus,
    DiagnosticWorkflow,
    DiagnosticWorkflowStep,
    DiagnosticsSnapshot,
    ImportPreview,
    ImportProfileDetails,
    ImportSource,
    Profile,
    SavedCredentialState,
    SessionDescriptor,
    SessionPhase,
)
from core.session_manager import SessionSnapshot  # noqa: E402


pytestmark = pytest.mark.e2e


class _FakeSettings:
    def load(self) -> AppSettings:
        return AppSettings()

    def save(self, settings: AppSettings) -> AppSettings:
        return settings


class _FakeProfileCatalog:
    def list_profiles(self, search: str = ""):
        return SimpleNamespace(profiles=(), search=search)


class _FakeLifecycle:
    def restore_existing_session(self):
        return self.snapshot()

    def snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            state=SessionPhase.IDLE,
            selected_profile_id=None,
            active_session=None,
            attention_requests=(),
            last_error=None,
        )

    def watch_active_session(self, callback):
        return lambda: None


class _FakeDiagnostics:
    def build_snapshot(self, *, profiles, settings, session_id=None, recent_log_limit=200):
        return DiagnosticsSnapshot(
            app_version="0.1.0",
            os_release="Test Linux",
            kernel="6.8.0",
            desktop_environment="GNOME",
            reachable_services={},
            capabilities=(),
            environment_checks=(
                DiagnosticCheck(
                    key="session_bus",
                    label="Session D-Bus environment",
                    status=DiagnosticStatus.PASS,
                    detail="Looks good.",
                ),
            ),
            troubleshooting_items=(
                DiagnosticCheck(
                    key="resolver",
                    label="Resolver integration",
                    status=DiagnosticStatus.WARN,
                    detail="Needs attention.",
                ),
            ),
            guided_workflows=(
                DiagnosticWorkflow(
                    key="repair_dns_scope",
                    label="Repair VPN DNS handling",
                    status=DiagnosticStatus.WARN,
                    summary="Resolver support needs attention.",
                    steps=(
                        DiagnosticWorkflowStep(
                            title="Use local DNS",
                            detail="Avoid the global resolver dependency.",
                        ),
                    ),
                ),
            ),
            recent_logs=tuple(f"log-{index}" for index in range(min(recent_log_limit, 1))),
            profiles=profiles,
            settings=settings,
        )

    def subscribe_live_logs(self, *, session_id=None, callback, limit=200):
        callback(())
        return lambda: None

    def export_support_bundle(self, target, snapshot):
        return target


def _fake_services():
    return SimpleNamespace(
        settings=_FakeSettings(),
        profile_catalog=_FakeProfileCatalog(),
        session_lifecycle=_FakeLifecycle(),
        diagnostics=_FakeDiagnostics(),
        backend=SimpleNamespace(reachable_services=lambda: {}),
        proxies=SimpleNamespace(
            list_proxies=lambda: (),
            get_proxy=lambda proxy_id: None,
            secure_storage_available=lambda: False,
        ),
        telemetry=SimpleNamespace(snapshot=lambda session: None, clear_session=lambda session_id: None),
        profile_secrets=SimpleNamespace(
            saved_state=lambda profile_id: SavedCredentialState(profile_id=profile_id),
            secure_storage_available=lambda: False,
            clear_password=lambda profile_id: None,
            save_password=lambda profile_id, password: None,
        ),
        session=SimpleNamespace(),
        attention=SimpleNamespace(),
        onboarding=SimpleNamespace(),
        log=SimpleNamespace(),
        netcfg=SimpleNamespace(),
        configuration=SimpleNamespace(),
    )


class _StatefulSettings:
    def __init__(self) -> None:
        self.current = AppSettings()

    def load(self) -> AppSettings:
        return self.current

    def save(self, settings: AppSettings) -> AppSettings:
        self.current = settings
        return settings

    def update(self, **changes) -> AppSettings:
        for key, value in changes.items():
            setattr(self.current, key, value)
        return self.current


class _StatefulProfileCatalog:
    def __init__(self, profiles: tuple[Profile, ...] = ()) -> None:
        self._profiles = list(profiles)
        self.imported_urls: list[str] = []

    def list_profiles(self, search: str = ""):
        normalized = search.strip().lower()
        profiles = tuple(
            profile
            for profile in self._profiles
            if not normalized
            or normalized in profile.name.lower()
            or normalized in profile.id.lower()
        )
        return SimpleNamespace(profiles=profiles, search=search)

    def get_profile(self, profile_id: str) -> Profile | None:
        return next((item for item in self._profiles if item.id == profile_id), None)

    def preview_file_import(self, path: Path, source: ImportSource = ImportSource.FILE) -> ImportPreview:
        return ImportPreview(
            name=path.name,
            source=source,
            canonical_location=str(path),
            redacted_location=str(path),
            details=ImportProfileDetails(profile_name=path.name),
        )

    def preview_url_import(self, url: str) -> ImportPreview:
        duplicate = next(
            (item for item in self._profiles if item.metadata.get("canonical_url") == url),
            None,
        )
        return ImportPreview(
            name="Imported Remote",
            source=ImportSource.URL,
            canonical_location=url,
            redacted_location=url,
            duplicate_profile_id=duplicate.id if duplicate is not None else None,
            duplicate_profile_name=duplicate.name if duplicate is not None else None,
            duplicate_reason="Matching import URL" if duplicate is not None else None,
            details=ImportProfileDetails(
                profile_name="Imported Remote",
                server_hostname="vpn.example.com",
                server_locked=True,
            ),
        )

    def preview_token_url_import(self, token_url: str) -> ImportPreview:
        return self.preview_url_import(token_url)

    def import_file(
        self,
        path: Path,
        *,
        source: ImportSource = ImportSource.FILE,
        profile_name: str | None = None,
    ) -> Profile:
        profile = Profile(
            id=f"profile-{len(self._profiles) + 1}",
            name=profile_name or path.stem,
            source=source,
            metadata={"profile_name": profile_name or path.stem},
        )
        self._profiles.append(profile)
        return profile

    def import_url(self, url: str, *, profile_name: str | None = None) -> Profile:
        name = profile_name or "Imported Remote"
        profile = Profile(
            id=f"profile-{len(self._profiles) + 1}",
            name=name,
            source=ImportSource.URL,
            metadata={
                "canonical_url": url,
                "profile_name": name,
                "server_hostname": "vpn.example.com",
            },
        )
        self.imported_urls.append(url)
        self._profiles.append(profile)
        return profile

    def import_token_url(self, url: str, *, profile_name: str | None = None) -> Profile:
        return self.import_url(url, profile_name=profile_name)

    def rename_profile(self, profile_id: str, profile_name: str) -> None:
        profile = self.get_profile(profile_id)
        if profile is not None:
            profile.name = profile_name

    def assign_proxy(self, profile_id: str, proxy_id: str | None) -> None:
        profile = self.get_profile(profile_id)
        if profile is not None:
            profile.assigned_proxy_id = proxy_id

    def reset_profile_overrides(self, profile_id: str) -> None:
        return None

    def clear_proxy_assignments(self, proxy_id: str) -> None:
        for profile in self._profiles:
            if profile.assigned_proxy_id == proxy_id:
                profile.assigned_proxy_id = None

    def delete_profile(self, profile_id: str) -> None:
        self._profiles = [item for item in self._profiles if item.id != profile_id]


class _StatefulLifecycle:
    def __init__(self, *, restored_session: SessionDescriptor | None = None) -> None:
        self._restored_session = restored_session
        self._active_session: SessionDescriptor | None = None
        self._state = SessionPhase.IDLE
        self._selected_profile_id: str | None = None
        self.connect_calls: list[str] = []
        self.restore_calls = 0
        self._watchers: list = []

    def restore_existing_session(self, profile_id: str | None = None):
        self.restore_calls += 1
        if self._active_session is None and self._restored_session is not None:
            if profile_id is None or self._restored_session.profile_id == profile_id:
                self._active_session = self._restored_session
                self._selected_profile_id = self._restored_session.profile_id
                self._state = self._restored_session.state
        return self.snapshot()

    def snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            state=self._state,
            selected_profile_id=self._selected_profile_id,
            active_session=self._active_session,
            attention_requests=(),
            last_error=None,
        )

    def connect(self, profile_id: str | None = None):
        if profile_id is not None:
            self.connect_calls.append(profile_id)
            self._selected_profile_id = profile_id
        active_profile_id = profile_id or self._selected_profile_id
        assert active_profile_id is not None
        self._active_session = SessionDescriptor(
            id=f"session-{len(self.connect_calls)}",
            profile_id=active_profile_id,
            state=SessionPhase.CONNECTED,
            status_message="Connected",
        )
        self._state = SessionPhase.CONNECTED
        snapshot = self.snapshot()
        for watcher in list(self._watchers):
            watcher(snapshot)
        return snapshot

    def disconnect(self):
        self._active_session = None
        self._state = SessionPhase.IDLE
        return self.snapshot()

    def pause(self):
        if self._active_session is not None:
            self._active_session = SessionDescriptor(
                id=self._active_session.id,
                profile_id=self._active_session.profile_id,
                state=SessionPhase.PAUSED,
                status_message="Paused",
            )
            self._state = SessionPhase.PAUSED
        return self.snapshot()

    def resume(self):
        if self._selected_profile_id is not None:
            return self.connect(self._selected_profile_id)
        return self.snapshot()

    def refresh_status(self):
        return self.snapshot()

    def reset_error(self):
        return self.snapshot()

    def watch_active_session(self, callback):
        self._watchers.append(callback)
        return lambda: self._watchers.remove(callback) if callback in self._watchers else None


class _StatefulDiagnostics:
    def __init__(self) -> None:
        self.exported_paths: list[Path] = []

    def build_snapshot(self, *, profiles, settings, session_id=None, recent_log_limit=200):
        return DiagnosticsSnapshot(
            app_version="0.1.0",
            os_release="Test Linux",
            kernel="6.8.0",
            desktop_environment="GNOME",
            reachable_services={
                "net.openvpn.v3.configuration": True,
                "net.openvpn.v3.sessions": True,
            },
            capabilities=(),
            environment_checks=(
                DiagnosticCheck(
                    key="session_bus",
                    label="Session D-Bus environment",
                    status=DiagnosticStatus.PASS,
                    detail="Looks good.",
                ),
            ),
            troubleshooting_items=(
                DiagnosticCheck(
                    key="baseline",
                    label="No immediate environment issues detected",
                    status=DiagnosticStatus.PASS,
                    detail="Looks healthy.",
                ),
            ),
            guided_workflows=(
                DiagnosticWorkflow(
                    key="baseline_ok",
                    label="Baseline diagnostics passed",
                    status=DiagnosticStatus.PASS,
                    summary="No blockers detected.",
                    steps=(
                        DiagnosticWorkflowStep(
                            title="Export a support bundle if needed",
                            detail="The diagnostics export remains available.",
                        ),
                    ),
                ),
            ),
            recent_logs=tuple(f"log-{index}" for index in range(min(recent_log_limit, 2))),
            profiles=profiles,
            settings=settings,
        )

    def subscribe_live_logs(self, *, session_id=None, callback, limit=200):
        callback(("log-0", "log-1")[:limit])
        return lambda: None

    def export_support_bundle(self, target, snapshot):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "app_version": snapshot.app_version,
                    "profiles": [profile.name for profile in snapshot.profiles],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.exported_paths.append(target)
        return target


def _stateful_services(
    *,
    profiles: tuple[Profile, ...] = (),
    restored_session: SessionDescriptor | None = None,
):
    return SimpleNamespace(
        settings=_StatefulSettings(),
        profile_catalog=_StatefulProfileCatalog(profiles),
        session_lifecycle=_StatefulLifecycle(restored_session=restored_session),
        diagnostics=_StatefulDiagnostics(),
        backend=SimpleNamespace(
            reachable_services=lambda: {
                "net.openvpn.v3.configuration": True,
                "net.openvpn.v3.sessions": True,
            }
        ),
        proxies=SimpleNamespace(
            list_proxies=lambda: (),
            get_proxy=lambda proxy_id: None,
            secure_storage_available=lambda: False,
            load_proxy_credentials=lambda proxy_id: None,
            save_proxy=lambda proxy, credentials=None, clear_credentials=False: proxy,
            delete_proxy=lambda proxy_id: None,
        ),
        telemetry=SimpleNamespace(snapshot=lambda session: None, clear_session=lambda session_id: None),
        profile_secrets=SimpleNamespace(
            saved_state=lambda profile_id: SavedCredentialState(profile_id=profile_id),
            secure_storage_available=lambda: False,
            clear_password=lambda profile_id: None,
            save_password=lambda profile_id, password: None,
        ),
        session=SimpleNamespace(),
        attention=SimpleNamespace(),
        onboarding=SimpleNamespace(),
        log=SimpleNamespace(),
        netcfg=SimpleNamespace(),
        configuration=SimpleNamespace(),
    )


def _drain_events() -> None:
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)


def _walk(widget):
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from _walk(child)
        child = child.get_next_sibling()


def _find_widget(root, predicate):
    return next((widget for widget in _walk(root) if predicate(widget)), None)


def _find_label(root, text: str):
    return _find_widget(
        root,
        lambda widget: isinstance(widget, Gtk.Label) and widget.get_label() == text,
    )


def _find_button_with_label(root, text: str):
    return _find_widget(
        root,
        lambda widget: isinstance(widget, Gtk.Button) and widget.get_label() == text,
    )


def _find_button_with_tooltip(root, text: str):
    return _find_widget(
        root,
        lambda widget: isinstance(widget, (Gtk.Button, Gtk.MenuButton))
        and widget.get_tooltip_text() == text,
    )


def _find_entry_with_placeholder(root, text: str):
    return _find_widget(
        root,
        lambda widget: isinstance(widget, Gtk.Entry) and widget.get_placeholder_text() == text,
    )


def _find_toplevel_dialog(title: str):
    dialogs = [
        widget
        for widget in Gtk.Window.list_toplevels()
        if isinstance(widget, Gtk.Dialog) and widget.get_title() == title
    ]
    return dialogs[-1] if dialogs else None


def test_main_window_builds_real_gtk_shell() -> None:
    app = Adw.Application(application_id="com.example.OpenVPN3ClientLinux.Tests")
    app.register(None)

    window = OpenVPNMainWindow(app, _fake_services())
    _drain_events()

    assert window.get_title() == "OpenVPN Connect"
    assert any(
        isinstance(widget, Gtk.Label) and widget.get_label() == "Guided Recovery"
        for widget in _walk(window)
    )

    window.destroy()


def test_import_dialog_builds_real_gtk_dialog() -> None:
    app = Adw.Application(application_id="com.example.OpenVPN3ClientLinux.DialogTests")
    app.register(None)
    parent = Adw.ApplicationWindow(application=app)

    present_import_profile_dialog(
        parent,
        on_preview_url=lambda url: ImportPreview(
            name="remote.ovpn",
            source=ImportSource.URL,
            canonical_location=url,
            redacted_location=url,
            details=ImportProfileDetails(
                profile_name="remote.ovpn",
                server_hostname="vpn.example.com",
                server_locked=True,
            ),
        ),
        on_preview_file=lambda path, source: ImportPreview(
            name=path.name,
            source=source,
            canonical_location=str(path),
            redacted_location=str(path),
            details=ImportProfileDetails(profile_name=path.name),
        ),
        on_commit_url=lambda url, profile_name, connect_after: None,
        on_commit_file=lambda path, source, profile_name, connect_after: None,
    )
    _drain_events()

    dialogs = [
        widget
        for widget in Gtk.Window.list_toplevels()
        if isinstance(widget, Gtk.Dialog) and widget.get_title() == "Import Profile"
    ]

    assert dialogs

    for dialog in dialogs:
        dialog.destroy()
    parent.destroy()


def test_main_window_import_url_flow_adds_profile_card() -> None:
    app = Adw.Application(application_id="com.example.OpenVPN3ClientLinux.ImportFlow")
    app.register(None)
    services = _stateful_services()

    window = OpenVPNMainWindow(app, services)
    _drain_events()

    import_button = _find_button_with_tooltip(window, "Import profile")
    assert import_button is not None
    popover = import_button.get_popover()
    assert popover is not None
    popover.popup()
    _drain_events()

    import_url_button = _find_button_with_label(popover, "Import URL")
    assert import_url_button is not None
    import_url_button.emit("clicked")
    _drain_events()

    dialog = _find_toplevel_dialog("Import Profile")
    assert dialog is not None

    url_entry = _find_entry_with_placeholder(dialog, "https://vpn.example.com/profile.ovpn")
    assert url_entry is not None
    url_entry.set_text("https://vpn.example.com/profile.ovpn")
    _drain_events()

    dialog.response(Gtk.ResponseType.ACCEPT)
    _drain_events()
    assert _find_label(dialog, "Imported Profile") is not None

    dialog.response(Gtk.ResponseType.REJECT)
    _drain_events()

    assert _find_label(window, "Imported Remote") is not None
    assert services.profile_catalog.imported_urls == ["https://vpn.example.com/profile.ovpn"]

    window.destroy()


def test_main_window_connect_flow_updates_connection_state() -> None:
    app = Adw.Application(application_id="com.example.OpenVPN3ClientLinux.ConnectFlow")
    app.register(None)
    services = _stateful_services(
        profiles=(
            Profile(
                id="profile-1",
                name="Office VPN",
                source=ImportSource.URL,
                metadata={"server_hostname": "vpn.example.com"},
            ),
        ),
    )

    window = OpenVPNMainWindow(app, services)
    _drain_events()

    connect_button = _find_button_with_tooltip(window, "Connect Office VPN")
    assert connect_button is not None
    connect_button.emit("clicked")
    _drain_events()

    assert services.session_lifecycle.connect_calls == ["profile-1"]
    assert _find_label(window, "CONNECTED") is not None
    assert _find_label(window, "Office VPN") is not None
    assert _find_label(
        window,
        "Connection is active. Session details and live status are shown below.",
    ) is not None

    window.destroy()


def test_main_window_restore_connection_flow_shows_existing_session() -> None:
    app = Adw.Application(application_id="com.example.OpenVPN3ClientLinux.RestoreFlow")
    app.register(None)
    services = _stateful_services(
        profiles=(
            Profile(
                id="profile-restore",
                name="Restored VPN",
                source=ImportSource.FILE,
            ),
        ),
        restored_session=SessionDescriptor(
            id="session-restore",
            profile_id="profile-restore",
            state=SessionPhase.CONNECTED,
            status_message="Connected",
        ),
    )

    window = OpenVPNMainWindow(app, services)
    _drain_events()

    assert services.session_lifecycle.restore_calls >= 1
    assert _find_label(window, "CONNECTED") is not None
    assert _find_label(window, "Restored VPN") is not None

    window.destroy()


def test_main_window_diagnostics_export_flow_writes_bundle(tmp_path: Path, monkeypatch) -> None:
    app = Adw.Application(application_id="com.example.OpenVPN3ClientLinux.DiagnosticsFlow")
    app.register(None)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    services = _stateful_services(
        profiles=(
            Profile(
                id="profile-1",
                name="Diagnostic VPN",
                source=ImportSource.URL,
            ),
        ),
    )

    window = OpenVPNMainWindow(app, services)
    _drain_events()

    export_button = _find_button_with_label(window, "Export Support Bundle")
    assert export_button is not None
    export_button.emit("clicked")
    _drain_events()

    assert services.diagnostics.exported_paths
    exported_path = services.diagnostics.exported_paths[-1]
    assert exported_path.exists()
    payload = json.loads(exported_path.read_text(encoding="utf-8"))
    assert payload["profiles"] == ["Diagnostic VPN"]
    assert _find_label(window, str(exported_path)) is not None

    window.destroy()
