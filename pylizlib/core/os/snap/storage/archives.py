"""Compatibility imports for ZIP mechanisms independent of snapshot formats."""

import shutil as shutil

from pylizlib.core.os.archives.zip.publication import write_verified_zip_exclusive as _write_verified_zip_exclusive
from pylizlib.core.os.filesystem.capacity import ensure_required_space as _ensure_required_space

__all__ = ["ZipArchivePreflight", "write_verified_zip", "extract_zip", "validate_zip_archive", "_write_verified_zip_exclusive", "_ensure_required_space"]

from pylizlib.core.os.archives.zip.extraction import extract_zip as extract_zip
from pylizlib.core.os.archives.zip.publication import write_verified_zip as write_verified_zip
from pylizlib.core.os.archives.zip.validation import ZipArchivePreflight as ZipArchivePreflight
from pylizlib.core.os.archives.zip.validation import validate_zip_archive as validate_zip_archive
