from ai.core.ai_dw_type import AiDownloadType
from ai.core.ai_env import AiEnvType
from ai.core.ai_power import AiPower
from ai.core.ai_source import AiSource
from ai.core.ai_source_type import AiSourceType
from ai.core.ai_file_type import AiFileType, AiFile


class AiModels:


    def __init__(self):
        pass

    # noinspection DuplicatedCode
    class Llava:

        # Local Models
        llava_15_7b_mmproj_f16 = AiFile("mmproj-model-f16.gguf", "https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/main/mmproj-model-f16.gguf", AiFileType.HG_MMPROJ)
        llava_15_7b_ggml_model_q4 = AiFile("ggml-model-q4_k.gguf", "https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/main/ggml-model-q4_k.gguf", AiFileType.HG_GGML)
        llava_15_7b_bundle = [llava_15_7b_mmproj_f16, llava_15_7b_ggml_model_q4]
        llava_15_7b_name = "llava157b"

        # LLM Studio Models
        llava_phi_3_mini_1 = "llava-phi-3-mini-int4"

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
                return AiSource(env=AiEnvType.REMOTE, model_name="llava:7b")
            if source == AiSourceType.LOCAL_LLAMACPP:
                return AiSource(env=AiEnvType.LOCAL, model_name=AiModels.Llava.llava_15_7b_name, ai_files=AiModels.Llava.llava_15_7b_bundle)
            if source == AiSourceType.LMSTUDIO_SERVER:
                return AiSource(env=AiEnvType.REMOTE, model_name=AiModels.Llava.llava_phi_3_mini_1)
            raise Exception("No model found for the given power and method.")

        @staticmethod
        def get_llava_power_medium(source: AiSourceType) -> AiSource:
            if source == AiSourceType.OLLAMA_SERVER:
                return AiSource(env=AiEnvType.REMOTE, model_name="llava:13b")
            if source == AiSourceType.LOCAL_LLAMACPP:
                return AiSource(env=AiEnvType.LOCAL, model_name=AiModels.Llava.llava_15_7b_name, ai_files=AiModels.Llava.llava_15_7b_bundle)
            if source == AiSourceType.LMSTUDIO_SERVER:
                return AiSource(env=AiEnvType.REMOTE, model_name=AiModels.Llava.llava_phi_3_mini_1)
            raise Exception("No model found for the given power and method.")

        @staticmethod
        def get_llava_power_high(source: AiSourceType) -> AiSource:
            if source == AiSourceType.OLLAMA_SERVER:
                return AiSource(env=AiEnvType.REMOTE, model_name="llava:13b")
            if source == AiSourceType.LOCAL_LLAMACPP:
                return AiSource(env=AiEnvType.LOCAL, model_name=AiModels.Llava.llava_15_7b_name, ai_files=AiModels.Llava.llava_15_7b_bundle)
            if source == AiSourceType.LMSTUDIO_SERVER:
                return AiSource(env=AiEnvType.REMOTE, model_name=AiModels.Llava.llava_phi_3_mini_1)
            raise Exception("No model found for the given power and method.")


    class Mistral:

        @staticmethod
        def get_pixstral() -> AiSource:
            return AiSource(env=AiEnvType.REMOTE, model_name="pixtral-12b-2409")

        @staticmethod
        def get_open_mistral() -> AiSource:
            return AiSource(env=AiEnvType.REMOTE, model_name="open-mistral-7b")


    class Gemini:

        @staticmethod
        def get_flash() -> AiSource:
            return AiSource(env=AiEnvType.REMOTE, model_name="gemini-1.5-flash")


    class Whisper:
        URL_TINY = "https://openaipublic.azureedge.net/main/whisper/models/65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9/tiny.pt"
        URL_BASE = "https://openaipublic.azureedge.net/main/whisper/models/ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b0e6c6326e34e/base.pt"
        URL_SMALL = "https://openaipublic.azureedge.net/main/whisper/models/9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794/small.pt"
        URL_MEDIUM = "https://openaipublic.azureedge.net/main/whisper/models/345ae4da62f9b3d59415adc60127b97c714f32e89e936602e85993674d08dcb1/medium.pt"
        URL_lARGE = "https://openaipublic.azureedge.net/main/whisper/models/e4b87e7e0bf463eb8e6956e646f1e277e901512310def2c24bf0e11bd3c28e9a/large.pt"
        FILE_TINY = AiFile("tiny.pt", URL_TINY, AiFileType.PT)
        FILE_BASE = AiFile("base.pt", URL_BASE, AiFileType.PT)
        FILE_SMALL = AiFile("small.pt", URL_SMALL, AiFileType.PT)
        FILE_MEDIUM = AiFile("medium.pt", URL_MEDIUM, AiFileType.PT)
        FILE_LARGE = AiFile("large.pt", URL_lARGE, AiFileType.PT)


        @staticmethod
        def __get_model_lib_id(power: AiPower) -> AiSource :
            if power == AiPower.LOW:
                return AiSource(env=AiEnvType.LOCAL, model_name="base")
            elif power == AiPower.MEDIUM:
                return AiSource(env=AiEnvType.LOCAL, model_name="small")
            elif power == AiPower.HIGH:
                return AiSource(env=AiEnvType.LOCAL, model_name="medium")
            else :
                raise Exception("No model found for the given power and method.")

        @staticmethod
        def __get_hg_files(power: AiPower) -> AiSource :
            pass

        @staticmethod
        def __get_openai_urls(power: AiPower) -> AiSource:
            if power == AiPower.LOW:
                return AiSource(env=AiEnvType.LOCAL, model_name="base", ai_files=[AiModels.Whisper.FILE_BASE])
            elif power == AiPower.MEDIUM:
                return AiSource(env=AiEnvType.LOCAL, model_name="small", ai_files=[AiModels.Whisper.FILE_SMALL])
            elif power == AiPower.HIGH:
                return AiSource(env=AiEnvType.LOCAL, model_name="medium", ai_files=[AiModels.Whisper.FILE_MEDIUM])
            else:
                raise Exception("No model found for the given power and method.")

        @staticmethod
        def get_whisper(dw_type: AiDownloadType, power: AiPower) -> AiSource:
            if dw_type == AiDownloadType.PYTHON_LIB:
                return AiModels.Whisper.__get_model_lib_id(power)
            elif dw_type == AiDownloadType.HG:
                return AiModels.Whisper.__get_hg_files(power)
            elif dw_type == AiDownloadType.WEB_FILES:
                return AiModels.Whisper.__get_openai_urls(power)
            else:
                raise Exception("No model found for the given power and method.")

