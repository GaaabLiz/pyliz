from ai.core.ai_method import AiMethod
from ai.core.ai_power import AiPower
from ai.core.ai_source import AiSource
from ai.core.ai_source_type import AiSourceType
from ai.core.hg_file import HgFile
from model.file_type import FileType


class AiModels:

    # Local Models
    llava_15_7b_mmproj_f16 = HgFile("mmproj-model-f16.gguf", "https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/main/mmproj-model-f16.gguf", FileType.HG_MMPROJ)
    llava_15_7b_ggml_model_q4 = HgFile("ggml-model-q4_k.gguf", "https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/main/ggml-model-q4_k.gguf", FileType.HG_GGML)
    llava_15_7b_bundle = [llava_15_7b_mmproj_f16, llava_15_7b_ggml_model_q4]
    llava_15_7b_name = "llava157b"

    # LLM Studio Models
    llava_phi_3_mini_1 = "llava-phi-3-mini-int4"


    def __init__(self):
        pass


    class Llava:

        @staticmethod
        def get_llava(power: AiPower, source: AiSourceType) -> AiSource:
            if power == AiPower.LOW:
                return AiModels.Llava.get_llava_power_low(source)
            elif power == AiPower.MEDIUM:
                return AiModels.Llava.get_llava_power_medium(source)
            elif power == AiPower.HIGH:
                return AiModels.Llava.get_llava_power_high(source)
            raise Exception("No model found for the given power and method.")

        @staticmethod
        def get_llava_power_low(source: AiSourceType) -> AiSource:
            if source == AiSourceType.OLLAMA_SERVER:
                return AiSource(ollama_name="llava:7b")
            if source == AiSourceType.LOCAL_LLAMACPP:
                return AiSource(local_name=AiModels.llava_15_7b_name, hg_files=AiModels.llava_15_7b_bundle)
            if source == AiSourceType.LMSTUDIO_SERVER:
                return AiSource(lmstudio_name=AiModels.llava_phi_3_mini_1)
            raise Exception("No model found for the given power and method.")

        @staticmethod
        def get_llava_power_medium(source: AiSourceType) -> AiSource:
            if source == AiSourceType.OLLAMA_SERVER:
                return AiSource(ollama_name="llava:13b")
            if source == AiSourceType.LOCAL_LLAMACPP:
                return AiSource(local_name=AiModels.llava_15_7b_name, hg_files=AiModels.llava_15_7b_bundle)
            raise Exception("No model found for the given power and method.")

        @staticmethod
        def get_llava_power_high(source: AiSourceType) -> AiSource:
            if source == AiSourceType.OLLAMA_SERVER:
                return AiSource(ollama_name="llava:13b")
            if source == AiSourceType.LOCAL_LLAMACPP:
                return AiSource(local_name=AiModels.llava_15_7b_name, hg_files=AiModels.llava_15_7b_bundle)
            raise Exception("No model found for the given power and method.")


