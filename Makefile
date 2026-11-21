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
#  Command modules
#  ─────────────────────────────────────────────────────────────────────────────
#    .mk/dev.mk       Environment setup, quality checks, tests, and API docs
#    .mk/build.mk     Metadata, packages, executables, installers, and cleanup
#    .mk/ci.mk        CI setup, validation, and configuration export
#    .mk/release.mk   Version bumps, tags, release notes, and assets
#    .mk/publish.mk   PyPI, Docker Hub, Chocolatey, Homebrew, and WinGet
#
# ==============================================================================

.DEFAULT_GOAL := help

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

include .mk/dev.mk .mk/build.mk .mk/ci.mk .mk/release.mk .mk/publish.mk
