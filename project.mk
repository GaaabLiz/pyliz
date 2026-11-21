# ==============================================================================
#
#  _____  _____   ____       _ ______ _____ _______
# |  __ \|  __ \ / __ \     | |  ____/ ____|__   __|
# | |__) | |__) | |  | |    | | |__ | |       | |
# |  ___/|  _  /| |  | |_   | |  __|| |       | |
# | |    | | \ \| |__| | |__| | |___| |____   | |
# |_|    |_|  \_\\____/ \____/|______\_____|  |_|
#
#   _____ ____  _   _ ______ _____ _____
#  / ____/ __ \| \ | |  ____|_   _/ ____|
# | |   | |  | |  \| | |__    | || |  __
# | |   | |  | | . ` |  __|   | || | |_ |
# | |___| |__| | |\  | |     _| || |__| |
#  \_____\____/|_| \_|_|    |_____\_____|
#
#                     PROJECT CONFIGURATION FILE
#
#  ► Edit THIS file to customise your project.
#  ► Shared commands are implemented in Makefile and the modules under .mk/.
#
#  Override project defaults from the command line:
#      make build PYTHON_MAIN_PACKAGE=mypkg
#
#  Optional modules
#  ─────────────────────────────────────────────────────────────────────────────
#  Uncomment the include line at the bottom of this file to activate extra
#  make targets for specific technology stacks:
#    qt.mk  – PySide6/PyQt resource compilation  (gen-qt-res-py target)
#
# ==============================================================================


# ==============================================================================
#  1. PROJECT IDENTITY AND METADATA
#
#  Importable package and paths used to generate package metadata.
# ==============================================================================

# Importable package directory. Use the same directory in the wheel
# configuration in pyproject.toml.
PYTHON_MAIN_PACKAGE ?= pylizlib

# Path to the pyproject.toml at the root of the repository.
FILE_PROJECT_TOML ?= pyproject.toml

# Destination path for the auto-generated Python module that mirrors the
# pyproject.toml metadata (name, version, authors, …) as Python constants.
# The gen-project-module target writes to this path at build time.
FILE_PROJECT_PY_GENERATED ?= $(PYTHON_MAIN_PACKAGE)/project.py


# ==============================================================================
#  2. DEVELOPMENT AND QUALITY
#
#  Test paths, coverage thresholds, and tool configuration files.
# ==============================================================================

# Directory (or pytest arguments) used by make test, make test-cov, and CI.
# Examples:
#   tests
#   tests/unit
#   tests/unit tests/integration
TESTS_PATH ?= test

# Minimum code coverage threshold (percentage) required by test-cov-verify.
MIN_COVERAGE ?= 80

# Configuration files used by Ruff and ty.
RUFF_CONFIG_FILE ?= ruff.toml
TY_CONFIG_FILE ?= ty.toml


# ==============================================================================
#  3. CONTINUOUS INTEGRATION
#
#  Tool versions, test runners, and quality checks used by CI.
# ==============================================================================

# Single Python version used by CI tests, quality checks, builds, and release assets.
CI_PYTHON_VERSION ?= 3.13

# The previous template tested both Python 3.12 and 3.13. The current template
# runs one fixed version across the OS matrix; keep the old settings for reference.
# CI_PYTHON_VERSIONS ?= ["3.12", "3.13"]
# CI_AI_IMPORT_CHECK ?= uv run --locked --extra ai python -c 'import easyocr, huggingface_hub, nudenet, onnxruntime, torch, torchvision; from pylizlib.ai import AiMediaScanner'
# CI_AI_IMPORT_SUFFIX ?= $(if $(and $(filter Linux,$(RUNNER_OS)),$(filter 3.12,$(CI_PYTHON_VERSION))),&& $(CI_AI_IMPORT_CHECK),)

# Operating systems used for the test job. Python stays fixed at CI_PYTHON_VERSION.
CI_TEST_OS_MATRIX ?= ["ubuntu-latest", "macos-latest", "windows-latest"]

# Pin uv so upstream releases cannot silently change CI behavior.
CI_UV_VERSION ?= 0.13.6

# Select the quality targets to run in CI. Add `type-check` if the project uses ty.
CI_QUALITY_TARGETS ?= lint format-check

# Override this for unittest, nox, tox, or a project-specific test runner.
CI_TEST_COMMAND ?= uv run --group docs --extra media --extra qt --extra qtfw pytest $(TESTS_PATH)


# ==============================================================================
#  4. STANDALONE APPLICATIONS
#
#  PyInstaller applications and the platforms to build on release.
# ==============================================================================

# Enable/disable per-platform executable/installer builds in the release workflow.
# Python wheel and sdist builds run once in the reusable CI gate.
# Set a platform to 1 only when APPS_LIST or the Windows installer is configured.
CI_BUILD_LINUX ?= 0
CI_BUILD_MACOS ?= 0
CI_BUILD_WINDOWS ?= 0

# Space-separated list of logical application identifiers to build.
# For each entry <id> you MUST define the four companion variables below.
#
# Leave empty for pure wheel/sdist projects.
# Set it only when you want CI/release jobs to build PyInstaller executables too.
APPS_LIST ?=

# Set to 1 only for GUI apps; CLI applications should keep a visible console.
PYINSTALLER_WINDOWED ?= 0

# ── Template – copy and fill in one block per entry in APPS_LIST ──────────────
#
# Replace <id> with the actual identifier (must match the entry in APPS_LIST).
#
#   <id>_NAME  := <id>                            # Output binary name (no extension)
#   <id>_MAIN  := $(PYTHON_MAIN_PACKAGE)/cli.py   # Entry-point script for PyInstaller
#   <id>_ICO   := resources/logo.ico              # Windows icon (.ico)
#   <id>_ICNS  := resources/logo.icns             # macOS  icon (.icns)
#
# Example (single CLI app):
#   APPS_LIST      := myapp
#   myapp_NAME     := myapp
#   myapp_MAIN     := myapp/__main__.py
#   myapp_ICO      := resources/logo.ico
#   myapp_ICNS     := resources/logo.icns


# ==============================================================================
#  5. WINDOWS INSTALLER
#
#  Inno Setup configuration and installer output.
# ==============================================================================

# Set to 1 to enable the Windows installer step in CI, or 0 to skip it.
# When enabled, the build generates the Inno Setup script at INNO_SETUP_FILE.
ENABLE_WINDOWS_INSTALLER ?= 0

# Path to the generated Inno Setup script (.iss) for the Windows installer.
INNO_SETUP_FILE ?= installer.iss

# Name of the #define inside the .iss file that holds the application version
# string.  The release bump targets update this value automatically via sed.
INNO_SETUP_VERSION_VARIABLE ?= MyAppVersion

# Display name shown in the installer UI (e.g., "My App").
INNO_APP_NAME ?= pyliz

# Publisher/company name shown in installer metadata.
INNO_APP_PUBLISHER ?= Your Company

# Relative path (from repo root) to the app icon used by SetupIconFile.
# Must point to a .ico file for Windows installers.
INNO_APP_ICON ?= resources/icon.ico

# One-file executable that the installer packages.
INNO_APP_EXE ?= dist/pyliz-windows.exe

# Default install directory under Program Files.
# Typical value: {autopf}\My App
INNO_DEFAULT_DIR_NAME ?= {autopf}\$(INNO_APP_NAME)

# Default Start Menu group/folder name.
INNO_DEFAULT_GROUP_NAME ?= $(INNO_APP_NAME)

# Directory where Inno Setup writes the generated installer .exe.
INNO_OUTPUT_DIR ?= Output

# Base filename (without extension) for the generated installer.
INNO_OUTPUT_BASE_FILENAME ?= $(PYTHON_MAIN_PACKAGE)-setup

# Compression mode used by Inno Setup for packaged files.
INNO_COMPRESSION ?= lzma

# Enable modern solid compression mode (yes/no).
INNO_SOLID_COMPRESSION ?= yes


# ==============================================================================
#  6. RELEASE AND API DOCUMENTATION
#
#  Release branch, artifacts, release notes, and the optional docs PR.
# ==============================================================================

# Branch that release tags must belong to and optional API-documentation PRs target.
# Preserve the previous project setting; the Makefile maps it to RELEASE_TARGET_BRANCH.
RELEASE_CHANGELOG_TARGET_BRANCH ?= main
ifeq ($(origin RELEASE_TARGET_BRANCH),undefined)
ifneq ($(origin RELEASE_CHANGELOG_TARGET_BRANCH),undefined)
RELEASE_TARGET_BRANCH = $(RELEASE_CHANGELOG_TARGET_BRANCH)
else
RELEASE_TARGET_BRANCH = main
endif
endif
# Backwards-compatible alias for projects created from earlier template versions.
RELEASE_CHANGELOG_TARGET_BRANCH ?= $(RELEASE_TARGET_BRANCH)

# Files or globs to attach to the GitHub Release. Quote paths with spaces.
# For an installer in the default output directory, use dist/* Output/*.exe.
RELEASE_ARTIFACTS ?= dist/*

# The previous workflow generated CHANGELOG.md through CI_CHANGELOG_FILE. The
# current workflow writes per-release notes and leaves the existing changelog in place.
# Legacy setting (no longer consumed): CI_CHANGELOG_FILE ?= CHANGELOG.md
# Per-release notes are generated in CI, attached to GitHub Releases, and added to PyPI package descriptions.
CI_RELEASE_NOTES_FILE ?= RELEASE_NOTES.md

# git-cliff configuration file used by CI release targets.
CI_GIT_CLIFF_CONFIG ?= cliff.toml

# Pin the release-notes generator so tag releases use reproducible tooling.
CI_GIT_CLIFF_VERSION ?= 2.14.2

# Enable/disable API docs generation during the release workflow.
# When enabled, CI opens a separate pull request for generated docs/api/ pages.
CI_ENABLE_RELEASE_DOCS ?= 0

# pdoc docstring format used by make docs and the project-specific docs-snap target.
PDOC_DOCFORMAT ?= google


# ==============================================================================
#  7. PUBLISHING
#
#  Settings for the optional publishing destinations. See docs/publishing-*.md.
# ==============================================================================

# Repository URL used for publisher metadata and default download links.
PROJECT_REPOSITORY_URL ?= https://github.com/your-org/your-repo

# Default download URL for the Windows installer. Keep the {version} placeholder.
CI_RELEASE_INSTALLER_URL ?= $(PROJECT_REPOSITORY_URL)/releases/download/v{version}/$(INNO_OUTPUT_BASE_FILENAME).exe

#  7.1 PYPI
#  -------------------------------------------------------------------------

# Enable/disable automated publication to PyPI after a verified release tag.
# The release workflow accepts the existing PYPI_API_TOKEN and supports trusted publishing.
CI_ENABLE_PYPI_PUBLISH ?= 1

# GitHub Actions environment name used by the PyPI publish workflow.
CI_PYPI_ENVIRONMENT ?= pypi

#  7.2 DOCKER HUB
#  -------------------------------------------------------------------------

# Enable/disable Docker image publication to Docker Hub on release tags.
# Keep this at 0 until Docker Hub repository and GitHub secrets are configured.
CI_ENABLE_DOCKERHUB_PUBLISH ?= 0

# GitHub Actions environment name used by the Docker Hub publish workflow.
CI_DOCKERHUB_ENVIRONMENT ?= dockerhub

# Full Docker Hub image name in the form: <namespace>/<repository>.
# Example: gaaabliz/myapp
CI_DOCKERHUB_IMAGE ?= your-dockerhub-user/your-image

# Path to the Dockerfile used for image builds.
CI_DOCKERFILE ?= Dockerfile

# Command that starts the application inside the container.
# Examples: python -m myapp, myapp
CI_DOCKER_ENTRYPOINT ?= python -m $(PYTHON_MAIN_PACKAGE)

# Python and uv versions used by the sample Dockerfile.
CI_DOCKER_PYTHON_VERSION ?= $(CI_PYTHON_VERSION)
CI_DOCKER_UV_VERSION ?= $(CI_UV_VERSION)

# Build context path passed to `docker build`.
CI_DOCKER_BUILD_CONTEXT ?= .

# Also push the `latest` tag during release publication (1=yes, 0=no).
CI_DOCKER_PUSH_LATEST ?= 1

#  7.3 CHOCOLATEY
#  -------------------------------------------------------------------------

# Enable/disable automated publication to Chocolatey on version tags.
# Keep this at 0 until CHOCOLATEY_API_KEY is configured in GitHub secrets.
CI_ENABLE_CHOCOLATEY_PUBLISH ?= 0

# GitHub Actions environment name used by the Chocolatey publish workflow.
CI_CHOCOLATEY_ENVIRONMENT ?= chocolatey

# Chocolatey package metadata.
CI_CHOCOLATEY_PACKAGE_ID ?= myapp
CI_CHOCOLATEY_PACKAGE_TITLE ?= My App
CI_CHOCOLATEY_AUTHORS ?= Your Name
CI_CHOCOLATEY_PROJECT_URL ?= $(PROJECT_REPOSITORY_URL)
CI_CHOCOLATEY_LICENSE_URL ?= $(PROJECT_REPOSITORY_URL)/blob/main/UNLICENSE
CI_CHOCOLATEY_TAGS ?= python cli

# Human-readable metadata shown on Chocolatey package page.
CI_CHOCOLATEY_SUMMARY ?= Windows package for $(INNO_APP_NAME)
CI_CHOCOLATEY_DESCRIPTION ?= $(INNO_APP_NAME) packaged from the GitHub release artifacts.

# Installer artifact and install-script settings.
# CI_CHOCOLATEY_INSTALLER_URL supports the {version} placeholder.
CI_CHOCOLATEY_INSTALLER_URL ?= $(CI_RELEASE_INSTALLER_URL)
CI_CHOCOLATEY_SILENT_ARGS ?= /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-
CI_CHOCOLATEY_VALID_EXIT_CODES ?= 0 3010 1641

# Chocolatey push endpoint. Default is the community feed.
CI_CHOCOLATEY_SOURCE_URL ?= https://push.chocolatey.org/

#  7.4 HOMEBREW
#  -------------------------------------------------------------------------

# Enable/disable automated publication to a Homebrew tap on version tags.
# Keep this at 0 until HOMEBREW_TAP_TOKEN is configured in GitHub secrets.
CI_ENABLE_HOMEBREW_PUBLISH ?= 0

# GitHub Actions environment name used by the Homebrew publish workflow.
CI_HOMEBREW_ENVIRONMENT ?= homebrew

# Homebrew tap repository in the form: <owner>/homebrew-<tap>.
# You must create this repository on GitHub before enabling publication.
# Example: your-org/homebrew-tap
CI_HOMEBREW_TAP_REPO ?= your-org/homebrew-tap

# Formula name as it will appear in the tap (without .rb extension).
CI_HOMEBREW_FORMULA_NAME ?= myapp

# Homepage URL shown in the formula metadata.
CI_HOMEBREW_HOMEPAGE ?= $(PROJECT_REPOSITORY_URL)

# Short description shown by `brew info`.
CI_HOMEBREW_DESCRIPTION ?= A Python CLI application

# License code used in the formula, for example MIT.
CI_HOMEBREW_LICENSE ?=

# Optional console script used for the formula's `--version` smoke check.
# Leave empty to verify the installed distribution metadata instead.
CI_HOMEBREW_EXECUTABLE ?=

# Optional file listing download details for the Python packages your app needs.
# Required when pyproject.toml declares runtime dependencies.
CI_HOMEBREW_RESOURCES_FILE ?=

#  7.5 WINGET
#  -------------------------------------------------------------------------

# Enable/disable automated publication of WinGet manifests on version tags.
# Keep this at 0 until WINGET_GITHUB_TOKEN is configured in GitHub secrets.
CI_ENABLE_WINGET_PUBLISH ?= 0

# GitHub Actions environment name used by the WinGet publish workflow.
CI_WINGET_ENVIRONMENT ?= winget

# Fork of microsoft/winget-pkgs where the workflow pushes the generated branch.
# Create this fork manually on GitHub before enabling publication.
# Example: your-github-user/winget-pkgs
CI_WINGET_FORK_REPO ?= your-github-user/winget-pkgs

# Unique WinGet identifier in Publisher.Package format.
CI_WINGET_PACKAGE_IDENTIFIER ?= YourCompany.MyApp

# Metadata shown by `winget show` and in the community repository.
CI_WINGET_PACKAGE_NAME ?= $(INNO_APP_NAME)
CI_WINGET_PUBLISHER ?= $(INNO_APP_PUBLISHER)
CI_WINGET_PACKAGE_LOCALE ?= en-US
CI_WINGET_SHORT_DESCRIPTION ?= Windows installer for $(INNO_APP_NAME)
CI_WINGET_LICENSE ?=
CI_WINGET_LICENSE_URL ?=
CI_WINGET_HOMEPAGE ?= $(PROJECT_REPOSITORY_URL)
CI_WINGET_TAGS ?= python cli

# Installer manifest settings. CI_WINGET_INSTALLER_URL supports {version}.
CI_WINGET_INSTALLER_URL ?= $(CI_RELEASE_INSTALLER_URL)
CI_WINGET_INSTALLER_TYPE ?= inno
CI_WINGET_INSTALLER_ARCHITECTURE ?= x64
CI_WINGET_INSTALLER_FILE ?= $(INNO_OUTPUT_DIR)/$(INNO_OUTPUT_BASE_FILENAME).exe

# WinGet manifest schema version used for generated YAML files.
CI_WINGET_MANIFEST_VERSION ?= 1.12.0


# ==============================================================================
#  8. OPTIONAL MODULES
#
#  Uncomment the include for any additional Make module you need.
# ==============================================================================

# ── Qt / PySide6 ─────────────────────────────────────────────────────────────
# Provides the `gen-qt-res-py` target for compiling .qrc resource files.
# Configure the variables in qt.mk before including it.
#
# include qt.mk
