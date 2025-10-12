#    $$\      $$\  $$$$$$\  $$\   $$\ $$$$$$$$\ $$$$$$$$\ $$$$$$\ $$\       $$$$$$$$\
#    $$$\    $$$ |$$  __$$\ $$ | $$  |$$  _____|$$  _____|\_$$  _|$$ |      $$  _____|
#    $$$$\  $$$$ |$$ /  $$ |$$ |$$  / $$ |      $$ |        $$ |  $$ |      $$ |
#    $$\$$\$$ $$ |$$$$$$$$ |$$$$$  /  $$$$$\    $$$$$\      $$ |  $$ |      $$$$$\
#    $$ \$$$  $$ |$$  __$$ |$$  $$<   $$  __|   $$  __|     $$ |  $$ |      $$  __|
#    $$ |\$  /$$ |$$ |  $$ |$$ |\$$\  $$ |      $$ |        $$ |  $$ |      $$ |
#    $$ | \_/ $$ |$$ |  $$ |$$ | \$$\ $$$$$$$$\ $$ |      $$$$$$\ $$$$$$$$\ $$$$$$$$\
#    \__|     \__|\__|  \__|\__|  \__|\________|\__|      \______|\________|\________|

# == PROJECT VARIABLES ==
PYTHON_MAIN_PACKAGE = pylizlib
FILE_MAIN_CLI := $(PYTHON_MAIN_PACKAGE)/core/cli.py
QT_QRC_FILE := resources/resources.qrc
QT_RESOURCE_PY := $(PYTHON_MAIN_PACKAGE)/resource/resources_rc.py

# == FILES VARIABLES ==
FILE_PROJECT_TOML := pyproject.toml
FILE_PROJECT_PY_GENERATED := $(PYTHON_MAIN_PACKAGE)/project.py

# == EXTERNAL COMMANDS VARIABLES ==
QT_COMMAND_GEN_RES := pyside6-rcc



#      ______ _   ___      _______ _____   ____  __  __ ______ _   _ _______
#     |  ____| \ | \ \    / /_   _|  __ \ / __ \|  \/  |  ____| \ | |__   __|
#     | |__  |  \| |\ \  / /  | | | |__) | |  | | \  / | |__  |  \| |  | |
#     |  __| | . ` | \ \/ /   | | |  _  /| |  | | |\/| |  __| | . ` |  | |
#     | |____| |\  |  \  /   _| |_| | \ \| |__| | |  | | |____| |\  |  | |
#     |______|_| \_|   \/   |_____|_|  \_\\____/|_|  |_|______|_| \_|  |_|

# Rule to create a virtual environment and install dependencies
install-env:
	uv sync
	uv sync --all-extras





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
	- rm -rf pylizlib.egg-info
	- rm -rf pyliz.spec

# Command to clean Python cache files
clean-cache:
	- rm -rf __pycache__
	- rm -rf .pytest_cache

# Command to clean generated documentation
clean-docs:
	- rm -rf docs

# Command to clean all generated files
clean-generated:
	@echo "clean-generated not implemented yet"
	- rm -f $(FILE_PROJECT_PY_GENERATED)

# Aggregate clean command
clean: clean-build clean-cache clean-docs clean-generated





#       _____ ______ _   _ ______ _____         _______ ______
#      / ____|  ____| \ | |  ____|  __ \     /\|__   __|  ____|
#     | |  __| |__  |  \| | |__  | |__) |   /  \  | |  | |__
#     | | |_ |  __| | . ` |  __| |  _  /   / /\ \ | |  |  __|
#     | |__| | |____| |\  | |____| | \ \  / ____ \| |  | |____
#      \_____|______|_| \_|______|_|  \_\/_/    \_\_|  |______|

build:
	uv run pyinstaller --windowed --icon=resources/logo.ico --name=pyliz pylizlib/core/cli.py

docs-gen:
	pdoc -o docs -d markdown pylizlib

gen-project-py:
	pyliz gen-project-py $(FILE_PROJECT_TOML) $(FILE_PROJECT_PY_GENERATED)

gen-qt-res-py:
	$(QT_COMMAND_GEN_RES) $(QT_QRC_FILE) -o $(QT_RESOURCE_PY); \
