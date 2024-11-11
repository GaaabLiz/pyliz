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


class AiChecker:


    @staticmethod
    def check_param_requirements(
            query: AiQuery,
    ):
        if query.setting.source_type == AiSourceType.OLLAMA_SERVER and query.setting.remote_url is None:
            raise ValueError("Remote URL is required for Ollama Server.")
        if query.setting.source_type == AiSourceType.LMSTUDIO_SERVER and query.setting.remote_url is None:
            raise ValueError("Remote URL is required for LM Studio Server.")
        if query.setting.source_type == AiSourceType.API_MISTRAL and query.setting.api_key is None:
            raise ValueError("API Key is required for Mistral API.")
        if query.setting.source_type == AiSourceType.API_MISTRAL and query.setting.api_key is None:
            raise ValueError("API Key is required for Gemini API.")
        if query.setting.source_type == AiSourceType.LOCAL_WHISPER and query.setting.download_type is None:
            raise ValueError("Download type is required for Whisper.")


    @staticmethod
    def __check_local_sources_ai_files(
            setting: AiSetting,
            app_model_folder: str,
    ):
        if setting.source.ai_files is not None:
            aimodel_model_folder = os.path.join(app_model_folder, setting.model.value)
            pathutils.check_path(aimodel_model_folder, True)
            for file in setting.source.ai_files:
                current_file = os.path.join(aimodel_model_folder, file.file_name)
                is_present = os.path.exists(current_file)
                size_web = file.get_file_size_byte()
                size_local = os.path.getsize(current_file) if is_present else 0
                if not is_present:
                    logger.debug(f"File {file} not found in model folder {aimodel_model_folder}.")
                    AiDownloader.download_ai_files(setting.source.ai_files, aimodel_model_folder)
                else:
                    if size_local < size_web:
                        logger.warning(f"File {file} size mismatch: Web {size_web} Local {size_local}. Downloading again...")
                        AiDownloader.download_ai_files(setting.source.ai_files, aimodel_model_folder)
                    else:
                        logger.info(f"File {file} found in model folder {aimodel_model_folder}.")

    @staticmethod
    def __check_local_source(
            setting: AiSetting,
            app_model_folder: str,
            app_folder_ai: str,
    ):
        AiChecker.__check_local_sources_ai_files(setting, app_model_folder)

    @staticmethod
    def check_source_requirements(
            setting: AiSetting,
            app_model_folder: str,
            app_folder_ai: str,
    ):
        logger.debug(f"Checking source requirements for model {setting.source.model_name} of env type {setting.source.env}...")
        if setting.source.env == AiEnvType.REMOTE:
            if not is_internet_available():
                logger.error("Internet connection is not available on this pc.")
                raise ValueError("Internet connection is not available on this pc.")
            else:
                logger.info("Internet connection is available on this pc.")
        elif setting.source.env == AiEnvType.LOCAL:
            AiChecker.__check_local_source(setting, app_model_folder, app_folder_ai)
        else:
            raise ValueError(f"Environment type not found: {setting.source.env}.")




