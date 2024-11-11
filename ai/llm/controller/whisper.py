import os

from ai.core.ai_dw_type import AiDownloadType
from ai.core.ai_setting import AiQuery
from ai.llm.local.whisper import Whisper
from model.operation import Operation
from util import fileutils


class WhisperController:

    def __init__(self, app_model_folder: str, app_temp_folder: str):
        self.whisper_model_folder = os.path.join(app_model_folder, "whisper")
        self.temp_folder = app_temp_folder

    def __run_from_lib(self, query: AiQuery):
        file = query.payload_path
        if not os.path.exists(file):
            return Operation(status=False, error="File not found during whisper operation.")
        if not fileutils.is_video_file(file) and not fileutils.is_audio_file(file):
            return Operation(status=False, error="File is not a video or audio file.")
        text = Whisper.transcribe(
            temp_folder=self.temp_folder,
            model_name=query.setting.source.model_name,
            video_path=query.payload_path,
            whisper_folder_path=self.whisper_model_folder,
        )

    def __run_from_hg(self, query: AiQuery):
        pass


    def run(self, query: AiQuery) -> Operation[str]:
        try:
            result = ""
            if query.setting.download_type == AiDownloadType.PYTHON_LIB:
                result = self.__run_from_lib(query)
            elif query.setting.download_type == AiDownloadType.HG:
                result = self.__run_from_hg(query)
            return Operation(status=True, payload=result)
        except Exception as e:
            return Operation(status=False, error=str(e))