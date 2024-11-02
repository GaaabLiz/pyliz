
import os
import time

import google.generativeai as genai
from loguru import logger

from ai.core.ai_setting import AiSetting, AiQuery
from model.operation import Operation
from util import fileutils
from google.generativeai.types import HarmCategory, HarmBlockThreshold


class GeminiController:

    def __init__(self, key: str):
        genai.configure(api_key=key)

    @staticmethod
    def __upload( path: str, file_name: str):
        uri = sample_file = genai.upload_file(path=path, display_name=file_name)
        logger.info(f"Uploaded file to Google temp cache: {sample_file}")
        return uri

    @staticmethod
    def __verify_loaded_video( uri):
        # Check whether the file is ready to be used.
        while uri.state.name == "PROCESSING":
            logger.debug('.', end='')
            time.sleep(10)
            video_file = genai.get_file(uri.name)

        if uri.state.name == "FAILED":
            raise ValueError(uri.state.name)

    def scan_image(self, query: AiQuery) -> Operation[str]:
        try:
            path = query.payload_path
            file_name = os.path.basename(path)
            uri = self.__upload(path, file_name)
            model = genai.GenerativeModel(model_name=query.setting.source.model_name)
            response = model.generate_content([uri, query.prompt])
            genai.delete_file(uri.name)
            logger.info("result =" + response.text)
            return Operation(status=True, payload=response.text)
        except Exception as e:
            return Operation(status=False, error=str(e))

    def scan_video(self, query: AiQuery) -> Operation[str]:
        try:
            path = query.payload_path
            file_name = os.path.basename(path)
            uri = self.__upload(path, file_name)
            # self.__verify_loaded_video(uri)
            model = genai.GenerativeModel(model_name=query.setting.source.model_name)
            response = model.generate_content(
                [uri, query.prompt],
                request_options={"timeout": 600},
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                }
            )


            logger.debug("result =" + response.text)
            genai.delete_file(uri.name)
            return Operation(status=True, payload=response.text)
        except Exception as e:
            return Operation(status=False, error=str(e))

    def run(self, query: AiQuery) -> Operation[str]:
        path = query.payload_path
        if fileutils.is_image_file(path):
            return self.scan_image(query)
        elif fileutils.is_video_file(path):
            return self.scan_video(query)

