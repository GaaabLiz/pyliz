# Changelog

Tutte le modifiche notevoli a questo progetto saranno documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e questo progetto aderisce al [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
## [0.5.5] - 2026-02-12

### Build

- Add pyliz-media configuration to project.mk
- Update installer script version and artifact paths

### Bump

- Bump version to 0.5.5

### ⚙️ Miscellaneous Tasks

- Update changelog [skip ci]
## [0.5.4] - 2026-02-06

### Bump

- Bump version to 0.5.4

### Ci

- Fix indentation and remove comments in release workflow

### ⚙️ Miscellaneous Tasks

- Update changelog [skip ci]
## [0.5.3] - 2026-02-06

### Build

- Add beta patch upgrade targets to makefile

### Bump

- Bump version to 0.5.3

### Ci

- Update release artifact paths and git-cliff tag pattern

### ⚙️ Miscellaneous Tasks

- Update changelog [skip ci]
## [0.5.2] - 2026-02-06

### Build

- Add install-pyinstaller target to makefile
- Add Inno Setup installer script
- Refactor makefile for multi-app support and add onefile targets
- Refactor project.mk to support multiple applications

### Bump

- Update version to 0.5.1
- Bump version to 0.5.2

### Ci

- Add release workflow for changelog generation and asset building

### ♻️ Refactor

- Extract version bump targets and simplify upgrade rules in makefile

### ⚙️ Miscellaneous Tasks

- Add run configuration for upgrade-patch-push-tag
## [0.5.0] - 2026-02-05

### Build

- Add tqdm dependency
- Update makefile to use uv run for project generation
- Refactor version upgrade logic and add upgrade-minor target
- Add major upgrade and tagging targets to makefile
- Add init-uv target to makefile

### Bump

- Bump version to 0.4.0
- Bump version to 0.5.0

### Ci

- Move release workflow to temp directory and update name
- Add PyPI release workflow

### ♻️ Refactor

- Move lizmedia.py to temp directory
- Extract media search logic to MediaSearcher class
- Extract media organization logic to MediaOrganizer class
- Introduce OrganizerOptions dataclass for MediaOrganizer
- Move OrganizerOptions to MediaOrganizer constructor
- Merge result logging into MediaSearcher and update organizer
- Extract search strategies into FileSystemSearcher and EagleCatalogSearcher classes
- Replace PIL with exifread for EXIF parsing in LizMedia
- Enhance media search results with status and skip reasons
- Standardize progress bar usage in media searchers
- Rename 'skipped' status to 'rejected' in media modules
- Enhance organizer command parameter logging and formatting
- Enhance Eagle media reader with error tracking and progress bars
- Enhance Eagle media reader with error tracking and progress bars
- Update Eagle reader to track and display error reasons
- Rename and enhance Eagle reader with filtering capabilities
- Rename file_found attribute to items in EagleCoolReader
- Enhance media search result handling and error reporting
- Move tag filtering to EagleCoolReader and improve reporting
- Introduce OrganizerResult and remove console output from MediaOrganizer
- Commented method
- Enhance media organizer logging and sidecar handling
- Decompose MediaOrganizer logic into helper methods
- Move result table generation to MediaOrganizer class
- Update table sorting logic and add visual indicators
- Enhance media organizer table sorting and display
- Rename organizer script to cli and enforce required arguments
- Extract table printing logic to OrganizerTablePrinter
- Move media script cli to organizer package
- Rename lizmedia2 module to lizmedia and update imports
- Rename media_app to pyliz_media and update entry point
- Extract organizer domain classes and relocate temp command
- Reorganize media organizer and view modules
- Unify media list table printing and standardize columns
- Reorganize media searcher classes into organizer module
- Modularize Eagle search logic in EagleCatalogSearcher
- Enhance sidecar handling in LizMedia and Eagle searcher
- Remove XMP generation and reporting from media organizer

### ⚙️ Miscellaneous Tasks

- Add temp_local to .gitignore
- Add run configurations for media organizer, clean, and build-app

### 🎨 Styling

- Add overflow folding to organizer result table columns

### 🐛 Bug Fixes

- Improve console output formatting in EagleMediaReader
- Use media file path for skipped items in Eagle reader and populate media object
- Enhance sidecar file matching logic in EagleCatalogSearcher
- Enable XMP generation for duplicate files skipped during organization
- Harden path sanitization in MediaOrganizer

### 📚 Documentation

- Update changelog for 0.3.71
- Add docstrings to LizMedia class in lizmedia2.py

### 🚀 Features

- Add ImageUtils class for image validation and SD metadata parsing
- Add video duration and frame rate retrieval methods
- Add pydantic dependency and pylizmedia script
- Add media organizer script and LizMedia model
- Implement file organization logic in media organizer
- Add heic, heif, webp, ico, and dng to image extensions in file.py
- Enhance media search results and logging in organizer
- Add sorting and update columns in media organizer list output
- Add progress bars to media searchers using tqdm
- Add summary output to Eagle searcher and suppress EXIF logs
- Separate sort indices for accepted/rejected lists and add progress bars to Eagle searcher
- Add support for listing errored media files in organizer
- Add result summary table and remove confirmation in organizer
- Add destination path field and source path property to OrganizerResult
- Add status spinners for table generation in organizer script
- Link sidecar files to accepted media in Eagle search results
- Add sidecar support to media organizer and improve reporting
- Initialize PylizApp and setup logging in media CLI
- Add sorting functionality to organizer results table
- Add environment variable support to organizer command
- Add XMP generation and reporting to media organizer
- Implement priority logic for HEIC and DNG files in Eagle reader
- Add index column to media search and organization tables
- Add media sidecar support and refine Eagle reader file type checks
- Implement XMP generation for missing sidecars in media organizer
- Add support for appending Eagle metadata to generated XMP files
- Update progress bars to show current filename in media scripts
- Add XMP sidecar support for creation date retrieval in LizMedia
- Add Lightroom hierarchical subject support to XMP tags

### 🧪 Testing

- Add logo resources and qrc file
- Add unit tests for EagleCool reader
- Add unit tests for LizMedia and update EagleCool reader
- Add unit tests for MediaOrganizer
## [0.3.71] - 2026-01-11

### Bump

- Bump version to 0.3.71

### 📚 Documentation

- Update changelog for 0.3.70

### 🚀 Features

- Add get_creation_date method to LizMedia for EXIF metadata extraction
## [0.3.70] - 2026-01-11

### Build

- Add macOS icon support and fix FILE_MAIN path

### Bump

- Bump version to 0.3.70

### ⚙️ Miscellaneous Tasks

- Add logo icon resources in various resolutions

### 📚 Documentation

- Update changelog for 0.3.69

### 🚀 Features

- Add eaglecool optional dependency and initialize package structure
- Add Eagle media reader and metadata models
## [0.3.69] - 2025-11-21

### Bump

- Bump version to 0.3.68
- Bump version to 0.3.69

### 📚 Documentation

- Update changelog for 0.3.67

### 🚀 Features

- Enhanced all Snapshot classes with detailed docstrings
- Enhanced all Snapshot classes with detailed docstrings
- Add export and import functionality for snapshot catalogue
- Add export and import functionality for snapshot catalogue tests
- Refactor search functionality to support file name and content queries
## [0.3.67] - 2025-11-06

### Bump

- Bump version to 0.3.66
- Bump version to 0.3.67

### 📚 Documentation

- Update changelog for 0.3.65

### 🚀 Features

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
## [0.3.65] - 2025-11-04

### Bump

- Bump version to 0.3.65

### 📚 Documentation

- Update changelog for 0.3.64

### 🚀 Features

- Emit progress update signal on operation completion
## [0.3.64] - 2025-11-04

### Bump

- Bump version to 0.3.64

### 📚 Documentation

- Update changelog for 0.3.63

### 🚀 Features

- Add task_update_message signal to Task and Operation classes
## [0.3.63] - 2025-11-04

### Bump

- Bump version to 0.3.62
- Bump version to 0.3.63

### 📚 Documentation

- Update changelog for 0.3.61

### 🚀 Features

- Update operation completion handling to report progress
## [0.3.61] - 2025-11-03

### Bump

- Bump version to 0.3.61

### 📚 Documentation

- Update changelog for 0.3.60

### 🚀 Features

- Enhance snapshot search functionality with parameterized queries and support for multiple snapshots
- Refactor search functionality to support single snapshot searches and add a method for searching multiple snapshots
- Refactor SnapshotSearcher to utilize SnapshotCatalogue and streamline search parameters
- Enhance search results to include line content and snapshot name
- Update file_path type to Path and adjust related assertions
- Add progress callback support to snapshot search methods
- Add method to batch add operations to the operation runner
## [0.3.60] - 2025-10-29

### Bump

- Bump version to 0.3.59
- Bump version to 0.3.60

### 📚 Documentation

- Update changelog for 0.3.58

### 🚀 Features

- Rename search functions to indicate global scope
- Refactor search functions to operate on individual snapshots
## [0.3.58] - 2025-10-29

### Build

- Refactor build process and add installer target
- Update clean targets and rename build command

### Bump

- Bump version to 0.3.54
- Bump version to 0.3.55
- Update versioning logic in upgrade-patch target
- Bump version to 0.3.56
- Bump version to 0.3.57
- Bump version to 0.3.58

### ♻️ Refactor

- Removed README.md
- Reorganize makefile and introduce project.mk for better structure

### 🐛 Bug Fixes

- Make folder ID and snapshot ID lengths configurable

### 📚 Documentation

- Update changelog for 0.3.53
- Added some comments

### 🚀 Features

- Add project metadata for pylizlib
- Implement text and regex search functionality in SnapshotSearcher
- Add sorting functionality for Snapshot objects with SnapshotSortKey enum
## [0.3.53] - 2025-10-20

### Bump

- Bump version to 0.3.53

### ⚙️ Miscellaneous Tasks

- Update dependencies to include pytest and related packages

### 🐛 Bug Fixes

- Use settings.json_filename for snapshot JSON path

### 📚 Documentation

- Update changelog for 0.3.52

### 🧪 Testing

- Add unit tests for Snapshot and related classes
## [0.3.52] - 2025-10-20

### Bump

- Bump version to 0.3.52

### ♻️ Refactor

- Introduce SnapshotSettings class for improved snapshot management

### 📚 Documentation

- Update changelog for 0.3.51
## [0.3.51] - 2025-10-20

### Bump

- Bump version to 0.3.51

### 🐛 Bug Fixes

- Simplify folder_name property to return only the id

### 📚 Documentation

- Update changelog for 0.3.50
## [0.3.50] - 2025-10-20

### Bump

- Bump version to 0.3.50

### 📚 Documentation

- Update changelog for 0.3.49

### 🚀 Features

- Updated uv.lock
- Add AboutMessageBox class for application information display
## [0.3.49] - 2025-10-19

### Bump

- Bump version to 0.3.49

### 📚 Documentation

- Update changelog for 0.3.48

### 🚀 Features

- Add Windows file permission handling during installation
- Add option for full control permissions during installation
- Add method to set custom catalogue path
## [0.3.48] - 2025-10-19

### Bump

- Bump version to 0.3.48

### 📚 Documentation

- Update changelog for 0.3.47

### 🚀 Features

- Improve installation process with safer directory clearing and copying
## [0.3.47] - 2025-10-19

### Bump

- Bump version to 0.3.47

### 📚 Documentation

- Update changelog for 0.3.46

### 🚀 Features

- Enhance installation process by removing existing paths before copying
- Add function to normalize size in GB and MB formats
## [0.3.46] - 2025-10-19

### Bump

- Bump version to 0.3.46

### 📚 Documentation

- Update changelog for 0.3.45

### 🚀 Features

- Update folder naming convention to include creation date
## [0.3.45] - 2025-10-19

### Bump

- Bump version to 0.3.45

### 📚 Documentation

- Update changelog for 0.3.44

### 🚀 Features

- Add cloning functionality to Snapshot and improve directory removal handling
## [0.3.44] - 2025-10-19

### Bump

- Bump version to 0.3.44

### 🐛 Bug Fixes

- Comment out release notes generation steps in release.yml

### 📚 Documentation

- Update changelog for 0.3.43

### 🚀 Features

- Improve snapshot directory management and update snapshot description
## [0.3.43] - 2025-10-19

### Bump

- Bump version to 0.3.43

### 🐛 Bug Fixes

- Comment out unused build steps for Linux, macOS, and Windows in release.yml

### 📚 Documentation

- Update changelog for 0.3.42

### 🚀 Features

- Add backup functionality for snapshots during install, modify, and delete operations
## [0.3.42] - 2025-10-19

### Bump

- Bump version to 0.3.42

### 🐛 Bug Fixes

- Remove unnecessary comment in release.yml

### 📚 Documentation

- Update changelog for 0.3.41
- Update makefile

### 🚀 Features

- Add functionality to track edits between snapshots
## [0.3.41] - 2025-10-18

### Bump

- Bump version to 0.3.41

### ♻️ Refactor

- Enhance release notes generation to include changelog between tags

### 📚 Documentation

- Update changelog for 0.3.40
## [0.3.40] - 2025-10-18

### Bump

- Bump version to 0.3.40

### ♻️ Refactor

- Enhance release notes generation to include changelog between tags

### 📚 Documentation

- Update changelog for 0.3.39
## [0.3.39] - 2025-10-18

### Bump

- Bump version to 0.3.39

### ♻️ Refactor

- Update release workflow for changelog generation and cleanup

### 📚 Documentation

- Update changelog for 0.3.38

### 🚀 Features

- Add QtFwQConfigGroup dataclass for configuration grouping
## [0.3.38] - 2025-10-18

### Bump

- Bump version to 0.3.38

### 📚 Documentation

- Update changelog for 0.3.37

### 🚀 Features

- Add UiUtils class with message display and widget creation methods
- Add QtFwQConfigItem class for enhanced configuration management
- Add QtFwQConfigItem class for enhanced configuration management
## [0.3.37] - 2025-10-18

### Bump

- Bump version to 0.3.37

### 🐛 Bug Fixes

- Update import from PyQt6 to PySide6 for compatibility

### 📚 Documentation

- Update changelog for 0.3.36

### 🚀 Features

- Add tags_as_string property and get_for_table_array method to enhance data representation
## [0.3.36] - 2025-10-17

### Bump

- Bump version to 0.3.36

### 📚 Documentation

- Update changelog for 0.3.35

### 🚀 Features

- Add UiWidgetMode enum for widget state management
- Add clear method to OperationRunner for managing pending operations
## [0.3.35] - 2025-10-17

### Bump

- Bump version to 0.3.35

### ♻️ Refactor

- Simplify progress dialog and worker implementation
- Rename progress utility module for improved clarity
- Rename operation module for improved organization
- Reorganize helper module and update import paths
- Replace interaction protocol with signal-based communication in operation modules
- Remove interaction protocol from operation module and add example window for operation execution

### 📚 Documentation

- Update changelog for 0.3.34
## [0.3.34] - 2025-10-16

### 📚 Documentation

- Update changelog for 0.3.33

### 🚀 Features

- Update task templates to use TaskTemplate2 for improved functionality
- Add delay between task executions for improved operation flow
- Add delay between task executions for improved operation flow
## [0.3.33] - 2025-10-15

### 📚 Documentation

- Update changelog for 0.3.32

### 🚀 Features

- Add function to calculate step progress percentage
- Add method to generate and update task progress using step progress percentage
- Add method to retrieve task result by ID
- Enhance operation handling with new task templates and logging
- Enhance operation handling with new task templates and logging
## [0.3.32] - 2025-10-15

### ♻️ Refactor

- Refactor operation handling by introducing operation_core and operation_domain modules

### 📚 Documentation

- Update changelog for 0.3.31

### 🚀 Features

- Add method to retrieve specific task result by name
- Add method to retrieve specific task result by name
## [0.3.31] - 2025-10-13

### 📚 Documentation

- Update changelog for 0.3.30

### 🚀 Features

- Enhance callback handling in progress dialog completion
- Add utility class for clearing layouts in UI
- Bump version to 0.3.31 in pyproject.toml and uv.lock
## [0.3.30] - 2025-10-13

### 📚 Documentation

- Update changelog for 0.3.29

### 🚀 Features

- Update progress dialog size to use dynamic dimensions from settings
- Bump version to 0.3.30 in pyproject.toml
## [0.3.29] - 2025-10-13

### 📚 Documentation

- Update changelog for 0.3.28

### 🚀 Features

- Add SimpleProgressManager and related classes for background operations with progress dialog
- Add SimpleProgressManager and related classes for background operations with progress dialog
- Bump version to 0.3.29 in pyproject.toml and uv.lock
## [0.3.28] - 2025-10-12

### 📚 Documentation

- Update changelog for 0.3.27

### 🚀 Features

- Add authors extraction to PyProjectToml class
- Bump version to 0.3.27 and add authors information
## [0.3.27] - 2025-10-12

### 🐛 Bug Fixes

- Simplify changelog generation in release.yml

### 📚 Documentation

- Update changelog for 0.3.26

### 🚀 Features

- Add SoftwareListStatusGroupCard for managing software status display
- Add LineEditMessageBox for custom message box functionality
- Add BoldLabel class for displaying bold text in the UI
- Bump version to 0.3.27 in pyproject.toml and uv.lock
## [0.3.26] - 2025-10-12

### 📚 Documentation

- Update changelog for 0.3.21

### 🚀 Features

- Bump version to 0.3.26 in pyproject.toml and uv.lock
## [0.3.25] - 2025-10-12

### 🚀 Features

- Bump version to 0.3.23 in pyproject.toml and uv.lock
- Bump version to 0.3.24 in pyproject.toml and uv.lock
- Bump version to 0.3.25 in pyproject.toml and uv.lock
## [0.3.23] - 2025-10-12

### 🚀 Features

- Add MasterListSettingCard and FileItem classes for enhanced file and folder management
- Bump version to 0.3.22 in pyproject.toml and update dependencies
- Update release workflow to generate changelog between tags
## [0.3.22] - 2025-10-12

### 🚀 Features

- Add WidgetDemo class for displaying subtitle labels in a QFrame
## [0.3.21] - 2025-10-12

### 📚 Documentation

- Update changelog for 0.3.20

### 🚀 Features

- Bump version to 0.3.21 in pyproject.toml and uv.lock, update dependencies
## [0.3.20] - 2025-10-12

### 📚 Documentation

- Update changelog for 0.3.18

### 🚀 Features

- Bump version to 0.3.19 in pyproject.toml
- Bump version to 0.3.19 in pyproject.toml
- Bump version to 0.3.20 in pyproject.toml and uv.lock
## [0.3.19] - 2025-10-12

### 🚀 Features

- Update makefile to include 'uv sync' command and bump pyqt6-fluent-widgets version to 1.9.1
## [0.3.18] - 2025-10-12

### 📚 Documentation

- Update changelog for 0.3.17

### 🚀 Features

- Add project metadata for pylizlib version 0.3.17
- Enhance Windows executable version retrieval with OS checks
- Add SoftwareData dataclass for managing software attributes
- Add validators for executable paths and text lists in qconfig.py
- Update makefile to include Qt resource generation commands
- Add .gitignore entry for test_local and create __init__.py file
- Bump version to 0.3.18 in pyproject.toml and uv.lock
## [0.3.17] - 2025-10-11

### ⚙️ Miscellaneous Tasks

- Bump version to 0.3.17 and update release workflow for Linux and macOS builds

### 📚 Documentation

- Update changelog for 0.3.15
## [0.3.16] - 2025-10-11

### ⚙️ Miscellaneous Tasks

- Restructure release workflow to separate GitHub release and PyPI publishing steps
- Bump version to 0.3.15 and update release workflow for improved changelog generation
## [0.3.14] - 2025-10-09

### ⚙️ Miscellaneous Tasks

- Clean up release workflow by removing unused tag creation step. Delete mv command.
- Restructure release workflow to separate GitHub release and PyPI publishing steps
## [0.3.13] - 2025-10-09

### ⚙️ Miscellaneous Tasks

- Update release workflow to install uv and set up Python 3.12
- Bump version to 0.3.13 in pyproject.toml and uv.lock
## [0.3.12] - 2025-10-09

### ⚙️ Miscellaneous Tasks

- Rename pypi.yml for consistency
- Rename test files for consistency
- Rename test files for consistency
- Refactor release workflow to include changelog generation and streamline build steps

### 📚 Documentation

- Update changelog for 0.3.11
## [0.3.11] - 2025-10-09

### Bump

- Update version to 0.3.11 in pyproject.toml and uv.lock

### ⚙️ Miscellaneous Tasks

- Add changelog configuration and git-cliff dependency
## [0.3.10] - 2025-10-09

### Bump

- Update version to 0.3.9 in pyproject.toml and uv.lock; modify release workflow in release.yml
- Update version to 0.3.9 in pyproject.toml and uv.lock; modify release workflow in release.yml
## [0.3.9] - 2025-10-09

### Bump

- Update version to 0.3.3
- Update version to 0.3.4 in pyproject.toml
- Update version to 0.3.5 in pyproject.toml and uv.lock; rename pypi.yml
- Update version to 0.3.6 in pyproject.toml and uv.lock; add release workflow in release.yml
- Update version to 0.3.7 in pyproject.toml and uv.lock
- Update version to 0.3.8 in pyproject.toml and uv.lock; modify release trigger in release.yml

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

