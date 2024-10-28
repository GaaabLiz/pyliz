from huggingface_hub import hf_hub_download
from llama_cpp import Llama


# https://github.com/abetlen/llama-cpp-python


class LlamaCppLib:

    @staticmethod
    def run_llama3(prompt: str, path_install: str) -> str:
        model_name = "Orenguteng/Llama-3-8B-Lexi-Uncensored-GGUF"
        model_file = "Lexi-Llama-3-8B-Uncensored_Q4_K_M.gguf"
        model_path = hf_hub_download(model_name,
                                     filename=model_file,
                                     local_dir=path_install,
                                     )
        llm = Llama(model_path, n_gpu_layers=1)
        response = llm(prompt)
        print(response)

