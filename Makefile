PYTHON_VERSION ?= 3.13
PYTHON_BOOTSTRAP ?= python$(PYTHON_VERSION)
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
VERSION ?= dev
PYTHON_SCRIPTS_DIR = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_path('scripts'))")

.PHONY: venv install-dev lint fix types deptry vulture import-lint test \
        test-integration integration audit build docker installer \
        cov docs-check check clean

venv:
	@set -eu; \
	expected="$(PYTHON_VERSION)"; \
	if [ -x .venv/bin/python ] && .venv/bin/python -c \
		'import sys; raise SystemExit(".".join(map(str, sys.version_info[:2])) != sys.argv[1])' \
		"$$expected"; then \
		echo "Virtual environment already uses Python $$expected"; \
		exit 0; \
	fi; \
	if ! command -v "$(PYTHON_BOOTSTRAP)" >/dev/null 2>&1; then \
		echo "Python $$expected is required. Install it or set PYTHON_BOOTSTRAP." >&2; \
		exit 1; \
	fi; \
	if ! "$(PYTHON_BOOTSTRAP)" -c \
		'import sys; raise SystemExit(".".join(map(str, sys.version_info[:2])) != sys.argv[1])' \
		"$$expected"; then \
		echo "PYTHON_BOOTSTRAP must point to Python $$expected." >&2; \
		exit 1; \
	fi; \
	rm -rf .venv; \
	"$(PYTHON_BOOTSTRAP)" -m venv .venv

install-dev: venv
	.venv/bin/python -m pip install -r requirements-dev.txt -c requirements-lock.txt

lint: docs-check
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	$(PYTHON) scripts/check_lock.py
	$(PYTHON_SCRIPTS_DIR)/shfmt -i 0 -d install.sh
	find scripts -type f -name '*.sh' -exec $(PYTHON_SCRIPTS_DIR)/shfmt -i 2 -sr -d {} +
	$(PYTHON_SCRIPTS_DIR)/shellcheck $(shell git ls-files '*.sh' '*.sh.example')

fix:
	$(PYTHON) -m ruff check . --fix
	$(PYTHON) -m ruff format .

types:
	$(PYTHON) -m mypy bot_obormot bot

deptry:
	$(PYTHON_SCRIPTS_DIR)/deptry .

vulture:
	$(PYTHON_SCRIPTS_DIR)/vulture

import-lint:
	$(PYTHON_SCRIPTS_DIR)/lint-imports

test:
	$(PYTHON) -m pytest -q -rs -m "not integration and not e2e" \
		--cov=bot_obormot --cov-branch \
		--cov-report=term-missing:skip-covered \
		--cov-report=xml --cov-report=html --junitxml=junit.xml

test-integration:
	$(PYTHON) -m pytest -q -rs -m integration

integration: test-integration

audit:
	$(PYTHON_SCRIPTS_DIR)/pip-audit -r requirements-lock.txt

docker:
	docker compose -f compose.yaml config --quiet
	docker compose -f compose.yaml build --pull bot-obormot

installer:
	$(PYTHON) -m pytest -q tests/unit/test_installer.py
	$(PYTHON) -m pytest -q tests/integration/legacy_installer_ci.py

cov:
	$(PYTHON) -m coverage xml --fail-under=0
	$(PYTHON) scripts/coverage_gaps.py
	$(PYTHON) -m coverage report --show-missing

docs-check:
	$(PYTHON) -m scripts.check_docs
	$(PYTHON) -m pre_commit run --all-files

check: lint types deptry vulture import-lint test docs-check

build:
	bash scripts/build_release.sh "$(VERSION)"

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage coverage.xml htmlcov junit.xml dist build
