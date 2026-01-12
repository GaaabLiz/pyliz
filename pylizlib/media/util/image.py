import os

import numpy as np
from PIL import Image
from sd_parsers import ParserManager
from sd_parsers.data import PromptInfo

from pylizlib.core.domain.os import FileType
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.file import is_media_file, get_file_type


def save_ndarrays_as_images(ndarray_list, output_path, prefix='frame', extension='png'):
    """
    Salva una lista di np.ndarray come file immagine in una directory.

    :param ndarray_list: Lista di np.ndarray da salvare.
    :param output_path: Path della directory in cui salvare le immagini.
    :param prefix: Prefisso per i nomi dei file immagine.
    :param extension: Estensione dei file immagine (es. 'png', 'jpg').
    """
    os.makedirs(output_path, exist_ok=True)  # Crea la directory se non esiste
    for idx, img_array in enumerate(ndarray_list):
        img = Image.fromarray(img_array)  # Converti in immagine
        img.save(os.path.join(output_path, f'{prefix}_{idx}.{extension}'))



def load_images_as_ndarrays(input_path):
    """
    Legge file immagine in una directory e li converte in np.ndarray.

    :param input_path: Path della directory contenente i file immagine.
    :return: Lista di np.ndarray rappresentanti le immagini.
    """
    ndarray_list = []
    for file_name in os.listdir(input_path):
        file_path = os.path.join(input_path, file_name)
        try:
            with Image.open(file_path) as img:
                ndarray_list.append(np.array(img))  # Converte in array numpy
        except Exception as e:
            logger.error(f"Errore leggendo {file_name}: {e}")
    return ndarray_list


class ImageUtils:

    @staticmethod
    def __check_file_is_image(path: str):
        if not is_media_file(path):
            raise ValueError(f"File {path} is not a media file.")
        file_type = get_file_type(path)
        if not file_type == FileType.IMAGE:
            raise ValueError(f"File {path} is not an image file.")

    @staticmethod
    def check_sd_metadata(path: str) -> PromptInfo | None:
        ImageUtils.__check_file_is_image(path)
        try:
            parser_manager = ParserManager()
            prompt_info: PromptInfo | None = parser_manager.parse(path)
            if prompt_info is not None:
                return prompt_info
        except Exception as e:
            logger.error(f"Error checking for AI metadata with sdParser: {str(e)}")
