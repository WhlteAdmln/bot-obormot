PYTHON_VERSION ?= 3.13
PYTHON_BOOTSTRAP ?= python$(PYTHON_VERSION)
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
VERSION ?= dev
PROJECT_VERSION = $(shell $(PYTHON) -c "import tomllib; from pathlib import Path; print(tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version'])")
PYTHON_SCRIPTS_DIR = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_path('scripts'))")

LOCK_PYTHON_VERSION ?= 3.11
# Releases younger than this are skipped; 0 turns the cutoff off.
LOCK_MIN_RELEASE_AGE_DAYS ?= 14

.PHONY: venv install-dev lint fix types pylint deptry vulture import-lint test \
        test-integration integration audit build docker installer \
        cov docs-check lock check clean pip-check test-no-skips \
        release-check

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
	$(PYTHON) scripts/check_test_layout.py
	$(PYTHON) scripts/check_test_rules.py
	$(PYTHON_SCRIPTS_DIR)/shfmt -i 0 -d install.sh
	find scripts -type f -name '*.sh' -exec $(PYTHON_SCRIPTS_DIR)/shfmt -i 2 -sr -d {} +
	$(PYTHON_SCRIPTS_DIR)/shellcheck $(shell git ls-files '*.sh' '*.sh.example')

fix:
	$(PYTHON) -m ruff check . --fix
	$(PYTHON) -m ruff format .

types:
	$(PYTHON) -m mypy bot_obormot

pylint:
	$(PYTHON) -m pylint bot_obormot scripts tests

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

lock:
	cutoff=""; \
	if [ "$(LOCK_MIN_RELEASE_AGE_DAYS)" -gt 0 ]; then \
		cutoff="$$($(PYTHON) -c "from datetime import datetime, timedelta, timezone; print((datetime.now(timezone.utc) - timedelta(days=$(LOCK_MIN_RELEASE_AGE_DAYS))).strftime('%Y-%m-%dT%H:%M:%SZ'))")"; \
	fi; \
	env $${cutoff:+UV_EXCLUDE_NEWER=$$cutoff} \
		uv pip compile pyproject.toml --python-version=$(LOCK_PYTHON_VERSION) \
		--output-file=requirements-lock.txt

audit:
	$(PYTHON_SCRIPTS_DIR)/pip-audit -r requirements-lock.txt

docker:
	docker compose -f compose.yaml config --quiet
	docker compose -f compose.yaml build --pull bot-obormot

installer:
	$(PYTHON) -m pytest -q tests/unit/project/test_installer.py

cov:
	$(PYTHON) -m coverage xml --fail-under=0
	$(PYTHON) scripts/coverage_gaps.py
	$(PYTHON) -m coverage report --show-missing

docs-check:
	$(PYTHON) -m scripts.check_docs
	$(PYTHON) -m pre_commit run --all-files

check: lint types pylint deptry vulture import-lint pip-check test-no-skips audit \
       release-check docs-check

pip-check:
	$(PYTHON) -m pip check

test-no-skips:
	@log="$$(mktemp)"; status=0; \
	$(MAKE) --no-print-directory test >"$$log" 2>&1 || status=$$?; \
	cat "$$log"; \
	if grep -q '^SKIPPED' "$$log"; then \
		echo "Unit tests must not be skipped." >&2; \
		status=1; \
	fi; \
	rm -f "$$log"; \
	exit $$status

release-check:
	PATH="$(PYTHON_SCRIPTS_DIR):$$PATH" bash scripts/build_release.sh "$(PROJECT_VERSION)"
	test -s dist/constraints.txt
	test -s dist/SHA256SUMS
	cd dist && sha256sum --check --status SHA256SUMS

build:
	bash scripts/build_release.sh "$(VERSION)"

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage coverage.xml htmlcov junit.xml dist build
