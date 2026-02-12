
# == PROJECT VARIABLES ==
PYTHON_MAIN_PACKAGE = pylizlib
QT_QRC_FILE := resources/resources.qrc
QT_RESOURCE_PY := $(PYTHON_MAIN_PACKAGE)/resource/resources_rc.py
INNO_SETUP_FILE := installer.iss
INNO_SETUP_VERSION_VARIABLE := MyAppVersion

# == APPLICATIONS CONFIGURATION ==

# Define the list of EXEs to build
APPS_LIST := pyliz qtliz pylizmedia

# Configuration for 'pyliz'
pyliz_NAME := pyliz
pyliz_MAIN := $(PYTHON_MAIN_PACKAGE)/core/cli.py
pyliz_ICO := resources/logo.ico
pyliz_ICNS := resources/logo_1024x1024_1024x1024.icns

# Configuration for 'qtliz'
qtliz_NAME := qtliz
qtliz_MAIN := $(PYTHON_MAIN_PACKAGE)/qt/cli.py
qtliz_ICO := $(pyliz_ICO)
qtliz_ICNS := $(pyliz_ICNS)

# Configuration for pyliz-media
pyliz_media_NAME := pylizmedia
pyliz_media_MAIN := $(PYTHON_MAIN_PACKAGE)/media/cli.py
pyliz_media_ICO := $(pyliz_ICO)
pyliz_media_ICNS := $(pyliz_ICNS)


# == FILES VARIABLES ==
FILE_PROJECT_TOML := pyproject.toml
FILE_PROJECT_PY_GENERATED := $(PYTHON_MAIN_PACKAGE)/project.py

# == EXTERNAL COMMANDS VARIABLES ==
QT_COMMAND_GEN_RES := pyside6-rcc