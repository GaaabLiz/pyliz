import os

import whisper
from loguru import logger
from whisper import Whisper

from ai.core.ai_dw_type import AiDownloadType
from ai.core.ai_setting import AiQuery
from ai.llm.local.whisper import Whisper as LocalWhisper
from media.video_helper import VideoUtils
from model.operation import Operation
from util import fileutils, datautils


class WhisperController:

    def __init__(self, app_model_folder: str, app_temp_folder: str):
        self.whisper_model_folder = os.path.join(app_model_folder, "whisper")
        self.temp_folder = app_temp_folder

    #
    # def __run_from_lib(self, query: AiQuery):
    #     file = query.payload_path
    #     if not os.path.exists(file):
    #         return Operation(status=False, error="File not found during whisper operation.")
    #     if not fileutils.is_video_file(file) and not fileutils.is_audio_file(file):
    #         return Operation(status=False, error="File is not a video or audio file.")
    #     text = Whisper.transcribe(
    #         temp_folder=self.temp_folder,
    #         model_name=query.setting.source.model_name,
    #         video_path=query.payload_path,
    #         whisper_folder_path=self.whisper_model_folder,
    #     )
    #
    # def __run_from_hg(self, query: AiQuery) -> Operation[str]:
    #     return Operation(status=False, error="Hugging face download not supported for whisper operation")

    @staticmethod
    def __transcribe(audio_file_path: str, whisper_obj: whisper.Whisper) -> Operation[str]:
        logger.debug(f"Transcribing audio {audio_file_path}")
        risultato = whisper_obj.transcribe(audio_file_path)
        return Operation(status=True, payload=risultato["text"])

    def __transcribe_file(self, query: AiQuery, whisper_obj: whisper.Whisper) -> Operation[str]:
        if fileutils.is_video_file(query.payload_path):
            audio_id = datautils.gen_random_string(10)
            audio_path = os.path.join(self.temp_folder, f"{audio_id}.wav")
            logger.debug(f"Extracting audio from video {query.payload_path} to {audio_path}")
            VideoUtils.extract_audio(query.payload_path, audio_path)
            return self.__transcribe(audio_path, whisper_obj)
        elif fileutils.is_audio_file(query.payload_path):
            return self.__transcribe(query.payload_path, whisper_obj)
        else:
            return Operation(status=False, error="File is not a video or audio file.")


    def run(self, query: AiQuery) -> Operation[str]:
        try:
            if query.setting.download_type == AiDownloadType.PYTHON_LIB:
                raise NotImplementedError("Python lib not implemented yet in WhisperController")
            elif query.setting.download_type == AiDownloadType.HG:
                raise NotImplementedError("Hugging face not implemented yet in WhisperController")
            elif query.setting.download_type == AiDownloadType.WEB_FILES:
                model_file_path = os.path.join(self.whisper_model_folder, query.setting.source.get_main_ai_file().file_name)
                whisper_obj = whisper.load_model(model_file_path)
                return self.__transcribe_file(query, whisper_obj)
        except Exception as e:
            return Operation(status=False, error=str(e))