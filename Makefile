UV ?= uv
VERSION := $(shell python3 packaging/scripts/release_version.py base-version)

.PHONY: test
test:
	$(UV) run pytest

.PHONY: package-assets
package-assets:
	python3 packaging/scripts/install_shared_assets.py --destdir /tmp/openvpn3-client-linux-stage --prefix /usr

.PHONY: cli-help
cli-help:
	$(UV) run python -m cli.main --help

.PHONY: rpm-build
rpm-build:
	mkdir -p ~/rpmbuild/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
	rm -rf dist
	python3 -m build --sdist --no-isolation
	cp dist/openvpn3_client_linux-*.tar.gz ~/rpmbuild/SOURCES/
	rpmbuild -ba packaging/rpm/openvpn3-client-linux.spec

.PHONY: rpm-install
rpm-install:
	sudo dnf install -y ~/rpmbuild/RPMS/noarch/openvpn3-client-linux-*.noarch.rpm

.PHONY: rpm-reinstall
rpm-reinstall:
	sudo dnf reinstall -y ~/rpmbuild/RPMS/noarch/openvpn3-client-linux-*.noarch.rpm

.PHONY: rpm-uninstall
rpm-uninstall:
	sudo dnf remove -y openvpn3-client-linux

.PHONY: deb-build
deb-build:
	dpkg-buildpackage -us -uc -b

.PHONY: deb-install
deb-install:
	sudo dpkg -i ../openvpn3-client-linux_*_all.deb

.PHONY: deb-uninstall
deb-uninstall:
	sudo apt-get remove -y openvpn3-client-linux
