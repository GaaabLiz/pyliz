# ==============================================================================
#
#   ____  _    _ _____ _      _____
#  |  _ \| |  | |_   _| |    |  __ \
#  | |_) | |  | | | | | |    | |  | |
#  |  _ <| |  | | | | | |    | |  | |
#  | |_) | |__| |_| |_| |____| |__| |
#  |____/ \____/|_____|______|_____/
#
#  Generate project files and build packages, executables, and installers.
# ==============================================================================

app_binary_name = $(or $($(1)_NAME),$(1))-$(2)
app_executable_path = dist/$(call app_binary_name,$(1),$(2))$(if $(filter windows,$(2)),.exe)
builds_macos_bundle = $(and $(filter macos,$(1)),$(filter 1,$(PYINSTALLER_WINDOWED)))
app_bundle_path = $(call app_executable_path,$(1),macos).app
app_release_path = $(if $(call builds_macos_bundle,$(2)),$(call app_bundle_path,$(1)).zip,$(call app_executable_path,$(1),$(2)))

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

## build                – Full build: clean → gen-project-module → uv build
.PHONY: build
build: clean
	$(MAKE) --no-print-directory gen-project-module
	$(MAKE) --no-print-directory build-uv
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
## build-exe-onefile    – Build single-file executables with PyInstaller for each app in APPS_LIST
.PHONY: build-exe build-exe-onefile
build-exe build-exe-onefile:
	@set -eu; \
	if [ -z "$(strip $(APPS_LIST))" ]; then \
		echo "[$@] APPS_LIST is empty. Skipping PyInstaller builds."; \
		echo "[$@] Configure APPS_LIST and the app settings in project.mk to enable executables."; \
	else \
		echo "[$@] Building PyInstaller apps: $(APPS_LIST)"; \
		$(foreach app,$(APPS_LIST),\
			uv run pyinstaller --noconfirm $(if $(filter 1,$(PYINSTALLER_WINDOWED)),--windowed,) \
				$(if $(filter build-exe-onefile,$@),--onefile) \
				$(if $(filter macos,$(OS_NAME)),--icon="$($(app)_ICNS)",$(if $(filter windows,$(OS_NAME)),--icon="$($(app)_ICO)")) \
				--name="$(call app_binary_name,$(app),$(OS_NAME))" \
				"$($(app)_MAIN)"; \
		) \
		echo "[$@] PyInstaller build completed."; \
	fi

## build-app            – Full app build: clean → gen-project-module → uv build → build-exe
.PHONY: build-app
build-app: build
	$(MAKE) --no-print-directory build-exe

## build-app-onefile    – Full app build using the --onefile PyInstaller mode
.PHONY: build-app-onefile
build-app-onefile: build
	$(MAKE) --no-print-directory build-exe-onefile

## installer            – Run Inno Setup to produce the Windows installer (Windows only)
.PHONY: installer
installer: gen-inno-iss
ifeq ($(filter Darwin Linux,$(UNAME_S)),)
	ISCC.exe "$(INNO_SETUP_FILE)"
else
	@echo "Error: The installer target can only be run on Windows."
	@exit 1
endif

## build-installer      – Full pipeline including the Windows installer step
.PHONY: build-installer
build-installer: build-app-onefile
	$(MAKE) --no-print-directory installer

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

## clean-generated      – Remove only the auto-generated Python source files
.PHONY: clean-generated
clean-generated:
	@echo "Cleaning generated files..."
	- rm -f $(FILE_PROJECT_PY_GENERATED)

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

## ci-smoke-build        – Install each wheel and sdist in isolation and import the package
.PHONY: ci-smoke-build
ci-smoke-build:
	uv run python .mk/scripts.py smoke-install-artifacts dist "$(PYTHON_MAIN_PACKAGE)"
