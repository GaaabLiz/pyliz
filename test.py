import ollama

from api.data.ollamapi import Ollamapi
from api.service.ollamaliz import Ollamaliz
from model.ai_power import AiPower


url = "http://192.168.0.205:11434"
print(Ollamaliz(url).get_models_list().models[1].name)
client = ollama.Client(host=url)

