# Changelog

Tutte le modifiche notevoli a questo progetto saranno documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e questo progetto aderisce al [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
## [unreleased]

### Build

- Refactor build process and add installer target
- Update clean targets and rename build command
- Add macOS icon support and fix FILE_MAIN path

### Bump

- Update version to 0.3.3
- Update version to 0.3.4 in pyproject.toml
- Update version to 0.3.5 in pyproject.toml and uv.lock; rename pypi.yml
- Update version to 0.3.6 in pyproject.toml and uv.lock; add release workflow in release.yml
- Update version to 0.3.7 in pyproject.toml and uv.lock
- Update version to 0.3.8 in pyproject.toml and uv.lock; modify release trigger in release.yml
- Update version to 0.3.9 in pyproject.toml and uv.lock; modify release workflow in release.yml
- Update version to 0.3.9 in pyproject.toml and uv.lock; modify release workflow in release.yml
- Update version to 0.3.11 in pyproject.toml and uv.lock
- Bump version to 0.3.35
- Bump version to 0.3.36
- Bump version to 0.3.37
- Bump version to 0.3.38
- Bump version to 0.3.39
- Bump version to 0.3.40
- Bump version to 0.3.41
- Bump version to 0.3.42
- Bump version to 0.3.43
- Bump version to 0.3.44
- Bump version to 0.3.45
- Bump version to 0.3.46
- Bump version to 0.3.47
- Bump version to 0.3.48
- Bump version to 0.3.49
- Bump version to 0.3.50
- Bump version to 0.3.51
- Bump version to 0.3.52
- Bump version to 0.3.53
- Bump version to 0.3.54
- Bump version to 0.3.55
- Update versioning logic in upgrade-patch target
- Bump version to 0.3.56
- Bump version to 0.3.57
- Bump version to 0.3.58
- Bump version to 0.3.59
- Bump version to 0.3.60
- Bump version to 0.3.61
- Bump version to 0.3.62
- Bump version to 0.3.63
- Bump version to 0.3.64
- Bump version to 0.3.65
- Bump version to 0.3.66
- Bump version to 0.3.67
- Bump version to 0.3.68
- Bump version to 0.3.69
- Bump version to 0.3.70

### ♻️ Refactor

- Reorganize test files and update dependencies in pyproject.toml
- Enhance Snapshot and Catalogue functionality with data management methods
- Restructure Snapshot and SnapshotCatalogue classes for improved management and clarity
- Streamline directory management with install and uninstall methods
- Remove unused imports and clean up type hints in snap.py
- Remove unused imports in snapshot.py
- Refactor operation handling by introducing operation_core and operation_domain modules
- Simplify progress dialog and worker implementation
- Rename progress utility module for improved clarity
- Rename operation module for improved organization
- Reorganize helper module and update import paths
- Replace interaction protocol with signal-based communication in operation modules
- Remove interaction protocol from operation module and add example window for operation execution
- Update release workflow for changelog generation and cleanup
- Enhance release notes generation to include changelog between tags
- Enhance release notes generation to include changelog between tags
- Introduce SnapshotSettings class for improved snapshot management
- Removed README.md
- Reorganize makefile and introduce project.mk for better structure

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
- Update dependencies to include pytest and related packages
- Add logo icon resources in various resolutions

### 🐛 Bug Fixes

- Simplify changelog generation in release.yml
- Update import from PyQt6 to PySide6 for compatibility
- Remove unnecessary comment in release.yml
- Comment out unused build steps for Linux, macOS, and Windows in release.yml
- Comment out release notes generation steps in release.yml
- Simplify folder_name property to return only the id
- Use settings.json_filename for snapshot JSON path
- Make folder ID and snapshot ID lengths configurable

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
- Update changelog for 0.3.38
- Update changelog for 0.3.39
- Update changelog for 0.3.40
- Update changelog for 0.3.41
- Update makefile
- Update changelog for 0.3.42
- Update changelog for 0.3.43
- Update changelog for 0.3.44
- Update changelog for 0.3.45
- Update changelog for 0.3.46
- Update changelog for 0.3.47
- Update changelog for 0.3.48
- Update changelog for 0.3.49
- Update changelog for 0.3.50
- Update changelog for 0.3.51
- Update changelog for 0.3.52
- Update changelog for 0.3.53
- Added some comments
- Update changelog for 0.3.58
- Update changelog for 0.3.60
- Update changelog for 0.3.61
- Update changelog for 0.3.63
- Update changelog for 0.3.64
- Update changelog for 0.3.65
- Update changelog for 0.3.67
- Update changelog for 0.3.69

### 🚀 Features

- Add data item editing and snapshot retrieval functionality
- Implement snapshot duplication functionality
- Add install functionality to manage snapshot directory installations
- Update dependencies and refactor import paths for pylizlib
- Update pdoc version and add new dependencies in pyproject.toml; refactor type hints in video.py and frameselector.py; rename docs target in makefile
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
- Add QtFwQConfigGroup dataclass for configuration grouping
- Add functionality to track edits between snapshots
- Add backup functionality for snapshots during install, modify, and delete operations
- Improve snapshot directory management and update snapshot description
- Add cloning functionality to Snapshot and improve directory removal handling
- Update folder naming convention to include creation date
- Enhance installation process by removing existing paths before copying
- Add function to normalize size in GB and MB formats
- Improve installation process with safer directory clearing and copying
- Add Windows file permission handling during installation
- Add option for full control permissions during installation
- Add method to set custom catalogue path
- Updated uv.lock
- Add AboutMessageBox class for application information display
- Add project metadata for pylizlib
- Implement text and regex search functionality in SnapshotSearcher
- Add sorting functionality for Snapshot objects with SnapshotSortKey enum
- Rename search functions to indicate global scope
- Refactor search functions to operate on individual snapshots
- Enhance snapshot search functionality with parameterized queries and support for multiple snapshots
- Refactor search functionality to support single snapshot searches and add a method for searching multiple snapshots
- Refactor SnapshotSearcher to utilize SnapshotCatalogue and streamline search parameters
- Enhance search results to include line content and snapshot name
- Update file_path type to Path and adjust related assertions
- Add progress callback support to snapshot search methods
- Add method to batch add operations to the operation runner
- Update operation completion handling to report progress
- Add task_update_message signal to Task and Operation classes
- Emit progress update signal on operation completion
- Add functionality to remove installed copies of snapshots with tests
- Enhance backup naming for snapshot operations
- Implement backup type differentiation for snapshot operations
- Add folder size calculation to snapshot initialization
- Add sorting functionality for snapshots by associated directory size
- Add export functionality for snapshots and associated directories
- Update create_backup method to differentiate export zip naming
- Implement snapshot import functionality with validation and error handling
- Add method to update associated directories from the filesystem and implement corresponding tests
- Add unit test for tags_as_string method in Snapshot class
- Enhanced all Snapshot classes with detailed docstrings
- Enhanced all Snapshot classes with detailed docstrings
- Add export and import functionality for snapshot catalogue
- Add export and import functionality for snapshot catalogue tests
- Refactor search functionality to support file name and content queries
- Add eaglecool optional dependency and initialize package structure
- Add Eagle media reader and metadata models

### 🧪 Testing

- Add unit tests for Snapshot and related classes

