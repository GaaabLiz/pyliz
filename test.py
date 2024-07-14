import ollama

from api.service.eagleliz import Eagleliz
from api.service.ollamaliz import Ollamaliz

url = "http://192.168.0.205:11434"
print(Ollamaliz(url).get_models_list().models[1].name)
client = ollama.Client(host=url)
eagle = Eagleliz()
print(eagle.get_app_info().payload.status)
