"""
Utilities for downloading sample files from the internet for testing purposes.

Uses Picsum Photos (https://picsum.photos) — free placeholder image service,
no API key required.
"""

import hashlib
import shutil
from pathlib import Path
from typing import Optional

import requests

from pylizlib.core.log.pylizLogger import logger


class SampleImageDownloader:
    """
    Downloads sample images from Picsum Photos (https://picsum.photos)
    for use in tests. Supports optional caching to avoid repeated downloads.

    Usage example::

        downloader = SampleImageDownloader(cache_dir=Path("/tmp/img_cache"))
        path = downloader.download_image(Path("/tmp/test_dir/img1.jpg"), seed="snap_test_1")
        dir_path = downloader.create_sample_directory(Path("/tmp"), "my_test_dir", image_count=3)
    """

    BASE_URL = "https://picsum.photos"

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Args:
            cache_dir: Directory to cache downloaded images.
                       If None, every call downloads from the network.
        """
        self.cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def download_image(
        self,
        destination: Path,
        width: int = 200,
        height: int = 200,
        image_id: Optional[int] = None,
        grayscale: bool = False,
        seed: Optional[str] = None,
        timeout: int = 15,
    ) -> Path:
        """
        Downloads a single image from Picsum Photos.

        URL patterns:
        - Specific ID:   https://picsum.photos/id/{id}/{w}/{h}
        - Seeded random: https://picsum.photos/seed/{seed}/{w}/{h}
        - Pure random:   https://picsum.photos/{w}/{h}

        Args:
            destination: The file path where the image will be saved.
            width: Image width in pixels.
            height: Image height in pixels.
            image_id: Specific Picsum photo ID. If provided, takes precedence over seed.
            grayscale: If True, request a grayscale version.
            seed: Seed string for deterministic random image selection.
            timeout: HTTP request timeout in seconds.

        Returns:
            The ``destination`` path after saving the image.

        Raises:
            requests.exceptions.RequestException: If the HTTP request fails.
        """
        if image_id is not None:
            url = f"{self.BASE_URL}/id/{image_id}/{width}/{height}"
        elif seed is not None:
            url = f"{self.BASE_URL}/seed/{seed}/{width}/{height}"
        else:
            url = f"{self.BASE_URL}/{width}/{height}"

        if grayscale:
            url += "?grayscale"

        # --- Cache lookup ---
        if self.cache_dir is not None:
            cache_key = hashlib.md5(url.encode()).hexdigest()
            cache_file = self.cache_dir / f"{cache_key}.jpg"
            if cache_file.exists():
                logger.debug(f"[SampleImageDownloader] Cache hit for '{url}' → {cache_file}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cache_file, destination)
                return destination

        # --- Download ---
        destination.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(f"[SampleImageDownloader] Downloading '{url}' → {destination}")
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        destination.write_bytes(response.content)

        if self.cache_dir is not None:
            # Overwrite cache_file (defined above if cache_dir is set)
            cache_key = hashlib.md5(url.encode()).hexdigest()
            cache_file = self.cache_dir / f"{cache_key}.jpg"
            cache_file.write_bytes(response.content)

        return destination

    def download_images_to_folder(
        self,
        folder: Path,
        count: int = 3,
        width: int = 200,
        height: int = 200,
        prefix: str = "image",
        seeds: Optional[list[str]] = None,
        timeout: int = 15,
    ) -> list[Path]:
        """
        Downloads *count* images into *folder*.

        Args:
            folder: Target directory (created if it does not exist).
            count: Number of images to download.
            width: Image width in pixels.
            height: Image height in pixels.
            prefix: Filename prefix (e.g. ``"image"`` → ``image_0.jpg``, ``image_1.jpg`` …).
            seeds: Optional list of seed strings (one per image).
                   If shorter than *count*, missing seeds fall back to ``"{prefix}_{i}"``.
            timeout: HTTP request timeout per image in seconds.

        Returns:
            List of paths to the successfully downloaded files.
        """
        folder.mkdir(parents=True, exist_ok=True)
        downloaded: list[Path] = []

        for i in range(count):
            seed = seeds[i] if seeds and i < len(seeds) else f"{prefix}_{i}"
            dest = folder / f"{prefix}_{i}.jpg"
            try:
                path = self.download_image(
                    destination=dest,
                    width=width,
                    height=height,
                    seed=seed,
                    timeout=timeout,
                )
                downloaded.append(path)
            except Exception as exc:
                logger.error(f"[SampleImageDownloader] Failed to download image {i} (seed='{seed}'): {exc}")

        return downloaded

    def create_sample_directory(
        self,
        base_path: Path,
        dir_name: str,
        image_count: int = 3,
        image_width: int = 200,
        image_height: int = 200,
        extra_text_files: Optional[dict[str, str]] = None,
        timeout: int = 15,
    ) -> Path:
        """
        Creates a directory populated with sample images and optional text files.

        Args:
            base_path: Parent directory.
            dir_name: Name of the directory to create.
            image_count: Number of images to place inside.
            image_width: Image width in pixels.
            image_height: Image height in pixels.
            extra_text_files: Mapping ``{filename: text_content}`` for extra text files.
            timeout: HTTP request timeout per image in seconds.

        Returns:
            Path of the created directory.
        """
        target_dir = base_path / dir_name
        target_dir.mkdir(parents=True, exist_ok=True)

        self.download_images_to_folder(
            folder=target_dir,
            count=image_count,
            width=image_width,
            height=image_height,
            seeds=[f"{dir_name}_img_{i}" for i in range(image_count)],
            timeout=timeout,
        )

        if extra_text_files:
            for filename, content in extra_text_files.items():
                (target_dir / filename).write_text(content, encoding="utf-8")

        return target_dir

