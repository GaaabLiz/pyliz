
prompt_llava_1 = """
Analyze the image thoroughly and provide a detailed description of every visible element. Return a jsom including the following information:
- "description": a detailed description of the image (minimum 15-20 words), considering colors, objects, actions, and any other relevant details.
- "tags": a list of tags that describe the image. Include specific objects, actions, locations, and any discernible themes. (minimum 5 maximum 10 tags)
- "text": a list of all the text found in the image (if any).
- "filename": phrase that summarizes the image content (maximum 30 characters).
"""