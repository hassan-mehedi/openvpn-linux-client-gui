UV ?= uv

.PHONY: test
test:
	$(UV) run pytest

.PHONY: package-assets
package-assets:
	python3 packaging/scripts/install_shared_assets.py --destdir /tmp/openvpn3-client-linux-stage --prefix /usr

.PHONY: cli-help
cli-help:
	$(UV) run python -m cli.main --help
