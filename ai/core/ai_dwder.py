import os

from loguru import logger

from ai.core.ai_file_type import AiFile
from ai.core.ai_source import AiSource
from util import fileutils


class AiDownloader:

    @staticmethod
    def download_ai_files(files: list[AiFile], dest_folder: str):
        for file in files:
            logger.debug(f"Downloading file {file.file_name} from {file.url} to {dest_folder}")
            file_path = os.path.join(dest_folder, file.file_name)
            fileutils.download_file(file.url, file_path, None)