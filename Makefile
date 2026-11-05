# ==============================================================================
#
#  _______     _________ _    _  ____  _   _
# |  __ \ \   / /__   __| |  | |/ __ \| \ | |
# | |__) \ \_/ /   | |  | |__| | |  | |  \| |
# |  ___/ \   /    | |  |  __  | |  | | . ` |
# | |      | |     | |  | |  | | |__| | |\  |
# |_|      |_|     |_|  |_|  |_|\____/|_| \_|
#
#  _____  _____   ____       _ ______ _____ _______
# |  __ \|  __ \ / __ \     | |  ____/ ____|__   __|
# | |__) | |__) | |  | |    | | |__ | |       | |
# |  ___/|  _  /| |  | |_   | |  __|| |       | |
# | |    | | \ \| |__| | |__| | |___| |____   | |
# |_|    |_|  \_\\____/ \____/|______\_____|  |_|
#
#  __  __          _  ________ ______ _____ _      ______
# |  \/  |   /\   | |/ /  ____|  ____|_   _| |    |  ____|
# | \  / |  /  \  | ' /| |__  | |__    | | | |    | |__
# | |\/| | / /\ \ |  < |  __| |  __|   | | | |    |  __|
# | |  | |/ ____ \| . \| |____| |     _| |_| |____| |____
# |_|  |_/_/    \_\_|\_\______|_|    |_____|______|______|
#
#                           VERSION 2.0.0
#
#  A reusable, self-documenting Makefile template for Python projects
#  managed with `uv`.
#
#  ► All project-specific variables live in project.mk  – edit THAT file.
#  ► Run `make` (no arguments) to see the list of available targets.
#
#  Sections
#  ─────────────────────────────────────────────────────────────────────────────
#    1. Platform Detection  – OS detection for cross-platform support
#    2. Help                – self-documenting target list
#    3. Environment         – install / setup via uv
#    4. Generate            – code generation from metadata
#    5. Quality             – lint · format · type-check · test
#    6. Build               – sdist · wheel · standalone executables
#    7. Docs                – API documentation with pdoc
#    8. Clean               – remove build artefacts and caches
#    9. Versioning          – bump version · create git tags
#   10. CI Helpers          – lightweight targets for GitHub Actions
#
# ==============================================================================

include project.mk


# ==============================================================================
#  1. PLATFORM DETECTION
#
#  Automatically detects the host OS so that platform-specific tools
#  (e.g. icon formats for PyInstaller, sed flavour for in-place edits)
#  can be selected without any manual configuration.
# ==============================================================================

UNAME_S := $(shell uname -s)

ifeq ($(UNAME_S),Darwin)
    OS_NAME     := macos
    SED_INPLACE := sed -i ''
else ifeq ($(UNAME_S),Linux)
    OS_NAME     := linux
    SED_INPLACE := sed -i
else
    OS_NAME     := windows
    SED_INPLACE := sed -i
endif


# ==============================================================================
#  2. HELP
#
#  The default target. Scans all included Makefiles for lines of the form
#      ## target-name  – Short description
#  and prints a formatted, colour-coded reference table.
# ==============================================================================

.DEFAULT_GOAL := help

## help              – Show this help message and exit
.PHONY: help
help:
	@printf "\n"
	@printf "  \033[1mPython Project Makefile\033[0m\n"
	@printf "  ──────────────────────────────────────────────────────\n"
	@grep -E '^## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS="## "}; {printf "  \033[36m%-26s\033[0m %s\n", $$2, $$3}' 2>/dev/null \
		|| grep -E '^## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS="## "}; {printf "  %-26s\n", $$2}'
	@printf "\n"


# ==============================================================================
#  3. ENVIRONMENT
#
#  ______ _   ___      _______ _____   ____  _   _ __  __ ______ _   _ _______
# |  ____| \ | \ \    / /_   _|  __ \ / __ \| \ | |  \/  |  ____| \ | |__   __|
# | |__  |  \| |\ \  / /  | | | |__) | |  | |  \| | \  / | |__  |  \| |  | |
# |  __| | . ` | \ \/ /   | | |  _  /| |  | | . ` | |\/| |  __| | . ` |  | |
# | |____| |\  |  \  /   _| |_| | \ \| |__| | |\  | |  | | |____| |\  |  | |
# |______|_| \_|   \/   |_____|_|  \_\\____/|_| \_|_|  |_|______|_| \_|  |_|
#
#  Setup and install targets for the local development environment.
#  Requires `uv` to be installed: https://docs.astral.sh/uv/
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

## install-pyinstaller  – Sync the build group containing PyInstaller
.PHONY: install-pyinstaller
install-pyinstaller:
	uv sync --group dev --group build

## install-inno         – Install Inno Setup via Chocolatey (Windows only)
.PHONY: install-inno
install-inno:
	@if [ "$(OS_NAME)" != "windows" ]; then \
		echo "Error: install-inno is available only on Windows."; \
		exit 1; \
	fi
	choco install innosetup --yes


# ==============================================================================
#  4. GENERATE
#
#    _____ ______ _   _ ______ _____         _______ ______
#   / ____|  ____| \ | |  ____|  __ \     /\|__   __|  ____|
#  | |  __| |__  |  \| | |__  | |__) |   /  \  | |  | |__
#  | | |_ |  __| | . ` |  __| |  _  /   / /\ \ | |  |  __|
#  | |__| | |____| |\  | |____| | \ \  / ____ \| |  | |____
#   \_____|______|_| \_|______|_|  \_\/_/    \_\_|  |______|
#
#  Targets that auto-generate source files from project metadata.
#  Qt resource generation lives in qt.mk (include it from project.mk if needed).
# ==============================================================================

## gen-project-module   – Generate $(FILE_PROJECT_PY_GENERATED) from pyproject.toml
#
#  Reads the [project] table from pyproject.toml and writes a plain Python
#  module (zero external dependencies) that exposes name, version, description,
#  requires_python, and authors as module-level constants.
.PHONY: gen-project-module
gen-project-module:
	uv run python .mk/scripts.py gen-project-module "$(FILE_PROJECT_TOML)" "$(FILE_PROJECT_PY_GENERATED)"

## gen-logo-icons SVG=<path>  – Convert a .svg file to .ico/.png/.jpg/.icns in all standard sizes
#
#  Requires skia-python and Pillow from the graphics dependency group.
#
#  Example:
#      make gen-logo-icons SVG=resources/logo.svg
.PHONY: gen-logo-icons
gen-logo-icons:
	@if [ -z "$(SVG)" ]; then \
		echo "Error: SVG variable is required."; \
		echo "Usage: make gen-logo-icons SVG=resources/logo.svg"; \
		exit 1; \
	fi
	uv run --group graphics python .mk/scripts.py convert-logo "$(SVG)"

## gen-inno-iss         – Generate $(INNO_SETUP_FILE) from project.mk installer variables
#
#  Creates a clean, template-friendly Inno Setup script that packages the
#  executable configured in project.mk. The script version is resolved from
#  `uv version --short`, so release bumps are reflected automatically.
.PHONY: gen-inno-iss
gen-inno-iss:
	uv run python .mk/scripts.py gen-inno-iss \
		"$(INNO_SETUP_FILE)" \
		"$(INNO_SETUP_VERSION_VARIABLE)" \
		"$(INNO_APP_NAME)" \
		"$(INNO_APP_PUBLISHER)" \
		"$(INNO_APP_ICON)" \
		"$(INNO_APP_EXE)" \
		"$(INNO_DEFAULT_DIR_NAME)" \
		"$(INNO_DEFAULT_GROUP_NAME)" \
		"$(INNO_OUTPUT_DIR)" \
		"$(INNO_OUTPUT_BASE_FILENAME)" \
		"$(INNO_COMPRESSION)" \
		"$(INNO_SOLID_COMPRESSION)" \
		"$$(uv version --short)"


# ==============================================================================
#  5. QUALITY
#
#    ____  _    _         _      _____ _________     __
#   / __ \| |  | |  /\   | |    |_   _|__   __\ \   / /
#  | |  | | |  | | /  \  | |      | |    | |   \ \_/ /
#  | |  | | |  | |/ /\ \ | |      | |    | |    \   /
#  | |__| | |__| / ____ \| |____ _| |_   | |     | |
#   \___\_\\____/_/    \_\______|_____|  |_|     |_|
#
#  Lint, format, type-check, and test the source code.
#  All tools are run through uv so no global installs are required.
# ==============================================================================

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

## test-cov             – Run tests with a terminal coverage report
.PHONY: test-cov
test-cov:
	@echo "[test-cov] Running pytest with coverage against: $(TESTS_PATH)"
	uv run pytest $(TESTS_PATH) --cov=$(PYTHON_MAIN_PACKAGE) --cov-report=term-missing

## test-cov-verify      – Run tests and fail if coverage is below MIN_COVERAGE
.PHONY: test-cov-verify
test-cov-verify:
	@echo "[test-cov-verify] Verifying coverage (>=$(MIN_COVERAGE)%) against: $(TESTS_PATH)"
	uv run pytest $(TESTS_PATH) --cov=$(PYTHON_MAIN_PACKAGE) --cov-report=term-missing --cov-fail-under=$(MIN_COVERAGE)

## test-cov-html        – Run tests and generate an HTML coverage report
.PHONY: test-cov-html
test-cov-html:
	@echo "[test-cov-html] Generating HTML coverage report"
	uv run pytest $(TESTS_PATH) --cov=$(PYTHON_MAIN_PACKAGE) --cov-report=html
	@echo "Open htmlcov/index.html in your browser to view the report."

## test-cov-xml         – Run tests and generate an XML coverage report
.PHONY: test-cov-xml
test-cov-xml:
	@echo "[test-cov-xml] Generating XML coverage report"
	uv run pytest $(TESTS_PATH) --cov=$(PYTHON_MAIN_PACKAGE) --cov-report=xml

## qa                   – Run all quality gates: lint · format-check · type-check · test
.PHONY: qa
qa: $(CI_QUALITY_TARGETS) test


# ==============================================================================
#  6. BUILD
#
#   ____  _    _ _____ _      _____
#  |  _ \| |  | |_   _| |    |  __ \
#  | |_) | |  | | | | | |    | |  | |
#  |  _ <| |  | | | | | |    | |  | |
#  | |_) | |__| |_| |_| |____| |__| |
#  |____/ \____/|_____|______|_____/
#
#  Build distribution packages (wheel + sdist) and standalone executables.
#  PyInstaller targets require `install-pyinstaller` to have been run first.
# ==============================================================================

## build                – Full build: clean → gen-project-module → uv build
.PHONY: build
build: clean gen-project-module build-uv
	@echo "[build] Build completed for package $(PYTHON_MAIN_PACKAGE)"

## build-uv             – Build sdist and wheel with uv (no clean or generate step)
.PHONY: build-uv
build-uv:
	@echo "[build-uv] Building sdist and wheel into dist/"
	uv build
	@$(MAKE) --no-print-directory ci-list-build-artifacts

## build-exe            – Build one-folder executables with PyInstaller for each app in APPS_LIST
#
#  Iterates over APPS_LIST. For each entry <id> the following companion
#  variables must be defined in project.mk:
#    <id>_NAME   output binary name (without extension)
#    <id>_MAIN   entry-point script passed to PyInstaller
#    <id>_ICO    Windows icon  (.ico)
#    <id>_ICNS   macOS icon    (.icns)
.PHONY: build-exe
build-exe:
	@set -eu; \
	if [ -z "$(strip $(APPS_LIST))" ]; then \
		echo "[build-exe] APPS_LIST is empty -> skipping PyInstaller one-folder builds."; \
		echo "[build-exe] Set APPS_LIST plus <app>_NAME/<app>_MAIN/<app>_ICO/<app>_ICNS in project.mk to enable executables."; \
	else \
		echo "[build-exe] Building PyInstaller apps: $(APPS_LIST)"; \
		$(foreach app,$(APPS_LIST),\
			uv run pyinstaller --noconfirm $(if $(filter 1,$(PYINSTALLER_WINDOWED)),--windowed,) \
				$(if $(filter Darwin,$(UNAME_S)),--icon=$($(app)_ICNS),$(if $(filter windows,$(OS_NAME)),--icon=$($(app)_ICO),)) \
				--name=$($(app)_NAME)-$(OS_NAME) \
				$($(app)_MAIN); \
		) \
		echo "[build-exe] PyInstaller one-folder build completed."; \
	fi

## build-exe-onefile    – Build single-file executables with PyInstaller for each app in APPS_LIST
.PHONY: build-exe-onefile
build-exe-onefile:
	@set -eu; \
	if [ -z "$(strip $(APPS_LIST))" ]; then \
		echo "[build-exe-onefile] APPS_LIST is empty -> skipping PyInstaller onefile builds."; \
		echo "[build-exe-onefile] Package-only releases do not enable platform asset builds."; \
	else \
		echo "[build-exe-onefile] Building PyInstaller onefile apps: $(APPS_LIST)"; \
		$(foreach app,$(APPS_LIST),\
			uv run pyinstaller --noconfirm $(if $(filter 1,$(PYINSTALLER_WINDOWED)),--windowed,) --onefile \
				$(if $(filter Darwin,$(UNAME_S)),--icon=$($(app)_ICNS),$(if $(filter windows,$(OS_NAME)),--icon=$($(app)_ICO),)) \
				--name=$($(app)_NAME)-$(OS_NAME) \
				$($(app)_MAIN); \
		) \
		echo "[build-exe-onefile] PyInstaller onefile build completed."; \
	fi

## build-app            – Full app build: clean → gen-project-module → uv build → build-exe
.PHONY: build-app
build-app: clean gen-project-module build-uv build-exe

## build-app-onefile    – Full app build using the --onefile PyInstaller mode
.PHONY: build-app-onefile
build-app-onefile: clean gen-project-module build-uv build-exe-onefile

## installer            – Run Inno Setup to produce the Windows installer (Windows only)
.PHONY: installer
installer: gen-inno-iss
ifeq ($(filter Darwin Linux,$(UNAME_S)),)
	ISCC.exe $(INNO_SETUP_FILE)
else
	@echo "Error: The installer target can only be run on Windows."
	@exit 1
endif

## build-installer      – Full pipeline including the Windows installer step
.PHONY: build-installer
build-installer: build-app-onefile installer


# ==============================================================================
#  7. DOCS
#
#   _____   ____   _____  _____
#  |  __ \ / __ \ / ____|/ ____|
#  | |  | | |  | | |    | (___
#  | |  | | |  | | |     \___ \
#  | |__| | |__| | |____ ____) |
#  |_____/ \____/ \_____|_____/
#
#  Generate API documentation with pdoc.
#  Install pdoc first: `uv add --group dev pdoc`
# ==============================================================================

## docs                 – Generate HTML docs in docs/ using pdoc (markdown format)
.PHONY: docs
docs:
	uv run --group docs pdoc -o docs/api -d markdown $(PYTHON_MAIN_PACKAGE)

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


# ==============================================================================
#  8. CLEAN
#
#    _____ _      ______          _   _
#   / ____| |    |  ____|   /\   | \ | |
#  | |    | |    | |__     /  \  |  \| |
#  | |    | |    |  __|   / /\ \ | . ` |
#  | |____| |____| |____ / ____ \| |\  |
#   \_____|______|______/_/    \_\_| \_|
#
#  Remove generated files, build artefacts, and caches.
# ==============================================================================

## clean                – Remove build artefacts and caches (safe pre-build step)
.PHONY: clean
clean: clean-build clean-cache

## clean-all            – Remove build artefacts and generated API docs
.PHONY: clean-all
clean-all: clean clean-docs

## clean-build          – Remove dist/, build/, .egg-info, and PyInstaller .spec files
.PHONY: clean-build
clean-build:
	- rm -rf dist
	- rm -rf build
	- rm -rf $(PYTHON_MAIN_PACKAGE).egg-info
	- rm -f *.spec

## clean-cache          – Remove Python bytecode, pytest, ty, and ruff caches
.PHONY: clean-cache
clean-cache:
	- rm -rf __pycache__
	- rm -rf .pytest_cache
	- rm -rf .ty_cache
	- rm -rf .ruff_cache
	- find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true

## clean-docs           – Remove only generated API documentation
.PHONY: clean-docs
clean-docs:
	- rm -rf docs/api

## clean-generated      – Remove only the auto-generated Python source files
.PHONY: clean-generated
clean-generated:
	@echo "Cleaning generated files..."
	- rm -f $(FILE_PROJECT_PY_GENERATED)


# ==============================================================================
#  9. VERSIONING
#
# __      ________ _____   _____ _____ ____  _   _ _____ _   _  _____
# \ \    / /  ____|  __ \ / ____|_   _/ __ \| \ | |_   _| \ | |/ ____|
#  \ \  / /| |__  | |__) | (___   | || |  | |  \| | | | |  \| | |  __
#   \ \/ / |  __| |  _  / \___ \  | || |  | | . ` | | | | . ` | | |_ |
#    \  /  | |____| | \ \ ____) |_| || |__| | |\  |_| |_| |\  | |__| |
#     \/   |______|_|  \_\_____/|_____\____/|_| \_|_____|_| \_|\_____|
#
#  Bump the project version (managed by uv) and manage git release tags.
#
#  Typical workflows
#  ─────────────────────────────────────────────────────────────────────────────
#    Patch release  →  make release-patch-tag
#    Minor release  →  make release-minor-tag
#    Pre-release    →  make release-patch-beta-tag
# ==============================================================================

## bump-patch-beta      – Bump to next patch pre-release, e.g. 1.2.3 → 1.2.4b1
.PHONY: bump-patch-beta
bump-patch-beta:
	uv version --bump patch --bump beta

## bump-patch           – Bump the patch component, e.g. 1.2.3 → 1.2.4
.PHONY: bump-patch
bump-patch:
	uv version --bump patch

## bump-minor           – Bump the minor component, e.g. 1.2.3 → 1.3.0
.PHONY: bump-minor
bump-minor:
	uv version --bump minor

## bump-major           – Bump the major component, e.g. 1.2.3 → 2.0.0
.PHONY: bump-major
bump-major:
	uv version --bump major

# ── Internal helper ──────────────────────────────────────────────────────────
#
#  Shared recipe executed after every version bump target.
#  Steps:
#    1. Optionally patches the version string inside the Inno Setup .iss file.
#    2. Commits all staged changes with a "bump: vX.Y.Z" message.
#    3. Pull-rebases to incorporate remote changes, then pushes.
define _release_impl
	@VERSION=$$(uv version --short); \
	echo "Releasing version $$VERSION …"; \
	if [ -f "$(INNO_SETUP_FILE)" ]; then \
		echo "  Updating Inno Setup version …"; \
		$(SED_INPLACE) \
			"s/#define $(INNO_SETUP_VERSION_VARIABLE) \"[^\"]*\"/#define $(INNO_SETUP_VERSION_VARIABLE) \"$$VERSION\"/" \
			$(INNO_SETUP_FILE); \
	fi; \
	git commit -am "bump: v$$VERSION"; \
	git pull --rebase; \
	git push
endef

## release-patch-beta   – bump-patch-beta + gen-project-module + commit & push
.PHONY: release-patch-beta
release-patch-beta: bump-patch-beta gen-project-module
	$(call _release_impl)

## release-patch        – bump-patch + gen-project-module + commit & push
.PHONY: release-patch
release-patch: bump-patch gen-project-module
	$(call _release_impl)

## release-minor        – bump-minor + gen-project-module + commit & push
.PHONY: release-minor
release-minor: bump-minor gen-project-module
	$(call _release_impl)

## release-major        – bump-major + gen-project-module + commit & push
.PHONY: release-major
release-major: bump-major gen-project-module
	$(call _release_impl)

## tag                  – Pull latest, create a v-prefixed git tag from uv version, and push
.PHONY: tag
tag:
	git pull
	git tag v$$(uv version --short)
	git push origin v$$(uv version --short)

## release-patch-beta-tag – release-patch-beta + tag
.PHONY: release-patch-beta-tag
release-patch-beta-tag: release-patch-beta tag

## release-patch-tag    – release-patch + tag
.PHONY: release-patch-tag
release-patch-tag: release-patch tag

## release-minor-tag    – release-minor + tag
.PHONY: release-minor-tag
release-minor-tag: release-minor tag

## release-major-tag    – release-major + tag
.PHONY: release-major-tag
release-major-tag: release-major tag


# ==============================================================================
# 10. CI HELPERS
#
#    _____ _____   _    _ ______ _      _____  ______ _____   _____
#   / ____|_   _| | |  | |  ____| |    |  __ \|  ____|  __ \ / ____|
#  | |      | |   | |__| | |__  | |    | |__) | |__  | |__) | (___
#  | |      | |   |  __  |  __| | |    |  ___/|  __| |  _  / \___ \
#  | |____ _| |_  | |  | | |____| |____| |    | |____| | \ \ ____) |
#   \_____|_____| |_|  |_|______|______|_|    |______|_|  \_\_____/
#
#  Make-first targets consumed by GitHub Actions workflows.
#  Keep all shell logic here so workflow files stay short and generic.
# ==============================================================================

## ci-log-config          – Print the project settings that drive CI and release automation
.PHONY: ci-log-config
ci-log-config:
	@echo "[ci-log-config] Project configuration summary"
	@echo "[ci-log-config] PYTHON_MAIN_PACKAGE=$(PYTHON_MAIN_PACKAGE)"
	@echo "[ci-log-config] TESTS_PATH=$(TESTS_PATH)"
	@echo "[ci-log-config] CI_PYTHON_VERSION=$(CI_PYTHON_VERSION)"
	@echo "[ci-log-config] CI_PYTHON_VERSIONS=$(CI_PYTHON_VERSIONS)"
	@echo "[ci-log-config] CI_TEST_OS_MATRIX=$(CI_TEST_OS_MATRIX)"
	@echo "[ci-log-config] CI_UV_VERSION=$(CI_UV_VERSION)"
	@echo "[ci-log-config] CI_QUALITY_TARGETS=$(CI_QUALITY_TARGETS)"
	@echo "[ci-log-config] CI_TEST_COMMAND=$(CI_TEST_COMMAND)"
	@echo "[ci-log-config] CI_DOCKER_ENTRYPOINT=$(CI_DOCKER_ENTRYPOINT)"
	@echo "[ci-log-config] APPS_LIST=$(if $(strip $(APPS_LIST)),$(APPS_LIST),<empty>)"
	@echo "[ci-log-config] ENABLE_WINDOWS_INSTALLER=$(ENABLE_WINDOWS_INSTALLER)"
	@echo "[ci-log-config] RELEASE_ARTIFACTS=$(RELEASE_ARTIFACTS)"
	@echo "[ci-log-config] CI_ENABLE_WINGET_PUBLISH=$(CI_ENABLE_WINGET_PUBLISH)"
	@echo "[ci-log-config] CI_WINGET_PACKAGE_IDENTIFIER=$(CI_WINGET_PACKAGE_IDENTIFIER)"
	@echo "[ci-log-config] Hint: leave APPS_LIST empty and CI_BUILD_* at 0 for package-only releases."
	@echo "[ci-log-config] Hint: RELEASE_ARTIFACTS covers optional platform assets; package distributions are uploaded by CI."

## ci-setup               – Prepare CI environment (install Python via uv + sync the dev group)
.PHONY: ci-setup
ci-setup:
	@echo "[ci-setup] Installing Python $(CI_PYTHON_VERSION) via uv"
	uv python install $(CI_PYTHON_VERSION)
	@echo "[ci-setup] Syncing the default project and dev dependencies"
	uv sync --group dev --python $(CI_PYTHON_VERSION) --locked
	@echo "[ci-setup] Tool versions"
	uv --version
	uv run python --version

## ci-quality             – Run CI static quality gates (lint, format-check, type-check)
.PHONY: ci-quality
ci-quality:
	@echo "[ci-quality] Running configured quality targets: $(CI_QUALITY_TARGETS)"
	$(MAKE) --no-print-directory $(CI_QUALITY_TARGETS)

## ci-test                – Run the required test command configured for CI
.PHONY: ci-test
ci-test:
	@echo "[ci-test] Tests are required in CI"
	$(MAKE) --no-print-directory test

## ci-validate-config    – Validate CI matrices and publication dependencies
.PHONY: ci-validate-config
ci-validate-config:
	python3 .mk/scripts.py validate-ci-config \
		'$(CI_PYTHON_VERSIONS)' '$(CI_TEST_OS_MATRIX)' \
		'$(CI_ENABLE_PYPI_PUBLISH)' '$(CI_ENABLE_HOMEBREW_PUBLISH)' \
		'$(CI_ENABLE_DOCKERHUB_PUBLISH)' '$(CI_DOCKERHUB_IMAGE)' \
		'$(CI_ENABLE_CHOCOLATEY_PUBLISH)' \
		'$(CI_ENABLE_WINGET_PUBLISH)' '$(CI_ENABLE_RELEASE_DOCS)' \
		'$(CI_BUILD_LINUX)' '$(CI_BUILD_MACOS)' '$(CI_BUILD_WINDOWS)' \
		'$(ENABLE_WINDOWS_INSTALLER)' '$(APPS_LIST)' '$(RELEASE_ARTIFACTS)' \
		'$(INNO_OUTPUT_DIR)/$(INNO_OUTPUT_BASE_FILENAME).exe' \
		'$(CI_DOCKER_PUSH_LATEST)' '$(CI_HOMEBREW_LICENSE)' \
		'$(CI_WINGET_LICENSE)' '$(CI_WINGET_LICENSE_URL)' \
		'$(CI_HOMEBREW_HOMEPAGE)' '$(CI_HOMEBREW_TAP_REPO)' \
		'$(CI_CHOCOLATEY_PROJECT_URL)' '$(CI_CHOCOLATEY_LICENSE_URL)' \
		'$(CI_CHOCOLATEY_INSTALLER_URL)' '$(CI_WINGET_HOMEPAGE)' \
		'$(CI_WINGET_INSTALLER_URL)' '$(CI_WINGET_INSTALLER_FILE)' \
		'$(CI_WINGET_FORK_REPO)' \
		'$(CI_WINGET_PACKAGE_IDENTIFIER)' '$(FILE_PROJECT_TOML)' \
		'$(CI_HOMEBREW_RESOURCES_FILE)' '$(PYINSTALLER_WINDOWED)'
	@set -eu; \
	if [ "$(CI_BUILD_LINUX)$(CI_BUILD_MACOS)$(CI_BUILD_WINDOWS)" != "000" ]; then \
		:; \
		$(foreach app,$(APPS_LIST),\
			if [ -z "$($(app)_NAME)" ]; then echo "Error: $(app)_NAME must be set when native builds are enabled."; exit 1; fi; \
			if [ -z "$($(app)_MAIN)" ] || [ ! -f "$($(app)_MAIN)" ]; then echo "Error: $(app)_MAIN must point to an existing entry-point file."; exit 1; fi; \
			if [ "$(CI_BUILD_MACOS)" = "1" ] && { [ -z "$($(app)_ICNS)" ] || [ ! -f "$($(app)_ICNS)" ]; }; then echo "Error: $(app)_ICNS must point to an existing .icns file for macOS builds."; exit 1; fi; \
			if [ "$(CI_BUILD_WINDOWS)" = "1" ] && { [ -z "$($(app)_ICO)" ] || [ ! -f "$($(app)_ICO)" ]; }; then echo "Error: $(app)_ICO must point to an existing .ico file for Windows builds."; exit 1; fi; \
		) \
	fi; \
	if [ "$(ENABLE_WINDOWS_INSTALLER)" = "1" ]; then \
		if [ ! -f "$(INNO_APP_ICON)" ]; then echo "Error: INNO_APP_ICON must point to an existing .ico file."; exit 1; fi; \
		case " $(foreach app,$(APPS_LIST),dist/$($(app)_NAME)-windows.exe) " in \
			*" $(INNO_APP_EXE) "*) ;; \
			*) echo "Error: INNO_APP_EXE must match one of the configured PyInstaller outputs ($(foreach app,$(APPS_LIST),dist/$($(app)_NAME)-windows.exe))."; exit 1 ;; \
		esac; \
	fi

## ci-setup-build         – Add build-only dependencies to the CI environment
.PHONY: ci-setup-build
ci-setup-build: ci-setup
	@echo "[ci-setup-build] Syncing PyInstaller build dependencies"
	uv sync --group dev --group build --python $(CI_PYTHON_VERSION) --locked

## ci-export-config       – Export CI configuration values to $GITHUB_OUTPUT
.PHONY: ci-export-config
ci-export-config:
	@$(MAKE) --no-print-directory ci-validate-config
	@if [ -z "$$GITHUB_OUTPUT" ]; then \
		echo "Error: GITHUB_OUTPUT is not set."; \
		exit 1; \
	fi
	@echo "[ci-export-config] Exporting CI configuration to $$GITHUB_OUTPUT"
	@printf 'python_version=%s\n' '$(CI_PYTHON_VERSION)' >> "$$GITHUB_OUTPUT"
	@printf 'python_versions=%s\n' '$(CI_PYTHON_VERSIONS)' >> "$$GITHUB_OUTPUT"
	@printf 'test_os_matrix=%s\n' '$(CI_TEST_OS_MATRIX)' >> "$$GITHUB_OUTPUT"
	@printf 'uv_version=%s\n' '$(CI_UV_VERSION)' >> "$$GITHUB_OUTPUT"
	@echo "release_branch=$(RELEASE_CHANGELOG_TARGET_BRANCH)" >> "$$GITHUB_OUTPUT"
	@echo "windows_installer_enabled=$(ENABLE_WINDOWS_INSTALLER)" >> "$$GITHUB_OUTPUT"
	@echo "build_linux=$(CI_BUILD_LINUX)" >> "$$GITHUB_OUTPUT"
	@echo "build_macos=$(CI_BUILD_MACOS)" >> "$$GITHUB_OUTPUT"
	@echo "build_windows=$(CI_BUILD_WINDOWS)" >> "$$GITHUB_OUTPUT"
	@echo "enable_pypi_publish=$(CI_ENABLE_PYPI_PUBLISH)" >> "$$GITHUB_OUTPUT"
	@echo "pypi_environment=$(CI_PYPI_ENVIRONMENT)" >> "$$GITHUB_OUTPUT"
	@echo "enable_dockerhub_publish=$(CI_ENABLE_DOCKERHUB_PUBLISH)" >> "$$GITHUB_OUTPUT"
	@echo "dockerhub_environment=$(CI_DOCKERHUB_ENVIRONMENT)" >> "$$GITHUB_OUTPUT"
	@echo "enable_chocolatey_publish=$(CI_ENABLE_CHOCOLATEY_PUBLISH)" >> "$$GITHUB_OUTPUT"
	@echo "chocolatey_environment=$(CI_CHOCOLATEY_ENVIRONMENT)" >> "$$GITHUB_OUTPUT"
	@echo "chocolatey_source_url=$(CI_CHOCOLATEY_SOURCE_URL)" >> "$$GITHUB_OUTPUT"
	@echo "enable_homebrew_publish=$(CI_ENABLE_HOMEBREW_PUBLISH)" >> "$$GITHUB_OUTPUT"
	@echo "homebrew_environment=$(CI_HOMEBREW_ENVIRONMENT)" >> "$$GITHUB_OUTPUT"
	@echo "homebrew_tap_repo=$(CI_HOMEBREW_TAP_REPO)" >> "$$GITHUB_OUTPUT"
	@echo "homebrew_formula_name=$(CI_HOMEBREW_FORMULA_NAME)" >> "$$GITHUB_OUTPUT"
	@echo "enable_winget_publish=$(CI_ENABLE_WINGET_PUBLISH)" >> "$$GITHUB_OUTPUT"
	@echo "winget_environment=$(CI_WINGET_ENVIRONMENT)" >> "$$GITHUB_OUTPUT"
	@echo "winget_fork_repo=$(CI_WINGET_FORK_REPO)" >> "$$GITHUB_OUTPUT"
	@echo "winget_package_identifier=$(CI_WINGET_PACKAGE_IDENTIFIER)" >> "$$GITHUB_OUTPUT"
	@echo "dockerhub_image=$(CI_DOCKERHUB_IMAGE)" >> "$$GITHUB_OUTPUT"
	@echo "dockerfile=$(CI_DOCKERFILE)" >> "$$GITHUB_OUTPUT"
	@echo "docker_build_context=$(CI_DOCKER_BUILD_CONTEXT)" >> "$$GITHUB_OUTPUT"
	@echo "docker_push_latest=$(CI_DOCKER_PUSH_LATEST)" >> "$$GITHUB_OUTPUT"
	@echo "enable_release_docs=$(CI_ENABLE_RELEASE_DOCS)" >> "$$GITHUB_OUTPUT"
	@echo "changelog_file=$(CI_CHANGELOG_FILE)" >> "$$GITHUB_OUTPUT"
	@echo "release_notes_file=$(CI_RELEASE_NOTES_FILE)" >> "$$GITHUB_OUTPUT"
	@echo "git_cliff_config=$(CI_GIT_CLIFF_CONFIG)" >> "$$GITHUB_OUTPUT"
	@{ \
		echo "release_artifacts<<EOF"; \
		$(MAKE) --no-print-directory ci-release-artifacts; \
		echo "EOF"; \
	} >> "$$GITHUB_OUTPUT"

## ci-install-git-cliff   – Ensure git-cliff is available in CI
.PHONY: ci-install-git-cliff
ci-install-git-cliff:
	@echo "[ci-install-git-cliff] Installing git-cliff via uv tool"
	uv tool install git-cliff==$(CI_GIT_CLIFF_VERSION)

## ci-generate-changelog  – Generate the full changelog file configured in CI_CHANGELOG_FILE
.PHONY: ci-generate-changelog
ci-generate-changelog:
	@echo "[ci-generate-changelog] Writing $(CI_CHANGELOG_FILE) using $(CI_GIT_CLIFF_CONFIG)"
	uvx --from git-cliff==$(CI_GIT_CLIFF_VERSION) git-cliff --config $(CI_GIT_CLIFF_CONFIG) --output $(CI_CHANGELOG_FILE)

## ci-generate-release-notes – Generate latest release notes into CI_RELEASE_NOTES_FILE
.PHONY: ci-generate-release-notes
ci-generate-release-notes:
	@echo "[ci-generate-release-notes] Writing $(CI_RELEASE_NOTES_FILE)"
	uvx --from git-cliff==$(CI_GIT_CLIFF_VERSION) git-cliff --config $(CI_GIT_CLIFF_CONFIG) --latest --strip header > $(CI_RELEASE_NOTES_FILE)

## ci-generate-docs       – Generate project documentation for release automation
.PHONY: ci-generate-docs
ci-generate-docs:
	@echo "[ci-generate-docs] Generating docs/api/ for $(PYTHON_MAIN_PACKAGE)"
	$(MAKE) --no-print-directory docs

## ci-prepare-release-update-branch – Start release automation from the tagged commit
.PHONY: ci-prepare-release-update-branch
ci-prepare-release-update-branch:
	@set -eu; \
	if [ -z "$${GITHUB_REF_NAME:-}" ] || [ -z "$${GITHUB_SHA:-}" ]; then \
		echo "Error: release tag context is missing."; exit 1; \
	fi; \
	TARGET_BRANCH="$(RELEASE_CHANGELOG_TARGET_BRANCH)"; \
	PR_BRANCH="automation/release-updates-$$GITHUB_REF_NAME"; \
	git fetch origin "refs/heads/$$TARGET_BRANCH:refs/remotes/origin/$$TARGET_BRANCH"; \
	if ! git merge-base --is-ancestor "$$GITHUB_SHA" "origin/$$TARGET_BRANCH"; then \
		echo "Error: release commit $$GITHUB_SHA is not contained in origin/$$TARGET_BRANCH."; \
		exit 1; \
	fi; \
	git switch --create "$$PR_BRANCH" "$$GITHUB_SHA"

## ci-open-release-updates-pr – Open/update a PR for generated release files
.PHONY: ci-open-release-updates-pr
ci-open-release-updates-pr:
	@set -eu; \
	if [ -z "$${GITHUB_REF_NAME:-}" ] || [ -z "$${GITHUB_SHA:-}" ]; then \
		echo "Error: release tag context is missing."; exit 1; \
	fi; \
	if [ -z "$${GH_TOKEN:-}" ]; then \
		echo "Error: GH_TOKEN is not set."; exit 1; \
	fi; \
	TARGET_BRANCH="$(RELEASE_CHANGELOG_TARGET_BRANCH)"; \
	PR_BRANCH="automation/release-updates-$$GITHUB_REF_NAME"; \
	if [ "$$(git branch --show-current)" != "$$PR_BRANCH" ]; then \
		echo "Error: expected to run on branch $$PR_BRANCH."; exit 1; \
	fi; \
	git config user.name "github-actions[bot]"; \
	git config user.email "github-actions[bot]@users.noreply.github.com"; \
	git add -- "$(CI_CHANGELOG_FILE)"; \
	if [ "$(CI_ENABLE_RELEASE_DOCS)" = "1" ]; then git add -A -- docs/api; fi; \
	if git diff --cached --quiet; then \
		echo "No generated release file changes to publish."; exit 0; \
	fi; \
	git commit -m "chore: update generated release files for $$GITHUB_REF_NAME"; \
	REMOTE_REF=$$(git ls-remote origin "refs/heads/$$PR_BRANCH"); \
	REMOTE_SHA=$${REMOTE_REF%%[[:space:]]*}; \
	if [ -n "$$REMOTE_SHA" ]; then \
		git push --force-with-lease="refs/heads/$$PR_BRANCH:$$REMOTE_SHA" origin "HEAD:refs/heads/$$PR_BRANCH"; \
	else \
		git push origin "HEAD:refs/heads/$$PR_BRANCH"; \
	fi; \
	PR_NUMBER=$$(GH_TOKEN="$$GH_TOKEN" gh pr list --repo "$$GITHUB_REPOSITORY" --head "$$PR_BRANCH" --state open --json number --jq '.[0].number // empty'); \
	if [ -n "$$PR_NUMBER" ]; then \
		GH_TOKEN="$$GH_TOKEN" gh pr edit "$$PR_NUMBER" --repo "$$GITHUB_REPOSITORY" \
			--title "chore: update generated files for $$GITHUB_REF_NAME" \
			--body "Generated changelog and optional API documentation for release $$GITHUB_REF_NAME."; \
	else \
		GH_TOKEN="$$GH_TOKEN" gh pr create --repo "$$GITHUB_REPOSITORY" \
			--base "$$TARGET_BRANCH" --head "$$PR_BRANCH" \
			--title "chore: update generated files for $$GITHUB_REF_NAME" \
			--body "Generated changelog and optional API documentation for release $$GITHUB_REF_NAME."; \
	fi

## ci-build-release-assets – Build release assets for the current runner OS with verbose diagnostics
.PHONY: ci-build-release-assets
ci-build-release-assets:
	@set -eu; \
	echo "[ci-build-release-assets] Runner OS=$(OS_NAME)"; \
	echo "[ci-build-release-assets] APPS_LIST=$(if $(strip $(APPS_LIST)),$(APPS_LIST),<empty>)"; \
	echo "[ci-build-release-assets] ENABLE_WINDOWS_INSTALLER=$(ENABLE_WINDOWS_INSTALLER)"; \
	if [ -n "$(strip $(APPS_LIST))" ]; then \
		$(MAKE) --no-print-directory gen-project-module; \
	fi; \
	if [ "$(OS_NAME)" = "windows" ] && [ "$(ENABLE_WINDOWS_INSTALLER)" = "1" ]; then \
		echo "[ci-build-release-assets] Building Windows installer because ENABLE_WINDOWS_INSTALLER=1"; \
		$(MAKE) --no-print-directory install-inno; \
		$(MAKE) --no-print-directory build-exe-onefile; \
		$(MAKE) --no-print-directory installer; \
	elif [ -n "$(strip $(APPS_LIST))" ]; then \
		echo "[ci-build-release-assets] APPS_LIST is set -> building onefile executables"; \
		$(MAKE) --no-print-directory build-exe-onefile; \
	else \
		echo "[ci-build-release-assets] No platform assets configured; package distributions are built once by CI."; \
	fi; \
	if [ "$(OS_NAME)" = "macos" ] && [ "$(PYINSTALLER_WINDOWED)" = "1" ] && [ -n "$(strip $(APPS_LIST))" ]; then \
		echo "[ci-build-release-assets] Archiving windowed macOS app bundles for release"; \
		$(foreach app,$(APPS_LIST),\
			APP_DIR="dist/$($(app)_NAME)-macos.app"; \
			if [ ! -d "$$APP_DIR" ]; then echo "Error: expected macOS app bundle $$APP_DIR was not built."; exit 1; fi; \
			ditto -c -k --sequesterRsrc --keepParent "$$APP_DIR" "$$APP_DIR.zip"; \
			rm -rf "$$APP_DIR"; \
		) \
	fi; \
	$(MAKE) --no-print-directory ci-list-build-artifacts

## ci-list-build-artifacts – Print the generated files used by CI and release jobs
.PHONY: ci-list-build-artifacts
ci-list-build-artifacts:
	@echo "[ci-list-build-artifacts] RELEASE_ARTIFACTS patterns:"
	@$(MAKE) --no-print-directory ci-release-artifacts | while IFS= read -r pattern; do \
		echo "[ci-list-build-artifacts]   $$pattern"; \
	done
	@echo "[ci-list-build-artifacts] dist/ contents:"
	@if [ -d dist ]; then \
		find dist -type f | sort; \
	else \
		echo "[ci-list-build-artifacts]   dist/ does not exist"; \
	fi
	@echo "[ci-list-build-artifacts] Output/ contents:"
	@if [ -d Output ]; then \
		find Output -type f | sort; \
	else \
		echo "[ci-list-build-artifacts]   Output/ does not exist"; \
	fi

## ci-verify-release-artifacts – Fail early when RELEASE_ARTIFACTS does not match generated files
.PHONY: ci-verify-release-artifacts
ci-verify-release-artifacts:
	@set -eu; \
	matched=0; \
	echo "[ci-verify-release-artifacts] Checking RELEASE_ARTIFACTS=$(RELEASE_ARTIFACTS)"; \
	for pattern in $(RELEASE_ARTIFACTS); do \
		echo "[ci-verify-release-artifacts] Pattern: $$pattern"; \
		for file in $$pattern; do \
			if [ -e "$$file" ]; then \
				echo "[ci-verify-release-artifacts]   matched: $$file"; \
				matched=1; \
			fi; \
		done; \
	done; \
	if [ "$$matched" -ne 1 ]; then \
		echo "[ci-verify-release-artifacts] Error: no platform assets matched RELEASE_ARTIFACTS."; \
		echo "[ci-verify-release-artifacts] Hint: wheel and sdist files are built separately by the CI gate."; \
		echo "[ci-verify-release-artifacts] Hint: executable projects must set APPS_LIST and companion *_NAME/*_MAIN/*_ICO/*_ICNS variables in project.mk."; \
		echo "[ci-verify-release-artifacts] Hint: installer projects usually need Output/*.exe added to RELEASE_ARTIFACTS."; \
		exit 1; \
	fi; \
	for expected in $(foreach app,$(APPS_LIST),$(if $(and $(filter macos,$(OS_NAME)),$(filter 1,$(PYINSTALLER_WINDOWED))),dist/$(or $($(app)_NAME),$(app))-macos.app.zip,dist/$(or $($(app)_NAME),$(app))-$(OS_NAME)$(if $(filter windows,$(OS_NAME)),.exe))); do \
		if [ ! -e "$$expected" ]; then \
			echo "[ci-verify-release-artifacts] Error: expected app artifact $$expected was not built."; \
			exit 1; \
		fi; \
		included=0; \
		for pattern in $(RELEASE_ARTIFACTS); do \
			for file in $$pattern; do \
				if [ "$$file" = "$$expected" ]; then included=1; fi; \
			done; \
		done; \
		if [ "$$included" -ne 1 ]; then \
			echo "[ci-verify-release-artifacts] Error: $$expected is not included in RELEASE_ARTIFACTS."; \
			exit 1; \
		fi; \
	done

## ci-smoke-build        – Install each wheel and sdist in isolation and import the package
.PHONY: ci-smoke-build
ci-smoke-build:
	uv run python .mk/scripts.py smoke-install-artifacts dist "$(PYTHON_MAIN_PACKAGE)"

## ci-verify-release-version – Fail unless the current v-tag matches the project version
.PHONY: ci-verify-release-version
ci-verify-release-version:
	@if [ "$$GITHUB_REF_TYPE" != "tag" ] || [ -z "$$GITHUB_REF_NAME" ]; then \
		echo "Error: release version verification requires a pushed tag."; \
		exit 1; \
	fi; \
	VERSION=$$(uv version --short); \
	TAG_VERSION=$${GITHUB_REF_NAME#v}; \
	if [ "$$VERSION" != "$$TAG_VERSION" ]; then \
		echo "Error: tag version '$$TAG_VERSION' does not match pyproject version '$$VERSION'."; \
		exit 1; \
	fi; \
	echo "Verified release version $$VERSION."

## ci-publish-pypi        – Publish package artifacts to PyPI (requires a token or trusted publishing)
.PHONY: ci-publish-pypi
ci-publish-pypi:
	uv publish

## ci-export-docker-tag   – Export Docker tag (release tag or pyproject version) to $GITHUB_OUTPUT
.PHONY: ci-export-docker-tag
ci-export-docker-tag:
	@if [ -z "$$GITHUB_OUTPUT" ]; then \
		echo "Error: GITHUB_OUTPUT is not set."; \
		exit 1; \
	fi
	@TAG="$$GITHUB_REF_NAME"; \
	if [ "$$GITHUB_REF_TYPE" != "tag" ] || [ -z "$$TAG" ]; then \
		TAG=$$(python3 -c 'from pathlib import Path; import tomllib; data=tomllib.loads(Path("$(FILE_PROJECT_TOML)").read_text(encoding="utf-8")); print(data.get("project", {}).get("version", "latest"))'); \
	fi; \
	echo "docker_image_tag=$$TAG" >> "$$GITHUB_OUTPUT"; \
	echo "Resolved Docker image tag: $$TAG"

## ci-docker-login        – Login to Docker Hub using DOCKERHUB_USERNAME and DOCKERHUB_TOKEN
.PHONY: ci-docker-login
ci-docker-login:
	@if [ -z "$$DOCKERHUB_USERNAME" ] || [ -z "$$DOCKERHUB_TOKEN" ]; then \
		echo "Error: DOCKERHUB_USERNAME and DOCKERHUB_TOKEN must be set."; \
		exit 1; \
	fi
	@echo "$$DOCKERHUB_TOKEN" | docker login --username "$$DOCKERHUB_USERNAME" --password-stdin

## ci-docker-build        – Build Docker image for DOCKER_IMAGE_TAG using project.mk Docker settings
.PHONY: ci-docker-build
ci-docker-build:
	@if [ -z "$$DOCKER_IMAGE_TAG" ]; then \
		echo "Error: DOCKER_IMAGE_TAG is not set."; \
		exit 1; \
	fi
	@if [ ! -f "$(CI_DOCKERFILE)" ]; then \
		echo "Error: Dockerfile not found at $(CI_DOCKERFILE)."; \
		exit 1; \
	fi
	docker build \
		-f "$(CI_DOCKERFILE)" \
		--build-arg PYTHON_VERSION="$(CI_DOCKER_PYTHON_VERSION)" \
		--build-arg UV_VERSION="$(CI_DOCKER_UV_VERSION)" \
		--build-arg PYTHON_MAIN_PACKAGE="$(PYTHON_MAIN_PACKAGE)" \
		--build-arg CI_DOCKER_ENTRYPOINT="$(CI_DOCKER_ENTRYPOINT)" \
		-t "$(CI_DOCKERHUB_IMAGE):$$DOCKER_IMAGE_TAG" \
		"$(CI_DOCKER_BUILD_CONTEXT)"

## ci-publish-dockerhub   – Build and push Docker image (and optional latest tag) to Docker Hub
.PHONY: ci-publish-dockerhub
ci-publish-dockerhub: ci-docker-build
	@docker push "$(CI_DOCKERHUB_IMAGE):$$DOCKER_IMAGE_TAG"
	@set -eu; \
	if [ "$(CI_DOCKER_PUSH_LATEST)" = "1" ]; then \
		docker tag "$(CI_DOCKERHUB_IMAGE):$$DOCKER_IMAGE_TAG" "$(CI_DOCKERHUB_IMAGE):latest"; \
		docker push "$(CI_DOCKERHUB_IMAGE):latest"; \
	fi

## ci-build-chocolatey-assets – Build Windows artefacts consumed by the Chocolatey package
.PHONY: ci-build-chocolatey-assets
ci-build-chocolatey-assets:
	$(MAKE) --no-print-directory ci-build-release-assets

## ci-pack-chocolatey     – Generate nuspec/install script and build a .nupkg in dist/chocolatey/
.PHONY: ci-pack-chocolatey
ci-pack-chocolatey:
	@set -eu; \
	VERSION=$$(uv version --short); \
	INSTALLER_URL=$$(uv run python -c 'import sys; print(sys.argv[1].replace("{version}", sys.argv[2]))' "$(CI_CHOCOLATEY_INSTALLER_URL)" "$$VERSION"); \
	mkdir -p .chocolatey/tools dist/chocolatey; \
	printf '%s\n' \
		'<?xml version="1.0" encoding="utf-8"?>' \
		'<package xmlns="http://schemas.microsoft.com/packaging/2015/06/nuspec.xsd">' \
		'  <metadata>' \
		'    <id>$(CI_CHOCOLATEY_PACKAGE_ID)</id>' \
		'    <version>'"$$VERSION"'</version>' \
		'    <title>$(CI_CHOCOLATEY_PACKAGE_TITLE)</title>' \
		'    <authors>$(CI_CHOCOLATEY_AUTHORS)</authors>' \
		'    <projectUrl>$(CI_CHOCOLATEY_PROJECT_URL)</projectUrl>' \
		'    <licenseUrl>$(CI_CHOCOLATEY_LICENSE_URL)</licenseUrl>' \
		'    <tags>$(CI_CHOCOLATEY_TAGS)</tags>' \
		'    <summary>$(CI_CHOCOLATEY_SUMMARY)</summary>' \
		'    <description>$(CI_CHOCOLATEY_DESCRIPTION)</description>' \
		'  </metadata>' \
		'  <files>' \
		'    <file src="tools\\**" target="tools" />' \
		'  </files>' \
		'</package>' > .chocolatey/$(CI_CHOCOLATEY_PACKAGE_ID).nuspec; \
	printf '%s\n' \
		'$$ErrorActionPreference = "Stop"' \
		'$$packageArgs = @{' \
		'  packageName    = "$(CI_CHOCOLATEY_PACKAGE_ID)"' \
		'  fileType       = "EXE"' \
		'  url64bit       = "'"$$INSTALLER_URL"'"' \
		'  silentArgs     = "$(CI_CHOCOLATEY_SILENT_ARGS)"' \
		'  validExitCodes = @($(CI_CHOCOLATEY_VALID_EXIT_CODES))' \
		'}' \
		'Install-ChocolateyPackage @packageArgs' > .chocolatey/tools/chocolateyinstall.ps1; \
	choco pack .chocolatey/$(CI_CHOCOLATEY_PACKAGE_ID).nuspec --outputdirectory dist/chocolatey --yes --limit-output

## ci-publish-chocolatey – Push generated .nupkg to Chocolatey source (requires CHOCOLATEY_API_KEY)
.PHONY: ci-publish-chocolatey
ci-publish-chocolatey:
	@if [ -z "$$CHOCOLATEY_API_KEY" ]; then \
		echo "Error: CHOCOLATEY_API_KEY is not set."; \
		exit 1; \
	fi
	@PACKAGE_FILE=$$(ls -1 dist/chocolatey/*.nupkg 2>/dev/null | grep -v '\\.symbols\\.nupkg$$' | head -n 1); \
	if [ -z "$$PACKAGE_FILE" ]; then \
		echo "Error: no .nupkg file found in dist/chocolatey. Run make ci-pack-chocolatey first."; \
		exit 1; \
	fi; \
	echo "Publishing $$PACKAGE_FILE to $(CI_CHOCOLATEY_SOURCE_URL)"; \
	choco push "$$PACKAGE_FILE" --source "$(CI_CHOCOLATEY_SOURCE_URL)" --api-key "$$CHOCOLATEY_API_KEY" --yes --limit-output

## ci-release-branch      – Print RELEASE_CHANGELOG_TARGET_BRANCH
.PHONY: ci-release-branch
ci-release-branch:
	@echo $(RELEASE_CHANGELOG_TARGET_BRANCH)

## ci-windows-installer   – Print ENABLE_WINDOWS_INSTALLER (1 or 0)
.PHONY: ci-windows-installer
ci-windows-installer:
	@echo $(ENABLE_WINDOWS_INSTALLER)

## ci-release-artifacts   – Print each RELEASE_ARTIFACTS glob pattern on its own line
.PHONY: ci-release-artifacts
ci-release-artifacts:
	@set -f; for pattern in $(RELEASE_ARTIFACTS); do printf '%s\n' "$$pattern"; done

## ci-print-release-target-branch – Legacy alias of ci-release-branch
.PHONY: ci-print-release-target-branch
ci-print-release-target-branch: ci-release-branch

## ci-print-windows-installer-enabled – Legacy alias of ci-windows-installer
.PHONY: ci-print-windows-installer-enabled
ci-print-windows-installer-enabled: ci-windows-installer

## ci-print-release-artifacts – Legacy alias of ci-release-artifacts
.PHONY: ci-print-release-artifacts
ci-print-release-artifacts: ci-release-artifacts

## ci-generate-homebrew-formula – Generate a Homebrew formula with the published PyPI source checksum
.PHONY: ci-generate-homebrew-formula
ci-generate-homebrew-formula:
	@set -eu; \
	VERSION=$$(uv version --short); \
	uv run python .mk/scripts.py gen-homebrew-formula \
		"$(FILE_PROJECT_TOML)" \
		"dist/homebrew/$(CI_HOMEBREW_FORMULA_NAME).rb" \
		"$$VERSION" \
		"$(CI_HOMEBREW_FORMULA_NAME)" \
		"$(CI_HOMEBREW_DESCRIPTION)" \
		"$(CI_HOMEBREW_HOMEPAGE)" \
		"$(CI_HOMEBREW_LICENSE)" \
		"$(CI_PYTHON_VERSION)" \
		"$(CI_HOMEBREW_EXECUTABLE)" $(if $(strip $(CI_HOMEBREW_RESOURCES_FILE)),--resources-file "$(CI_HOMEBREW_RESOURCES_FILE)",)

## ci-publish-homebrew – Push generated formula to the Homebrew tap repository
.PHONY: ci-publish-homebrew
ci-publish-homebrew:
	@set -eu; \
	if [ -z "$${HOMEBREW_TAP_TOKEN:-}" ]; then \
		echo "Error: HOMEBREW_TAP_TOKEN is not set."; exit 1; \
	fi; \
	FORMULA="dist/homebrew/$(CI_HOMEBREW_FORMULA_NAME).rb"; \
	if [ ! -f "$$FORMULA" ]; then \
		echo "Error: $$FORMULA not found. Run make ci-generate-homebrew-formula first."; exit 1; \
	fi; \
	VERSION=$$(uv version --short); \
	CLONE_DIR=$$(mktemp -d); \
	trap 'rm -rf "$$CLONE_DIR"' EXIT; \
	echo "[ci-publish-homebrew] Cloning tap $(CI_HOMEBREW_TAP_REPO)"; \
	git clone "https://x-access-token:$$HOMEBREW_TAP_TOKEN@github.com/$(CI_HOMEBREW_TAP_REPO).git" "$$CLONE_DIR"; \
	mkdir -p "$$CLONE_DIR/Formula"; \
	cp "$$FORMULA" "$$CLONE_DIR/Formula/$(CI_HOMEBREW_FORMULA_NAME).rb"; \
	cd "$$CLONE_DIR"; \
	git config user.name "github-actions[bot]"; \
	git config user.email "github-actions[bot]@users.noreply.github.com"; \
	git add "Formula/$(CI_HOMEBREW_FORMULA_NAME).rb"; \
	if git diff --cached --quiet; then \
		echo "[ci-publish-homebrew] Formula is already current for version $$VERSION."; exit 0; \
	fi; \
	git commit -m "$(CI_HOMEBREW_FORMULA_NAME): update to $$VERSION"; \
	git push; \
	echo "[ci-publish-homebrew] Formula pushed to $(CI_HOMEBREW_TAP_REPO)"

## ci-build-winget-assets  – Build Windows artefacts consumed by the WinGet manifests
.PHONY: ci-build-winget-assets
ci-build-winget-assets:
	$(MAKE) --no-print-directory ci-build-release-assets

## ci-generate-winget-manifests – Generate WinGet version/defaultLocale/installer manifests
.PHONY: ci-generate-winget-manifests
ci-generate-winget-manifests:
	@VERSION=$$(uv version --short); \
	INSTALLER_PATH="$(CI_WINGET_INSTALLER_FILE)"; \
	if [ ! -f "$$INSTALLER_PATH" ]; then \
		echo "Error: installer not found at $$INSTALLER_PATH. Run make ci-build-winget-assets first."; \
		exit 1; \
	fi; \
	INSTALLER_URL=$$(uv run python -c 'import sys; print(sys.argv[1].replace("{version}", sys.argv[2]))' "$(CI_WINGET_INSTALLER_URL)" "$$VERSION"); \
	printf '%s\n' \
		'from hashlib import sha256' \
		'import json' \
		'from pathlib import Path' \
		'import sys' \
		'' \
		'def q(value: str) -> str:' \
		'    return json.dumps(value, ensure_ascii=False)' \
		'' \
		'version = sys.argv[1]' \
		'package_identifier = sys.argv[2]' \
		'package_name = sys.argv[3]' \
		'publisher = sys.argv[4]' \
		'package_locale = sys.argv[5]' \
		'short_description = sys.argv[6]' \
		'license_name = sys.argv[7]' \
		'license_url = sys.argv[8]' \
		'homepage = sys.argv[9]' \
		'tags = [tag for tag in sys.argv[10].split() if tag]' \
		'installer_url = sys.argv[11]' \
		'installer_type = sys.argv[12]' \
		'installer_arch = sys.argv[13]' \
		'installer_path = Path(sys.argv[14])' \
		'manifest_version = sys.argv[15]' \
		'publisher_from_id, application_from_id = package_identifier.split(".", 1)' \
		'root = Path("dist") / "winget" / "manifests" / publisher_from_id[0].lower() / publisher_from_id / application_from_id / version' \
		'root.mkdir(parents=True, exist_ok=True)' \
		'installer_sha = sha256(installer_path.read_bytes()).hexdigest().upper()' \
		'version_lines = [' \
		'    f"# yaml-language-server: $$schema=https://aka.ms/winget-manifest.version.{manifest_version}.schema.json",' \
		'    f"PackageIdentifier: {q(package_identifier)}",' \
		'    f"PackageVersion: {q(version)}",' \
		'    f"DefaultLocale: {q(package_locale)}",' \
		'    "ManifestType: \"version\"",' \
		'    f"ManifestVersion: {q(manifest_version)}",' \
		']' \
		'default_locale_lines = [' \
		'    f"# yaml-language-server: $$schema=https://aka.ms/winget-manifest.defaultLocale.{manifest_version}.schema.json",' \
		'    f"PackageIdentifier: {q(package_identifier)}",' \
		'    f"PackageVersion: {q(version)}",' \
		'    f"PackageLocale: {q(package_locale)}",' \
		'    f"Publisher: {q(publisher)}",' \
		'    f"PackageName: {q(package_name)}",' \
		'    f"ShortDescription: {q(short_description)}",' \
		'    f"License: {q(license_name)}",' \
		'    f"LicenseUrl: {q(license_url)}",' \
		'    f"PublisherUrl: {q(homepage)}",' \
		'    f"PackageUrl: {q(homepage)}",' \
		']' \
		'if tags:' \
		'    default_locale_lines.append("Tags:")' \
		'    default_locale_lines.extend(f"- {q(tag)}" for tag in tags)' \
		'default_locale_lines.extend([' \
		'    "ManifestType: \"defaultLocale\"",' \
		'    f"ManifestVersion: {q(manifest_version)}",' \
		'])' \
		'installer_lines = [' \
		'    f"# yaml-language-server: $$schema=https://aka.ms/winget-manifest.installer.{manifest_version}.schema.json",' \
		'    f"PackageIdentifier: {q(package_identifier)}",' \
		'    f"PackageVersion: {q(version)}",' \
		'    "Installers:",' \
		'    f"- Architecture: {q(installer_arch)}",' \
		'    f"  InstallerType: {q(installer_type)}",' \
		'    f"  InstallerUrl: {q(installer_url)}",' \
		'    f"  InstallerSha256: {q(installer_sha)}",' \
		'    f"  InstallerLocale: {q(package_locale)}",' \
		'    "ManifestType: \"installer\"",' \
		'    f"ManifestVersion: {q(manifest_version)}",' \
		']' \
		'(root / f"{package_identifier}.yaml").write_text("\n".join(version_lines) + "\n", encoding="utf-8")' \
		'(root / f"{package_identifier}.locale.{package_locale}.yaml").write_text("\n".join(default_locale_lines) + "\n", encoding="utf-8")' \
		'(root / f"{package_identifier}.installer.yaml").write_text("\n".join(installer_lines) + "\n", encoding="utf-8")' \
		'print(f"Generated WinGet manifests in {root}")' \
	| uv run python - \
		"$$VERSION" \
		"$(CI_WINGET_PACKAGE_IDENTIFIER)" \
		"$(CI_WINGET_PACKAGE_NAME)" \
		"$(CI_WINGET_PUBLISHER)" \
		"$(CI_WINGET_PACKAGE_LOCALE)" \
		"$(CI_WINGET_SHORT_DESCRIPTION)" \
		"$(CI_WINGET_LICENSE)" \
		"$(CI_WINGET_LICENSE_URL)" \
		"$(CI_WINGET_HOMEPAGE)" \
		"$(CI_WINGET_TAGS)" \
		"$$INSTALLER_URL" \
		"$(CI_WINGET_INSTALLER_TYPE)" \
		"$(CI_WINGET_INSTALLER_ARCHITECTURE)" \
		"$$INSTALLER_PATH" \
		"$(CI_WINGET_MANIFEST_VERSION)"

## ci-validate-winget-manifests – Validate generated WinGet manifests when winget is available
.PHONY: ci-validate-winget-manifests
ci-validate-winget-manifests:
	@VERSION=$$(uv version --short); \
	MANIFEST_DIR=$$(uv run python -c 'import sys; publisher, app = sys.argv[1].split(".", 1); print(f"dist/winget/manifests/{publisher[0].lower()}/{publisher}/{app}/{sys.argv[2]}")' "$(CI_WINGET_PACKAGE_IDENTIFIER)" "$$VERSION"); \
	if [ ! -d "$$MANIFEST_DIR" ]; then \
		echo "Error: $$MANIFEST_DIR not found. Run make ci-generate-winget-manifests first."; \
		exit 1; \
	fi; \
	WINGET_BIN=$$(command -v winget 2>/dev/null || command -v winget.exe 2>/dev/null || true); \
	if [ -z "$$WINGET_BIN" ]; then \
		echo "[ci-validate-winget-manifests] winget is not available on this runner -> skipping validation."; \
	else \
		echo "[ci-validate-winget-manifests] Validating $$MANIFEST_DIR"; \
		"$$WINGET_BIN" validate "$$MANIFEST_DIR"; \
	fi

## ci-publish-winget – Push generated manifests to your winget-pkgs fork and open/update a PR
.PHONY: ci-publish-winget
ci-publish-winget:
	@set -eu; \
	if [ -z "$${WINGET_GITHUB_TOKEN:-}" ]; then \
		echo "Error: WINGET_GITHUB_TOKEN is not set."; exit 1; \
	fi; \
	VERSION=$$(uv version --short); \
	SOURCE_DIR=$$(uv run python -c 'import sys; publisher, app = sys.argv[1].split(".", 1); print(f"dist/winget/manifests/{publisher[0].lower()}/{publisher}/{app}/{sys.argv[2]}")' "$(CI_WINGET_PACKAGE_IDENTIFIER)" "$$VERSION"); \
	TARGET_PATH=$$(uv run python -c 'import sys; publisher, app = sys.argv[1].split(".", 1); print(f"manifests/{publisher[0].lower()}/{publisher}/{app}/{sys.argv[2]}")' "$(CI_WINGET_PACKAGE_IDENTIFIER)" "$$VERSION"); \
	BRANCH=$$(uv run python -c 'import re, sys; slug = re.sub(r"[^A-Za-z0-9]+", "-", sys.argv[1]).strip("-").lower(); print(f"winget-{slug}-{sys.argv[2]}")' "$(CI_WINGET_PACKAGE_IDENTIFIER)" "$$VERSION"); \
	FORK_REPO="$(CI_WINGET_FORK_REPO)"; \
	FORK_OWNER=$${FORK_REPO%%/*}; \
	if [ ! -d "$$SOURCE_DIR" ]; then \
		echo "Error: $$SOURCE_DIR not found. Run make ci-generate-winget-manifests first."; exit 1; \
	fi; \
	CLONE_DIR=$$(mktemp -d); \
	trap 'rm -rf "$$CLONE_DIR"' EXIT; \
	echo "[ci-publish-winget] Cloning fork $$FORK_REPO"; \
	git clone --filter=blob:none --no-checkout "https://x-access-token:$$WINGET_GITHUB_TOKEN@github.com/$$FORK_REPO.git" "$$CLONE_DIR"; \
	cd "$$CLONE_DIR"; \
	git sparse-checkout init --cone; \
	git sparse-checkout set "$$TARGET_PATH"; \
	DEFAULT_BRANCH=$$(GH_TOKEN="$$WINGET_GITHUB_TOKEN" gh repo view "$$FORK_REPO" --json defaultBranchRef --jq '.defaultBranchRef.name'); \
	if git ls-remote --exit-code --heads origin "$$BRANCH" >/dev/null 2>&1; then \
		git fetch origin "refs/heads/$$BRANCH:refs/remotes/origin/$$BRANCH"; \
		git checkout -B "$$BRANCH" "refs/remotes/origin/$$BRANCH"; \
	else \
		git fetch origin "refs/heads/$$DEFAULT_BRANCH:refs/remotes/origin/$$DEFAULT_BRANCH"; \
		git checkout -B "$$BRANCH" "refs/remotes/origin/$$DEFAULT_BRANCH"; \
	fi; \
	mkdir -p "$$TARGET_PATH"; \
	cp "$$SOURCE_DIR"/* "$$TARGET_PATH"/; \
	git config user.name "github-actions[bot]"; \
	git config user.email "github-actions[bot]@users.noreply.github.com"; \
	git add "$$TARGET_PATH"; \
	if git diff --cached --quiet; then \
		echo "[ci-publish-winget] Manifests are already current for version $$VERSION."; exit 0; \
	fi; \
	git commit -m "Add $(CI_WINGET_PACKAGE_IDENTIFIER) version $$VERSION"; \
	git push --set-upstream origin "$$BRANCH"; \
	EXISTING_PR=$$(GH_TOKEN="$$WINGET_GITHUB_TOKEN" gh pr list --repo microsoft/winget-pkgs --head "$$FORK_OWNER:$$BRANCH" --state open --json number --jq '.[0].number // empty'); \
	if [ -n "$$EXISTING_PR" ]; then \
		GH_TOKEN="$$WINGET_GITHUB_TOKEN" gh pr edit "$$EXISTING_PR" --repo microsoft/winget-pkgs \
			--title "Add $(CI_WINGET_PACKAGE_IDENTIFIER) version $$VERSION" \
			--body "Automated manifest submission generated from the template release workflow."; \
	else \
		GH_TOKEN="$$WINGET_GITHUB_TOKEN" gh pr create --repo microsoft/winget-pkgs \
			--head "$$FORK_OWNER:$$BRANCH" \
			--title "Add $(CI_WINGET_PACKAGE_IDENTIFIER) version $$VERSION" \
			--body "Automated manifest submission generated from the template release workflow."; \
	fi; \
	echo "[ci-publish-winget] Manifest branch pushed and PR updated for $(CI_WINGET_PACKAGE_IDENTIFIER) $$VERSION"
