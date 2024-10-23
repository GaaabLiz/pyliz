
import os
import google.generativeai as genai


class GeminiController:

    def __init__(self, key: str):
        genai.configure(api_key=key)

    def upload(self, path: str, file_name: str):
        sample_file = genai.upload_file(path=path, display_name=file_name)


