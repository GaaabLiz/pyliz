# Changelog

Tutte le modifiche notevoli a questo progetto saranno documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e questo progetto aderisce al [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
## [0.3.38] - 2025-10-18

### Bump

- Update version to 0.3.9 in pyproject.toml and uv.lock; modify release workflow in release.yml
- Update version to 0.3.9 in pyproject.toml and uv.lock; modify release workflow in release.yml
- Update version to 0.3.11 in pyproject.toml and uv.lock
- Bump version to 0.3.35
- Bump version to 0.3.36
- Bump version to 0.3.37
- Bump version to 0.3.38

### ♻️ Refactor

- Refactor operation handling by introducing operation_core and operation_domain modules
- Simplify progress dialog and worker implementation
- Rename progress utility module for improved clarity
- Rename operation module for improved organization
- Reorganize helper module and update import paths
- Replace interaction protocol with signal-based communication in operation modules
- Remove interaction protocol from operation module and add example window for operation execution

### ⚙️ Miscellaneous Tasks

- Add changelog configuration and git-cliff dependency
- Rename pypi.yml for consistency
- Rename test files for consistency
- Rename test files for consistency
- Refactor release workflow to include changelog generation and streamline build steps
- Update release workflow to install uv and set up Python 3.12
- Bump version to 0.3.13 in pyproject.toml and uv.lock
- Clean up release workflow by removing unused tag creation step. Delete mv command.
- Restructure release workflow to separate GitHub release and PyPI publishing steps
- Restructure release workflow to separate GitHub release and PyPI publishing steps
- Bump version to 0.3.15 and update release workflow for improved changelog generation
- Bump version to 0.3.17 and update release workflow for Linux and macOS builds

### 🐛 Bug Fixes

- Simplify changelog generation in release.yml
- Update import from PyQt6 to PySide6 for compatibility

### 📚 Documentation

- Update changelog for 0.3.11
- Update changelog for 0.3.15
- Update changelog for 0.3.17
- Update changelog for 0.3.18
- Update changelog for 0.3.20
- Update changelog for 0.3.21
- Update changelog for 0.3.26
- Update changelog for 0.3.27
- Update changelog for 0.3.28
- Update changelog for 0.3.29
- Update changelog for 0.3.30
- Update changelog for 0.3.31
- Update changelog for 0.3.32
- Update changelog for 0.3.33
- Update changelog for 0.3.34
- Update changelog for 0.3.35
- Update changelog for 0.3.36
- Update changelog for 0.3.37

### 🚀 Features

- Add project metadata for pylizlib version 0.3.17
- Enhance Windows executable version retrieval with OS checks
- Add SoftwareData dataclass for managing software attributes
- Add validators for executable paths and text lists in qconfig.py
- Update makefile to include Qt resource generation commands
- Add .gitignore entry for test_local and create __init__.py file
- Bump version to 0.3.18 in pyproject.toml and uv.lock
- Update makefile to include 'uv sync' command and bump pyqt6-fluent-widgets version to 1.9.1
- Bump version to 0.3.19 in pyproject.toml
- Bump version to 0.3.19 in pyproject.toml
- Bump version to 0.3.20 in pyproject.toml and uv.lock
- Bump version to 0.3.21 in pyproject.toml and uv.lock, update dependencies
- Add WidgetDemo class for displaying subtitle labels in a QFrame
- Add MasterListSettingCard and FileItem classes for enhanced file and folder management
- Bump version to 0.3.22 in pyproject.toml and update dependencies
- Update release workflow to generate changelog between tags
- Bump version to 0.3.23 in pyproject.toml and uv.lock
- Bump version to 0.3.24 in pyproject.toml and uv.lock
- Bump version to 0.3.25 in pyproject.toml and uv.lock
- Bump version to 0.3.26 in pyproject.toml and uv.lock
- Add SoftwareListStatusGroupCard for managing software status display
- Add LineEditMessageBox for custom message box functionality
- Add BoldLabel class for displaying bold text in the UI
- Bump version to 0.3.27 in pyproject.toml and uv.lock
- Add authors extraction to PyProjectToml class
- Bump version to 0.3.27 and add authors information
- Add SimpleProgressManager and related classes for background operations with progress dialog
- Add SimpleProgressManager and related classes for background operations with progress dialog
- Bump version to 0.3.29 in pyproject.toml and uv.lock
- Update progress dialog size to use dynamic dimensions from settings
- Bump version to 0.3.30 in pyproject.toml
- Enhance callback handling in progress dialog completion
- Add utility class for clearing layouts in UI
- Bump version to 0.3.31 in pyproject.toml and uv.lock
- Add method to retrieve specific task result by name
- Add method to retrieve specific task result by name
- Add function to calculate step progress percentage
- Add method to generate and update task progress using step progress percentage
- Add method to retrieve task result by ID
- Enhance operation handling with new task templates and logging
- Enhance operation handling with new task templates and logging
- Update task templates to use TaskTemplate2 for improved functionality
- Add delay between task executions for improved operation flow
- Add delay between task executions for improved operation flow
- Add UiWidgetMode enum for widget state management
- Add clear method to OperationRunner for managing pending operations
- Add tags_as_string property and get_for_table_array method to enhance data representation
- Add UiUtils class with message display and widget creation methods
- Add QtFwQConfigItem class for enhanced configuration management
- Add QtFwQConfigItem class for enhanced configuration management
## [0.3.8] - 2025-10-09

### Bump

- Update version to 0.3.8 in pyproject.toml and uv.lock; modify release trigger in release.yml
## [0.3.7] - 2025-10-09

### Bump

- Update version to 0.3.7 in pyproject.toml and uv.lock
## [0.3.6] - 2025-10-09

### Bump

- Update version to 0.3.3
- Update version to 0.3.4 in pyproject.toml
- Update version to 0.3.5 in pyproject.toml and uv.lock; rename pypi.yml
- Update version to 0.3.6 in pyproject.toml and uv.lock; add release workflow in release.yml

### ♻️ Refactor

- Reorganize test files and update dependencies in pyproject.toml
- Enhance Snapshot and Catalogue functionality with data management methods
- Restructure Snapshot and SnapshotCatalogue classes for improved management and clarity
- Streamline directory management with install and uninstall methods
- Remove unused imports and clean up type hints in snap.py
- Remove unused imports in snapshot.py

### 🚀 Features

- Add data item editing and snapshot retrieval functionality
- Implement snapshot duplication functionality
- Add install functionality to manage snapshot directory installations
- Update dependencies and refactor import paths for pylizlib
- Update pdoc version and add new dependencies in pyproject.toml; refactor type hints in video.py and frameselector.py; rename docs target in makefile

