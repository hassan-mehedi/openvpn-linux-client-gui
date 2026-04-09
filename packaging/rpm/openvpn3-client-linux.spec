Name:           openvpn3-client-linux
Version:        0.1.0
Release:        1%{?dist}
Summary:        Native Linux GUI and CLI for OpenVPN 3 Linux

License:        CC-BY-NC-4.0
URL:            https://github.com/hassan-mehedi/openvpn-linux-client-gui
Source0:        openvpn3_client_linux-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools

Requires:       gtk4
Requires:       libadwaita
Requires:       libsecret
Requires:       openvpn3
Requires:       python3-dbus
Requires:       python3-gobject

%description
Production-oriented GTK4/libadwaita desktop GUI and companion CLI for
OpenVPN 3 Linux. The application integrates with the OpenVPN 3 D-Bus services,
stores secrets via libsecret, and installs native desktop metadata for
launcher, MIME, and URI handling.

%generate_buildrequires
%pyproject_buildrequires

%prep
%autosetup -n openvpn3_client_linux-%{version}

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files app cli core openvpn3
python3 packaging/scripts/install_shared_assets.py --destdir %{buildroot} --prefix %{_prefix}

%post
if [ -x /usr/bin/update-desktop-database ]; then
    /usr/bin/update-desktop-database -q %{_datadir}/applications || :
fi
if [ -x /usr/bin/update-mime-database ]; then
    /usr/bin/update-mime-database %{_datadir}/mime || :
fi
if [ -x /usr/bin/gtk-update-icon-cache ]; then
    /usr/bin/gtk-update-icon-cache -q %{_datadir}/icons/hicolor || :
fi

%postun
if [ $1 -eq 0 ]; then
    if [ -x /usr/bin/update-desktop-database ]; then
        /usr/bin/update-desktop-database -q %{_datadir}/applications || :
    fi
    if [ -x /usr/bin/update-mime-database ]; then
        /usr/bin/update-mime-database %{_datadir}/mime || :
    fi
    if [ -x /usr/bin/gtk-update-icon-cache ]; then
        /usr/bin/gtk-update-icon-cache -q %{_datadir}/icons/hicolor || :
    fi
fi

%files -f %{pyproject_files}
%doc README.md
%{_bindir}/ovpn-gui
%{_bindir}/ovpn3-linux-gui
%{_datadir}/applications/com.openvpn3.clientlinux.desktop
%{_datadir}/icons/hicolor/scalable/apps/com.openvpn3.clientlinux.svg
%{_datadir}/mime/packages/openvpn3-client-linux.xml

%changelog
* Thu Apr 09 2026 Mehedi Hassan <howlader.mehedihassan@gmail.com> - 0.1.0-1
- Initial native package recipe for the OpenVPN 3 Linux GUI and CLI
