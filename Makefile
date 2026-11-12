# VENDORED: keep identical in bot-obormot and audiodoc. Source of truth: audiodoc.

PYTHON_VERSION ?= 3.13
PYTHON_BOOTSTRAP ?= python$(PYTHON_VERSION)
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
VERSION ?= dev
PYTHON_SCRIPTS_DIR = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_path('scripts'))")

.PHONY: venv install-dev lint fix types test cov docs-check check build clean

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
	.venv/bin/python -m pip install -r requirements-dev.txt

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	$(PYTHON) scripts/check_lock.py
	$(PYTHON_SCRIPTS_DIR)/shellcheck --shell=sh install.sh

fix:
	$(PYTHON) -m ruff check . --fix
	$(PYTHON) -m ruff format .

types:
	$(PYTHON) -m mypy bot

test:
	$(PYTHON) -m pytest -q -rs \
		--cov=bot \
		--cov-branch \
		--cov-report=term-missing:skip-covered \
		--cov-report=xml \
		--cov-report=html \
		--junitxml=junit.xml

cov:
	$(PYTHON) -m coverage report --show-missing

docs-check:
	@echo "not enabled yet"

check: lint types test

build:
	bash scripts/build_release.sh "$(VERSION)"

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage coverage.xml htmlcov junit.xml dist build
