import base64

import requests


OLLAMA_PORT = "11434"
OLLAMA_HTTP_LOCALHOST_URL = "http://localhost:" + OLLAMA_PORT


def check_ollama_status(url) -> NetResponse:
    return exec_get(url)


def get_installed_models(url) -> NetResponse:
    api_url = url + "/api/tags"
    return exec_get(api_url)


def send_query(
        url: str,
        prompt: str,
        model_name: str,
) -> NetResponse:
    api_url = url + "/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False
    }
    return exec_post(api_url, payload, False)


def send_llava_query(
        url: str,
        prompt: str,
        image_base_64: str,
        model_name: str,
) -> NetResponse:
    api_url = url + "/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "images": [image_base_64],
        "format": "json",
        "stream": False
    }
    return exec_post(api_url, payload, False)



