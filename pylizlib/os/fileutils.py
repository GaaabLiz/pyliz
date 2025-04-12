import hashlib
import json
import os
import platform
from datetime import datetime

import requests
from pylizlib.log.pylizLogger import logger

from pylizlib.model.fileType import FileType
from pylizlib.model.operation import Operation

image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.svg']
video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.3gp']
audio_extensions = ['.mp3', '.wav', '.ogg', '.flac', '.wma', '.aac', '.m4a']
text_extensions = ['.txt', '.doc', '.docx', '.pdf', '.odt', '.rtf', '.tex']


def is_image_extension(extension: str) -> bool:
    return extension in image_extensions


def is_video_extension(extension: str) -> bool:
    return extension in video_extensions


def is_audio_extension(extension: str) -> bool:
    return extension in audio_extensions


def is_text_extension(extension: str) -> bool:
    return extension in text_extensions


def is_image_file(path: str) -> bool:
    return is_image_extension(os.path.splitext(path)[1])


def is_video_file(path: str) -> bool:
    return is_video_extension(os.path.splitext(path)[1])


def is_audio_file(path: str) -> bool:
    return is_audio_extension(os.path.splitext(path)[1])


def is_text_file(path: str) -> bool:
    return is_text_extension(os.path.splitext(path)[1])


def is_image_or_video_file(path: str) -> bool:
    return is_image_file(path) or is_video_file(path)


def is_media_file(path: str) -> bool:
    return is_image_file(path) or is_video_file(path) or is_audio_file(path)


def get_file_type(path: str) -> FileType:
    if is_image_file(path):
        return FileType.IMAGE
    elif is_video_file(path):
        return FileType.VIDEO
    elif is_audio_file(path):
        return FileType.AUDIO
    elif is_text_file(path):
        return FileType.TEXT
    else:
        raise ValueError("Unsupported file type")


def is_file_dup_in_dir(path:str, file_name:str) -> bool:
    for root, dirs, files in os.walk(path):
        if file_name in files:
            return True
    return False


def get_file_c_date(path_to_file) -> datetime:
    """
    Try to get the date that a file was created, falling back to when it was
    last modified if that isn't possible.
    See http://stackoverflow.com/a/39501288/1709587 for explanation.
    """
    if platform.system() == 'Windows':
        timestamp = os.path.getctime(path_to_file)
    else:
        stat = os.stat(path_to_file)
        try:
            timestamp = stat.st_birthtime
        except AttributeError:
            # We're probably on Linux. No easy way to get creation dates here,
            # so we'll settle for when its content was last modified.
            timestamp = stat.st_mtime

    # Convert timestamp to datetime object
    return datetime.fromtimestamp(timestamp)


def download_file(url: str, destinazione: str, on_progress: callable) -> Operation[None]:
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()  # Verifica se la richiesta è andata a buon fine

        # Ottieni la dimensione totale del file dal campo 'Content-Length' dell'header
        totale = int(response.headers.get('content-length', 0))

        # Inizializza variabili per il calcolo della percentuale
        scaricato = 0
        percentuale = 0

        with open(destinazione, 'wb') as file:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:  # Filtra fuori i chunk vuoti
                    file.write(chunk)
                    scaricato += len(chunk)

                    # Calcola la nuova percentuale
                    nuova_percentuale = int(scaricato * 100 / totale)
                    if nuova_percentuale > percentuale:
                        percentuale = nuova_percentuale
                        on_progress(percentuale)
        logger.trace(f"Download completed!")
        return Operation(status=True)
    except Exception as e:
        return Operation(status=False, error=str(e))


def write_json_to_file(path, filename, content):
    # Verifica se la directory esiste, altrimenti la crea
    if not os.path.exists(path):
        os.makedirs(path)

    # Crea il percorso completo del file
    file_path = os.path.join(path, filename)

    # Scrive il contenuto JSON nel file
    with open(file_path, 'w') as json_file:
        json.dump(content, json_file, indent=4)


def gen_file_hash(path):
    sha256_hash = hashlib.sha256()
    # Leggi il file a blocchi per evitare problemi con file di grandi dimensioni
    with open(path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
