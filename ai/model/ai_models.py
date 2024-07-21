from ai.model.ai_method import AiMethod
from ai.model.ai_power import AiPower
from ai.model.ai_source import AiSource
from ai.model.hg_file import HgFile
from model.file_type import FileType


class AiModels:

    llava_15_7b_mmproj_f16 = HgFile("mmproj-model-f16.gguf", "https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/main/mmproj-model-f16.gguf", FileType.HG_MMPROJ)
    llava_15_7b_ggml_model_q4 = HgFile("ggml-model-q4_k.gguf", "https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/main/ggml-model-q4_k.gguf", FileType.HG_GGML)
    llava_15_7b_bundle = [llava_15_7b_mmproj_f16, llava_15_7b_ggml_model_q4]
    llava_15_7b_name = "llava157b"

    def __init__(self):
        pass


    class Llava:

        @staticmethod
        def get_llava(power: AiPower, method: AiMethod) -> AiSource:
            if power == AiPower.LOW:
                return AiModels.Llava.get_llava_power_low(method)
            elif power == AiPower.MEDIUM:
                return AiModels.Llava.get_llava_power_medium(method)
            elif power == AiPower.HIGH:
                return AiModels.Llava.get_llava_power_high(method)
            raise Exception("No model found for the given power and method.")

        @staticmethod
        def get_llava_power_low(method: AiMethod) -> AiSource:
            if method == AiMethod.LLAVA_OLLAMA:
                return AiSource(ollama_name="llava:7b")
            if method == AiMethod.LLAVA_LOCAL_LLAMACPP:
                return AiSource(local_name=AiModels.llava_15_7b_name, hg_files=AiModels.llava_15_7b_bundle)
            raise Exception("No model found for the given power and method.")

        @staticmethod
        def get_llava_power_medium(method: AiMethod) -> AiSource:
            if method == AiMethod.LLAVA_OLLAMA:
                return AiSource(ollama_name="llava:13b")
            if method == AiMethod.LLAVA_LOCAL_LLAMACPP:
                return AiSource(local_name=AiModels.llava_15_7b_name, hg_files=AiModels.llava_15_7b_bundle)
            raise Exception("No model found for the given power and method.")

        @staticmethod
        def get_llava_power_high(method: AiMethod) -> AiSource:
            if method == AiMethod.LLAVA_OLLAMA:
                return AiSource(ollama_name="llava:15b")
            if method == AiMethod.LLAVA_LOCAL_LLAMACPP:
                return AiSource(local_name=AiModels.llava_15_7b_name, hg_files=AiModels.llava_15_7b_bundle)
            raise Exception("No model found for the given power and method.")


