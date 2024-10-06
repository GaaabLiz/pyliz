import base64
import requests
import os
from mistralai import Mistral


class Mistraliz:


    def __init__(self, api_key: str):
        self.api_key = api_key


    def run_pixstral_vision(self, model_name: str, image_path: str, prompt: str) -> str:
        with open(image_path, "rb") as image_file:
            base_image = base64.b64encode(image_file.read()).decode('utf-8')
        client = Mistral(api_key=self.api_key)
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{base_image}"
                    }
                ]
            }
        ]
        chat_response = client.chat.complete(
            model=model_name,
            messages=messages
        )
        return chat_response.choices[0].message.content

    def run_open_mistral(self, model_name: str, prompt: str) -> str:
        client = Mistral(api_key=self.api_key)
        chat_response = client.chat.complete(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                },
            ]
        )
        return chat_response.choices[0].message.content
