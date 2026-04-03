#    $$\      $$\  $$$$$$\  $$\   $$\ $$$$$$$$\ $$$$$$$$\ $$$$$$\ $$\       $$$$$$$$\
#    $$$\    $$$ |$$  __$$\ $$ | $$  |$$  _____|$$  _____|\_$$  _|$$ |      $$  _____|
#    $$$$\  $$$$ |$$ /  $$ |$$ |$$  / $$ |      $$ |        $$ |  $$ |      $$ |
#    $$\$$\$$ $$ |$$$$$$$$ |$$$$$  /  $$$$$\    $$$$$\      $$ |  $$ |      $$$$$\
#    $$ \$$$  $$ |$$  __$$ |$$  $$<   $$  __|   $$  __|     $$ |  $$ |      $$  __|
#    $$ |\$  /$$ |$$ |  $$ |$$ |\$$\  $$ |      $$ |        $$ |  $$ |      $$ |
#    $$ | \_/ $$ |$$ |  $$ |$$ | \$$\ $$$$$$$$\ $$ |      $$$$$$\ $$$$$$$$\ $$$$$$$$\
#    \__|     \__|\__|  \__|\__|  \__|\________|\__|      \______|\________|\________|
#
#                               PYTHON PROJECT MAKEFILE
#
#                                   VERSION 1.1.2

include project.mk


#   _____   ______   _______   _______   _____   _   _    _____    _____
#  / ____| |  ____| |__   __| |__   __| |_   _| | \ | |  / ____|  / ____|
# | (___   | |__       | |       | |     | |   |  \| | | |  __  | (___
#  \___ \  |  __|      | |       | |     | |   | . ` | | | |_ |  \___ \
#  ____) | | |____     | |       | |    _| |_  | |\  | | |__| |  ____) |
# |_____/  |______|    |_|       |_|   |_____| |_| \_|  \_____| |_____/
#
# THIS SETTINGS WILL OVVERRIDE THE DEFAULT ONES IN project.mk IF NOT SET THERE.
#

RELEASE_CHANGELOG_TARGET_BRANCH ?= main
ENABLE_WINDOWS_INSTALLER ?= 1
RELEASE_ARTIFACTS ?= $(foreach app,$(APPS_LIST),dist/$($(app)_NAME)-*) Output/*.exe





#      ______ _   ___      _______ _____   ____  __  __ ______ _   _ _______
#     |  ____| \ | \ \    / /_   _|  __ \ / __ \|  \/  |  ____| \ | |__   __|
#     | |__  |  \| |\ \  / /  | | | |__) | |  | | \  / | |__  |  \| |  | |
#     |  __| | . ` | \ \/ /   | | |  _  /| |  | | |\/| |  __| | . ` |  | |
#     | |____| |\  |  \  /   _| |_| | \ \| |__| | |  | | |____| |\  |  | |
#     |______|_| \_|   \/   |_____|_|  \_\\____/|_|  |_|______|_| \_|  |_|


# == PLATFORM DETECTION ==
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    OS_NAME := macos
else ifeq ($(UNAME_S),Linux)
    OS_NAME := linux
else
    OS_NAME := windows
endif


# Rule to create a virtual environment and install dependencies
install-env:
	uv sync
	uv sync --all-extras

init-uv:
	uv python install 3.12
	uv sync --all-groups
	uv build

install-pyinstaller:
	uv add --group dev pyinstaller

install-inno-setup:
	choco install innosetup





#       _____ _      ______          _   _
#      / ____| |    |  ____|   /\   | \ | |
#     | |    | |    | |__     /  \  |  \| |
#     | |    | |    |  __|   / /\ \ | . ` |
#     | |____| |____| |____ / ____ \| |\  |
#      \_____|______|______/_/    \_\_| \_|

# Command to clean build artifacts
clean-build:
	- rm -rf dist
	- rm -rf build
	- rm -rf $(PYTHON_MAIN_PACKAGE).egg-info
	- rm -f *.spec

# Command to clean Python cache files
clean-cache:
	- rm -rf __pycache__
	- rm -rf .pytest_cache

# Command to clean generated documentation
clean-docs:
	- rm -rf docs

# Command to clean all generated files
clean-generated:
	@echo "CLeaning generated files..."
	- rm -f $(FILE_PROJECT_PY_GENERATED)
	- rm -f Output

# Aggregate clean command
clean: clean-build clean-cache clean-generated





#       _____ ______ _   _ ______ _____         _______ ______
#      / ____|  ____| \ | |  ____|  __ \     /\|__   __|  ____|
#     | |  __| |__  |  \| | |__  | |__) |   /  \  | |  | |__
#     | | |_ |  __| | . ` |  __| |  _  /   / /\ \ | |  |  __|
#     | |__| | |____| |\  | |____| | \ \  / ____ \| |  | |____
#      \_____|______|_| \_|______|_|  \_\/_/    \_\_|  |______|

gen-project-py:
	@printf '%s\n' \
		'from pathlib import Path' \
		'import sys' \
		'import tomllib' \
		'pyproject_path = Path("$(FILE_PROJECT_TOML)")' \
		'py_file = Path("$(FILE_PROJECT_PY_GENERATED)")' \
		'try:' \
		'    if not pyproject_path.exists():' \
		'        raise FileNotFoundError(f"File {pyproject_path} does not exist.")' \
		'    with pyproject_path.open("rb") as f:' \
		'        data = tomllib.load(f)' \
		'    project = data.get("project", {})' \
		'    raw_authors = project.get("authors", [])' \
		'    authors = []' \
		'    for entry in raw_authors:' \
		'        name = entry.get("name")' \
		'        email = entry.get("email")' \
		'        if name or email:' \
		'            authors.append((name, email))' \
		'    info = {' \
		'        "name": project.get("name"),' \
		'        "version": project.get("version"),' \
		'        "description": project.get("description"),' \
		'        "requires_python": project.get("requires-python"),' \
		'        "authors": authors,' \
		'    }' \
		'    authors_repr = "[" + ", ".join(f"({repr(name)}, {repr(email)})" for name, email in info["authors"]) + "]"' \
		'    lines = [' \
		'        "name = " + repr(info["name"]),' \
		'        "version = " + repr(info["version"]),' \
		'        "description = " + repr(info["description"]),' \
		'        "requires_python = " + repr(info["requires_python"]),' \
		'        "authors = " + authors_repr,' \
		'    ]' \
		'    py_file.parent.mkdir(parents=True, exist_ok=True)' \
		'    with py_file.open("w", encoding="utf-8") as f:' \
		'        f.write("\n".join(lines) + "\n")' \
		'except Exception as e:' \
		'    print(f"Error: {e}", file=sys.stderr)' \
		'    raise SystemExit(1)' | uv run python -

# Target usati dai workflow GitHub Actions (output semplice e stabile).
ci-print-release-target-branch:
	@echo $(RELEASE_CHANGELOG_TARGET_BRANCH)

ci-print-windows-installer-enabled:
	@echo $(ENABLE_WINDOWS_INSTALLER)

ci-print-release-artifacts:
	@set -f; for pattern in $(RELEASE_ARTIFACTS); do printf '%s\n' "$$pattern"; done

gen-qt-res-py:
	$(QT_COMMAND_GEN_RES) $(QT_QRC_FILE) -o $(QT_RESOURCE_PY); \

installer:
ifeq ($(filter Darwin Linux,$(shell uname)),)
	ISCC.exe $(INNO_SETUP_FILE)
else
	@echo "Error: The installer can only be built on Windows."
	@exit 1
endif

build-uv:
	uv build

build-exe:
	$(foreach app,$(APPS_LIST),\
		uv run pyinstaller --windowed \
		--icon=$(if $(filter Darwin,$(shell uname)),$($(app)_ICNS),$($(app)_ICO)) \
		--name=$($(app)_NAME)-$(OS_NAME) \
		$($(app)_MAIN); \
	)

build-exe-onefile:
	$(foreach app,$(APPS_LIST),\
		uv run pyinstaller --windowed --onefile \
		--icon=$(if $(filter Darwin,$(shell uname)),$($(app)_ICNS),$($(app)_ICO)) \
		--name=$($(app)_NAME)-$(OS_NAME) \
		$($(app)_MAIN); \
	)

docs-gen:
	pdoc -o docs -d markdown $(PYTHON_MAIN_PACKAGE)

build-app: clean gen-project-py build-uv build-exe

build-app-onefile: clean gen-project-py build-uv build-exe-onefile

build-installer: build-app installer





#     __      _______  _____
#     \ \    / / ____|/ ____|
#      \ \  / / |    | (___
#       \ \/ /| |     \___ \
#        \  / | |____ ____) |
#         \/   \_____|_____/
#
#

uv-bump-patch-beta:
	uv version --bump patch --bump beta

uv-bump-patch:
	uv version --bump patch

uv-bump-minor:
	uv version --bump minor

uv-bump-major:
	uv version --bump major

define upgrade_version_impl
	@VERSION=$$(uv version --short); \
	if [ -f $(INNO_SETUP_FILE) ]; then \
		echo "Inno setup script found. upgrading version to $$VERSION..."; \
		sed -i "s/#define $(INNO_SETUP_VERSION_VARIABLE) \"[^\"]*\"/#define $(INNO_SETUP_VERSION_VARIABLE) \"$$VERSION\"/" $(INNO_SETUP_FILE); \
	fi; \
	git commit -am "bump: Bump version to $$VERSION"; \
	git pull --rebase; \
	git push
endef

upgrade-patch-beta: uv-bump-patch-beta gen-project-py
	$(upgrade_version_impl)

upgrade-patch: uv-bump-patch gen-project-py
	$(upgrade_version_impl)

upgrade-minor: uv-bump-minor gen-project-py
	$(upgrade_version_impl)

upgrade-major: uv-bump-major gen-project-py
	$(upgrade_version_impl)

create-version-tag:
	git pull
	git tag $$(uv version --short)
	git push origin $$(uv version --short)

upgrade-patch-beta-push-tag: upgrade-patch-beta create-version-tag

upgrade-patch-push-tag: upgrade-patch create-version-tag
upgrade-minor-push-tag: upgrade-minor create-version-tag
upgrade-major-push-tag: upgrade-major create-version-tag

