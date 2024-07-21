from ai.core.ai_method import AiMethod
from ai.core.ai_power import AiPower
from ai.core.ai_setting import AiSettings
from media.image_scanner import ImageScanner
from util import osutils

url = "http://192.168.0.205:11434"
# print(Ollamaliz(url).get_models_list().models[1].name)
# client = ollama.Client(host=url)
# eagle = Eagleliz()
# print(eagle.get_app_info().payload.status)

setting = AiSettings(
    remote_url=url,
    model_name="llava:13b",
    method=AiMethod.LLAVA_OLLAMA,
    power=AiPower.LOW,
)
scanner = ImageScanner("/Users/gabliz/Pictures/obama343434333.jpg", setting)
# op_image = scanner.scan()
# print(op_image.status)
# print(test_with_head(url))
print(osutils.is_command_available("masske"))