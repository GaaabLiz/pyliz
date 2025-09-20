import os

import numpy as np
from PIL import Image

from pylizlib.core.log.pylizLogger import logger


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