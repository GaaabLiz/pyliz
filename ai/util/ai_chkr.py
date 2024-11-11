import os

from loguru import logger

from ai.core.ai_dwder import AiDownloader
from ai.core.ai_env import AiEnvType
from ai.core.ai_model_list import AiModelList
from ai.core.ai_setting import AiQuery, AiSetting
from ai.core.ai_source import AiSource
from ai.core.ai_source_type import AiSourceType
from network.netutils import is_internet_available
from util import pathutils



class AiRunChecker:

    def __init__(self, query: AiQuery, app_model_folder: str, app_folder_ai: str ):
        self.query = query
        self.source = query.setting.source
        self.app_folder_ai = app_folder_ai
        self.app_model_folder = app_model_folder
        self.current_model_folder = os.path.join(self.app_model_folder, self.query.setting.model.value)


    def __check_ai_files(self):
        if self.source.ai_files is not None:
            pathutils.check_path(self.current_model_folder, True)

            for file in self.source.ai_files:
                current_file = os.path.join(self.current_model_folder, file.file_name)
                is_present = os.path.exists(current_file)
                size_web = file.get_file_size_byte()
                size_local = os.path.getsize(current_file) if is_present else 0

                if not is_present:
                    logger.debug(f"File \"{file.file_name}\" not found in model folder {self.current_model_folder}.")
                    AiDownloader.download_ai_file(file, self.current_model_folder)
                else:
                    if size_local < size_web:
                        logger.warning(f"File {file.file_name} size mismatch: Web {size_web} bytes, Local {size_local} bytes. Downloading again...")
                        os.remove(current_file)
                        AiDownloader.download_ai_file(file, self.current_model_folder)
                    else:
                        logger.info(f"File {file.file_name} found in model folder {self.current_model_folder}.")

    def __check_hg_files(self):
        if self.source.hg_files is not None:
            pathutils.check_path(self.current_model_folder, True)

            for item in self.source.hg_files:
                current_item = os.path.join(self.current_model_folder, item.file_name)
                is_present = os.path.exists(current_item)

                if not is_present:
                    logger.debug(f"Hugging face File {item} not found in model folder {self.current_model_folder}.")
                    AiDownloader.download_hg_file(item, self.current_model_folder)
                else:
                    logger.info(f"File {item} found in model folder {self.current_model_folder}.")


    def check_params(self):
        if self.query.setting.source_type == AiSourceType.OLLAMA_SERVER and self.query.setting.remote_url is None:
            raise ValueError("Remote URL is required for Ollama Server.")
        if self.query.setting.source_type == AiSourceType.LMSTUDIO_SERVER and self.query.setting.remote_url is None:
            raise ValueError("Remote URL is required for LM Studio Server.")
        if self.query.setting.source_type == AiSourceType.API_MISTRAL and self.query.setting.api_key is None:
            raise ValueError("API Key is required for Mistral API.")
        if self.query.setting.source_type == AiSourceType.API_MISTRAL and self.query.setting.api_key is None:
            raise ValueError("API Key is required for Gemini API.")
        if self.query.setting.source_type == AiSourceType.LOCAL_WHISPER and self.query.setting.download_type is None:
            raise ValueError("Download type is required for Whisper.")


    def check_source(self):
        logger.debug(f"Checking source requirements for model {self.source.model_name} of env type {self.source.env}...")
        if self.source.env == AiEnvType.REMOTE:
            if not is_internet_available():
                logger.error("Internet connection is not available on this pc.")
                raise ValueError("Internet connection is not available on this pc.")
            else:
                logger.info("Internet connection is available on this pc.")
        elif self.source.env == AiEnvType.LOCAL:
            self.__check_ai_files()
            self.__check_hg_files()
        else:
            raise ValueError(f"Environment type not found: {self.source.env}.")

