UV ?= uv

.PHONY: test
test:
	$(UV) run pytest

.PHONY: cli-help
cli-help:
	$(UV) run python -m cli.main --help
