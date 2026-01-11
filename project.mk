
# == PROJECT VARIABLES ==
APP_NAME := pyliz
PYTHON_MAIN_PACKAGE = pylizlib
FILE_MAIN_CLI := $(PYTHON_MAIN_PACKAGE)/core/cli.py
FILE_MAIN := $(PYTHON_MAIN_PACKAGE)/core/cli.py
QT_QRC_FILE := resources/resources.qrc
QT_RESOURCE_PY := $(PYTHON_MAIN_PACKAGE)/resource/resources_rc.py
INNO_SETUP_FILE := installer.iss
INNO_SETUP_VERSION_VARIABLE := MyAppVersion


# == FILES VARIABLES ==
FILE_PROJECT_TOML := pyproject.toml
FILE_PROJECT_PY_GENERATED := $(PYTHON_MAIN_PACKAGE)/project.py
FILE_MAIN_LOGO_ICO := resources/logo.ico
FILE_MAIN_LOGO_ICNS := resources/logo_1024x1024_1024x1024.icns

# == EXTERNAL COMMANDS VARIABLES ==
QT_COMMAND_GEN_RES := pyside6-rcc