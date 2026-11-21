# ==============================================================================
#
#    _____ _____   _    _ ______ _      _____  ______ _____   _____
#   / ____|_   _| | |  | |  ____| |    |  __ \|  ____|  __ \ / ____|
#  | |      | |   | |__| | |__  | |    | |__) | |__  | |__) | (___
#  | |      | |   |  __  |  __| | |    |  ___/|  __| |  _  / \___ \
#  | |____ _| |_  | |  | | |____| |____| |    | |____| | \ \ ____) |
#   \_____|_____| |_|  |_|______|______|_|    |______|_|  \_\_____/
#
#  Set up CI environments and validate and export project settings.
# ==============================================================================

ci_config_targets := ci-log-config ci-validate-config ci-export-config
# Keep every CI target on its configured interpreter, even when .python-version
# selects a different version for local development.
ci-%: export UV_PYTHON = $(CI_PYTHON_VERSION)

CI_CONFIG_INSTALLER_PATH = $(INNO_OUTPUT_DIR)/$(INNO_OUTPUT_BASE_FILENAME).exe
CI_CONFIG_RELEASE_NOTES_FILENAME = $(notdir $(CI_RELEASE_NOTES_FILE))
windows_app_executables = $(foreach app,$(APPS_LIST),$(call app_executable_path,$(app),windows))

ci_config_vars := \
	APPS_LIST \
	CI_BUILD_LINUX \
	CI_BUILD_MACOS \
	CI_BUILD_WINDOWS \
	CI_CHOCOLATEY_ENVIRONMENT \
	CI_CHOCOLATEY_INSTALLER_URL \
	CI_CHOCOLATEY_LICENSE_URL \
	CI_CHOCOLATEY_PROJECT_URL \
	CI_CONFIG_INSTALLER_PATH \
	CI_CONFIG_RELEASE_NOTES_FILENAME \
	CI_DOCKERHUB_ENVIRONMENT \
	CI_DOCKERHUB_IMAGE \
	CI_DOCKER_ENTRYPOINT \
	CI_DOCKER_PUSH_LATEST \
	CI_ENABLE_CHOCOLATEY_PUBLISH \
	CI_ENABLE_DOCKERHUB_PUBLISH \
	CI_ENABLE_HOMEBREW_PUBLISH \
	CI_ENABLE_PYPI_PUBLISH \
	CI_ENABLE_RELEASE_DOCS \
	CI_ENABLE_WINGET_PUBLISH \
	CI_HOMEBREW_ENVIRONMENT \
	CI_HOMEBREW_HOMEPAGE \
	CI_HOMEBREW_LICENSE \
	CI_HOMEBREW_RESOURCES_FILE \
	CI_HOMEBREW_TAP_REPO \
	CI_PYPI_ENVIRONMENT \
	CI_PYTHON_VERSION \
	CI_QUALITY_TARGETS \
	CI_RELEASE_NOTES_FILE \
	CI_TEST_COMMAND \
	CI_TEST_OS_MATRIX \
	CI_UV_VERSION \
	CI_WINGET_ENVIRONMENT \
	CI_WINGET_FORK_REPO \
	CI_WINGET_HOMEPAGE \
	CI_WINGET_INSTALLER_FILE \
	CI_WINGET_INSTALLER_URL \
	CI_WINGET_LICENSE \
	CI_WINGET_LICENSE_URL \
	CI_WINGET_PACKAGE_IDENTIFIER \
	ENABLE_WINDOWS_INSTALLER \
	FILE_PROJECT_TOML \
	PYINSTALLER_WINDOWED \
	PYTHON_MAIN_PACKAGE \
	RELEASE_ARTIFACTS \
	TESTS_PATH

# Export the effective values only when a configuration target runs.
$(foreach var,$(ci_config_vars),\
	$(eval $(ci_config_targets): export TEMPLATE_SETTING_$(var) = $$($(var))))

## ci-log-config          – Print the project settings that drive CI and release automation
.PHONY: ci-log-config
ci-log-config:
	@if python3 -c 'import tomllib' >/dev/null 2>&1; then \
		python3 .mk/scripts.py ci-config log; \
	else \
		uv run --no-project --python '>=3.11' python .mk/scripts.py ci-config log; \
	fi

# Include build dependencies when both setup targets are requested together.
ci_setup_extra_groups = $(if $(filter ci-setup-build,$(MAKECMDGOALS)),--group build)

## ci-setup               – Prepare CI environment (install Python via uv + sync the dev group)
.PHONY: ci-setup
ci-setup:
	@echo "[ci-setup] Installing Python $(CI_PYTHON_VERSION) via uv"
	uv python install $(CI_PYTHON_VERSION)
	@echo "[ci-setup] Syncing the project and dev dependencies$(if $(ci_setup_extra_groups), and PyInstaller)"
	uv sync --group dev $(ci_setup_extra_groups) --python $(CI_PYTHON_VERSION) --locked
	@echo "[ci-setup] Tool versions"
	uv --version
	uv run --no-sync python --version

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

## ci-validate-config    – Validate the CI Python version, OS matrix, and publication dependencies
.PHONY: ci-validate-config
ci-validate-config:
	@python3 .mk/scripts.py ci-config validate
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
		case " $(windows_app_executables) " in \
			*" $(INNO_APP_EXE) "*) ;; \
			*) echo "Error: INNO_APP_EXE must match one of the configured PyInstaller outputs ($(windows_app_executables))."; exit 1 ;; \
		esac; \
	fi

## ci-setup-build         – Prepare CI environment with dev and PyInstaller dependencies
.PHONY: ci-setup-build
ci-setup-build: ci_setup_extra_groups = --group build
ci-setup-build: ci-setup

## ci-export-config       – Export CI configuration values to $GITHUB_OUTPUT
.PHONY: ci-export-config
ci-export-config: ci-validate-config
	@python3 .mk/scripts.py ci-config export
