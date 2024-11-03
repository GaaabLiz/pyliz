import os

from ai.core.ai_setting import AiQuery
from ai.llm.local.whisper import Whisper
from model.operation import Operation
from util import fileutils


class WhisperController:

    @staticmethod
    def run(query: AiQuery, model_folder: str, temp_folder: str) -> Operation[str]:
        try:
            file = query.payload_path
            if not os.path.exists(file):
                return Operation(status=False, error="File not found during whisper operation.")
            if not fileutils.is_video_file(file) and not fileutils.is_audio_file(file):
                return Operation(status=False, error="File is not a video or audio file.")
            text = Whisper.transcribe(
                temp_folder=temp_folder,
                model_name=query.setting.source.model_name,
                video_path=query.payload_path,
                whisper_folder_path=os.path.join(model_folder, "whisper"),
            )
            return Operation(status=True, payload=text)
        except Exception as e:
            return Operation(status=False, error=str(e))