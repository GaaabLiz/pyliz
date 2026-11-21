# ==============================================================================
#
#   _____  ________      ________ _      ____  _____  __  __ ______ _   _ _______
#  |  __ \|  ____\ \    / /  ____| |    / __ \|  __ \|  \/  |  ____| \ | |__   __|
#  | |  | | |__   \ \  / /| |__  | |   | |  | | |__) | \  / | |__  |  \| |  | |
#  | |  | |  __|   \ \/ / |  __| | |   | |  | |  ___/| |\/| |  __| | . ` |  | |
#  | |__| | |____   \  /  | |____| |___| |__| | |    | |  | | |____| |\  |  | |
#  |_____/|______|   \/   |______|______\____/|_|    |_|  |_|______|_| \_|  |_|
#
#  Set up the local environment and run checks, tests, and API docs.
# ==============================================================================

## install              – Sync all dependency groups and extras via uv
.PHONY: install
install:
	uv sync --all-extras --all-groups

## install-all          – Install configured Python, sync all groups, and run uv build
.PHONY: install-all
install-all:
	uv python install $(CI_PYTHON_VERSION)
	uv sync --all-extras --all-groups --python $(CI_PYTHON_VERSION)
	uv build

## install-dev          – Sync only the dev dependency group
.PHONY: install-dev
install-dev:
	uv sync --group dev

## lint                 – Run Ruff linter (check only, no changes written)
.PHONY: lint
lint:
	uv run ruff check --config $(RUFF_CONFIG_FILE) .

## lint-fix             – Run Ruff linter and auto-fix safe issues
.PHONY: lint-fix
lint-fix:
	uv run ruff check --config $(RUFF_CONFIG_FILE) --fix .

## format               – Format all Python files with Ruff formatter
.PHONY: format
format:
	uv run ruff format --config $(RUFF_CONFIG_FILE) .

## format-check         – Check formatting without making changes (CI-safe)
.PHONY: format-check
format-check:
	uv run ruff format --config $(RUFF_CONFIG_FILE) --check .

## type-check           – Run static type analysis with ty
.PHONY: type-check
type-check:
	uv run --group typing ty check --config-file $(TY_CONFIG_FILE) $(PYTHON_MAIN_PACKAGE)

## test                 – Run the full test suite with pytest
.PHONY: test
test:
	@echo "[test] Running configured command: $(CI_TEST_COMMAND)"
	$(CI_TEST_COMMAND)

coverage_command = uv run pytest $(TESTS_PATH) --cov=$(PYTHON_MAIN_PACKAGE)

## test-cov             – Run tests with a terminal coverage report
.PHONY: test-cov
test-cov:
	@echo "[test-cov] Running pytest with coverage against: $(TESTS_PATH)"
	$(coverage_command) --cov-report=term-missing

## test-cov-verify      – Run tests and fail if coverage is below MIN_COVERAGE
.PHONY: test-cov-verify
test-cov-verify:
	@echo "[test-cov-verify] Verifying coverage (>=$(MIN_COVERAGE)%) against: $(TESTS_PATH)"
	$(coverage_command) --cov-report=term-missing --cov-fail-under=$(MIN_COVERAGE)

## test-cov-html        – Run tests and generate an HTML coverage report
.PHONY: test-cov-html
test-cov-html:
	@echo "[test-cov-html] Generating HTML coverage report"
	$(coverage_command) --cov-report=html
	@echo "Open htmlcov/index.html in your browser to view the report."

## test-cov-xml         – Run tests and generate an XML coverage report
.PHONY: test-cov-xml
test-cov-xml:
	@echo "[test-cov-xml] Generating XML coverage report"
	$(coverage_command) --cov-report=xml

## qa                   – Run all quality gates: lint · format-check · type-check · test
.PHONY: qa
qa: $(CI_QUALITY_TARGETS) test

## docs                 – Generate HTML docs in docs/api using the configured pdoc format
.PHONY: docs
docs:
	uv run --group docs pdoc -o docs/api -d $(PDOC_DOCFORMAT) $(PYTHON_MAIN_PACKAGE)

## docs-snap            – Preview snapshot and shared-primitive API docs in temp_local
.PHONY: docs-snap
docs-snap:
	uv run --group docs pdoc -o temp_local/docs_snap_preview -d $(PDOC_DOCFORMAT) \
		pylizlib/core/os/snap/*.py pylizlib.core.os.snap.operations \
		pylizlib.core.os.snap.storage pylizlib.core.os.snap.copying \
		pylizlib.core.os.paths pylizlib.core.os.filesystem \
		pylizlib.core.os.windows pylizlib.core.os.archives pylizlib.core.data.text

## docs-open            – Generate docs and open docs/api/index.html
.PHONY: docs-open
docs-open: docs
ifeq ($(UNAME_S),Darwin)
	open docs/api/index.html
else ifeq ($(OS_NAME),windows)
	explorer.exe docs/api/index.html
else
	xdg-open docs/api/index.html
endif

## clean-docs           – Remove only generated API documentation
.PHONY: clean-docs
clean-docs:
	- rm -rf docs/api
