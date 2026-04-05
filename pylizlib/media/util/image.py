import os

import numpy as np
from PIL import Image
from sd_parsers import ParserManager
from sd_parsers.data import PromptInfo

from pylizlib.core.domain.os import FileType
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.file import is_media_file, get_file_type


def save_ndarrays_as_images(ndarray_list: list[np.ndarray], output_path: str, prefix: str = 'frame', extension: str = 'png'):
    """
    Saves a list of numpy arrays (images) to a directory.

    Args:
        ndarray_list: List of images as numpy arrays.
        output_path: Path to the destination directory.
        prefix: Filename prefix for the saved images.
        extension: Image file extension (e.g., 'png', 'jpg').
    """
    os.makedirs(output_path, exist_ok=True)  # Crea la directory se non esiste
    for idx, img_array in enumerate(ndarray_list):
        img = Image.fromarray(img_array)  # Converti in immagine
        img.save(os.path.join(output_path, f'{prefix}_{idx}.{extension}'))



def load_images_as_ndarrays(input_path: str) -> list[np.ndarray]:
    """
    Reads all image files from a directory and converts them into numpy arrays.

    Args:
        input_path: Path to the directory containing image files.

    Returns:
        A list of numpy arrays representing the images.
    """
    ndarray_list = []
    for file_name in os.listdir(input_path):
        file_path = os.path.join(input_path, file_name)
        try:
            with Image.open(file_path) as img:
                ndarray_list.append(np.array(img))  # Convert to numpy array
        except Exception as e:
            logger.error(f"Error reading {file_name}: {e}")
    return ndarray_list


class ImageUtils:
    """
    Utility class for image-specific operations, including metadata 
    extraction for Stable Diffusion images.
    """

    @staticmethod
    def __check_file_is_image(path: str):
        if not is_media_file(path):
            raise ValueError(f"File {path} is not a media file.")
        file_type = get_file_type(path)
        if not file_type == FileType.IMAGE:
            raise ValueError(f"File {path} is not an image file.")

    @staticmethod
    def check_sd_metadata(path: str) -> PromptInfo | None:
        """
        Attempts to parse Stable Diffusion generation metadata from an image.
        Uses sd-parsers to extract prompt, sampler, and other parameters.

        Args:
            path: Path to the image file.

        Returns:
            PromptInfo object if metadata is found, otherwise None.
        """
        ImageUtils.__check_file_is_image(path)
        try:
            parser_manager = ParserManager()
            prompt_info: PromptInfo | None = parser_manager.parse(path)
            if prompt_info is not None:
                return prompt_info
        except Exception as e:
            logger.error(f"Error checking for AI metadata with sdParser: {str(e)}")
