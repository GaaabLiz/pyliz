import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from pylizlib.core.log.pylizLogger import logger


class MetadataHandler:
    """
    Handles metadata extraction and modification for media files using external tools
    like Exiftool. This class provides methods for generating sidecar files,
    updating XMP metadata, and resolving creation dates.
    """

    def __init__(self, file_path: str | Path):
        """
        Initializes the handler for a specific media file.

        Args:
            file_path: Path to the media file to process.
        """
        self.file_path = Path(file_path)

    def generate_xmp(self, output_path: str | Path) -> bool:
        """
        Generates an XMP sidecar file by extracting metadata from the source file using exiftool.
        The source file is read-only and is not modified.

        :param output_path: The destination path for the .xmp file.
        :return: True if successful, False otherwise.
        """
        output_path = Path(output_path)

        # Check if exiftool is installed
        if shutil.which("exiftool") is None:
            logger.error("Exiftool is not installed or not found in PATH.")
            return False

        try:
            # -tagsfromfile SRC: Copy tags from source file
            # -all:all: Copy all tags from all groups
            # -o DST: Write output to destination file
            cmd = [
                "exiftool",
                "-tagsfromfile",
                str(self.file_path),
                "-all:all",
                "-o",
                str(output_path),
            ]

            # Execute command
            # capture_output=True prevents printing to stdout/stderr unless there's an error we want to log
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.debug(f"Generated XMP for {self.file_path.name} at {output_path}")
            return True

        except subprocess.CalledProcessError as e:
            # Check if failure is due to no metadata tags found
            error_msg = e.stderr if e.stderr else ""
            output_msg = e.stdout if e.stdout else ""

            if "Nothing to write" in error_msg or "Nothing to write" in output_msg:
                logger.warning( f"Exiftool found no metadata to copy for {self.file_path.name}. Creating minimal XMP." )
                try:
                    minimal_xmp = (
                        "<?xpacket begin='﻿' id='W5M0MpCehiHzreSzNTczkc9d'?>\n"
                        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
                        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
                        '  <rdf:Description rdf:about=""/>\n'
                        " </rdf:RDF>\n"
                        "</x:xmpmeta>\n"
                        "<?xpacket end='w'?>"
                    )
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(minimal_xmp)
                    return True
                except Exception as write_err:
                    logger.error(f"Failed to write minimal XMP: {write_err}")
                    return False

            logger.error(f"Failed to generate XMP for {self.file_path}: {error_msg}")
            return False
        except Exception as e:
            logger.error(f"Error executing exiftool: {e}")
            return False

    def append_eagle_to_xmp(self, metadata: Any, xmp_path: str | Path) -> bool:
        """
        Appends Eagle-specific metadata (tags, annotations) to an existing XMP sidecar.
        Updates standardized fields like 'Subject', 'HierarchicalSubject', and 'Description'.

        Args:
            metadata: An object containing Eagle tags and annotations.
            xmp_path: Path to the .xmp sidecar file to update.

        Returns:
            True if the update was successful, False if Exiftool failed or file was missing.
        """
        xmp_path = Path(xmp_path)

        if shutil.which("exiftool") is None:
            logger.error("Exiftool is not installed or not found in PATH.")
            return False

        if not xmp_path.exists():
            logger.error(f"XMP file not found: {xmp_path}")
            return False

        cmd = ["exiftool", "-overwrite_original"]

        # Add tags
        if metadata.tags:
            for tag in metadata.tags:
                # Use -Subject+=tag to append to existing list
                cmd.append(f"-xmp:subject+={tag}")
                # Add Lightroom hierarchical subject
                cmd.append(f"-XMP-lr:HierarchicalSubject+={tag}")

        # Add annotation/description
        if metadata.annotation:
            # Use -Description=text to set/overwrite
            cmd.append(f"-xmp:description={metadata.annotation}")

        # If no changes needed, return True
        if len(cmd) == 2:  # Only 'exiftool' and '-overwrite_original'
            return True

        cmd.append(str(xmp_path))

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.debug(f"Updated XMP {xmp_path.name} with Eagle metadata")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to append Eagle metadata to {xmp_path}: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Error executing exiftool update: {e}")
            return False

    def set_creation_date(self, date: datetime, xmp_path: str | Path) -> bool:
        """
        Explicitly sets the creation date in an XMP sidecar file.
        Updates 'photoshop:DateCreated' and 'xmp:CreateDate' fields.

        Args:
            date: The datetime object to write into the metadata.
            xmp_path: Path to the .xmp sidecar file.

        Returns:
            True if date was successfully set.
        """
        xmp_path = Path(xmp_path)
        if not xmp_path.exists():
            return False

        date_str = date.strftime("%Y:%m:%d %H:%M:%S")
        # photoshop:DateCreated and xmp:CreateDate are common
        cmd = [
            "exiftool",
            "-overwrite_original",
            f"-photoshop:DateCreated={date_str}",
            f"-xmp:CreateDate={date_str}",
            str(xmp_path),
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return True
        except Exception as e:
            logger.error(f"Error setting creation date in XMP: {e}")
            return False

    def get_image_creation_date(self) -> Optional[datetime]:
        """
        Extracts the most reliable creation date from the image using Exiftool.
        Iterates through multiple fields (DateTimeOriginal, CreateDate, etc.)
        to find the most likely origin timestamp.

        Returns:
            A datetime object if found, otherwise None.
        """
        if shutil.which("exiftool") is None:
            return None

        # Try common creation tags in order of reliability
        tags = ["-DateTimeOriginal", "-CreateDate", "-CreationDate", "-GPSDateTime"]

        try:
            cmd = ["exiftool", "-s3", "-d", "%Y:%m:%d %H:%M:%S"]
            cmd.extend(tags)
            cmd.append(str(self.file_path))

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stdout.strip().split("\n")

            for date_str in output:
                if date_str and ":" in date_str:
                    try:
                        # Exiftool output might contain multiple lines if multiple tags found
                        # We take the first valid one
                        return datetime.strptime(date_str.strip(), "%Y:%m:%d %H:%M:%S")
                    except ValueError:
                        continue
        except Exception as e:
            logger.debug(f"Exiftool failed to extract date for {self.file_path}: {e}")

        return None
