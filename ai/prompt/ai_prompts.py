from enum import Enum

from ai.prompt.customPrompt import CustomPrompt, PromptType, PromptInfo

prompt_llava_json = """
Analyze the image thoroughly and provide a detailed description of every visible element. Return a json including the following information:
- "description": a detailed description of the image (minimum 15-20 words), considering colors, objects, actions, and any other relevant details.
- "tags": a list of tags that describe the image. Include specific objects, actions, locations, and any discernible themes. (minimum 5 maximum 10 tags)
- "text": a list of all the text found in the image (if any).
- "filename": phrase that summarizes the image content (maximum 30 characters).
"""

extract_info_from_image = """
Analyze the following text that contains a description of image. Return a json including the following information:
- "tags": a list of tags that describe the image. Include specific objects, actions, locations, and any discernible themes. (minimum 5 maximum 10 tags)
- "text": a list of all the text found in the image (if specified).
- "filename": phrase that summarizes the image content (maximum 30 characters).
"""

prompt_llava_detailed_STEP1 = """
Analyze the image thoroughly and provide a detailed description of every visible element. 
If there are people, try to recognize them. If there are objects, try to identify them.
If the are texts, try to read them.
"""


class AiPrompt(Enum):

    IMAGE_VISION_DETAILED_1 = prompt_llava_detailed_STEP1
    IMAGE_VISION_JSON = prompt_llava_json
    TEXT_EXTRACT_FROM_VISION_1 = extract_info_from_image




