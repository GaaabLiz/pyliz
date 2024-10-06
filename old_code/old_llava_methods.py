
# def __get_image_from_json(self, output: str, image_path: str) -> Operation[LizImage]:
#     info_json = json.loads(output)
#     output_image = LizImage(image_path)
#     output_image.set_ai_filename(info_json.get("filename")) if self.settings.scan_settings.ai_rename else None
#     output_image.set_ai_description(info_json.get("description")) if self.settings.scan_settings.ai_comment else None
#     output_image.set_ai_tags(info_json.get("tags")) if self.settings.scan_settings.ai_tags else None
#     output_image.set_ai_text(info_json.get("text")) if self.settings.scan_settings.ai_ocr else None
#     output_image.set_ai_scanned(True)
#     return Operation(status=True, payload=output_image)


# def run(self, image_path: str) -> Operation[str]:
#     if self.settings.method == AiMethod.LLAVA_OLLAMA:
#         return self.__run_from_ollama(image_path)
#     elif self.settings.method == AiMethod.LLAVA_LOCAL_LLAMACPP:
#         return self.__run_from_local_llamacpp(image_path)
#     else:
#         raise NotImplementedError("This method is not implemented.")


# def run_and_get_liz_media(self, image_path: str) -> Operation[LizImage]:
#     if self.settings.prompt == AiPrompt.LLAVA_INNER_JSON:
#         op = self.__run_from_ollama(image_path)
#         if not op.is_op_ok():
#             return Operation(status=False, error=op.error)
#         return self.__get_image_from_json(op.payload, image_path)
#     elif self.settings.method == AiMethod.LLAVA_INNER_JSON:
#         op = self.__run_from_local_llamacpp(image_path)
#         if not op.is_op_ok():
#             return Operation(status=False, error=op.error)
#         return self.__get_image_from_json(op.payload, image_path)
#     else:
#         raise NotImplementedError("Current Aimethod is not implemented for this function.")


# def run_and_get_liz_media(
#         self,
#         image_path: str,
#         scan_settings: AiScanSettings | None = None
# ) -> Operation[LizImage]:
#     if self.rag_settings is None:
#         raise ValueError("Rag AI settings is not set.")
