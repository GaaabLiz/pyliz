# from ai.controller.llava_controller import LlavaController
# from ai.core.ai_prompts import AiPrompt
# from ai.core.ai_setting import AiSettings
# from old_code.liz_image import LizImage
# from model.operation import Operation
#
#
# class ImageScanner:
#
#     def __init__(self, path: str, image_ai_setting: AiSettings | None = None, rag_setting: AiSettings | None = None,):
#         self.path = path
#         self.image_ai_setting = image_ai_setting
#         self.rag_setting = rag_setting
#
#     def scan(self) -> Operation[LizImage]:
#         if self.image_ai_setting:
#             return self.__scan_image_with_ai()
#         else:
#             return self.__scan_image()
#
#     def __scan_image_with_ai(self) -> Operation[LizImage]:
#         controller = LlavaController(self.image_ai_setting, self.rag_setting)
#         json_result = controller.run_and_get_vanilla_json(self.path, AiPrompt.LLAVA_DETAILED.value)
#         return controller.run_and_get_liz_media(self.path)
#
#     def __scan_image(self) -> Operation[LizImage]:
#         return Operation(status=True, payload=LizImage(self.path))
#
#
#
#
#
