import os
import tempfile

import moviepy.editor as mp
import whisper
from loguru import logger

from media.video_helper import VideoUtils
from network.ssl import ignore_context_ssl, setup2323
from util import datautils


class Whisper:


    @staticmethod
    def get_model_obj_from_lib(model_name: str, whisper_folder_path: str):

        # Imposta la directory personalizzata per i modelli
        logger.debug(f"Setting WHISPER_CACHE_DIR to {whisper_folder_path}")
        os.environ["WHISPER_CACHE_DIR"] = whisper_folder_path
        # Carica il modello, che verrà scaricato se non già presente
        logger.debug(f"Loading Whisper model {model_name}")
        modello = whisper.load_model(model_name, download_root=whisper_folder_path)
        return modello

    @staticmethod
    def get_model_obj_from_hf():
        model_name = "Orenguteng/Llama-3-8B-Lexi-Uncensored-GGUF"
        model_file = "Lexi-Llama-3-8B-Uncensored_Q4_K_M.gguf"
        model_path = hf_hub_download(model_name,
                                     filename=model_file,
                                     local_dir=path_install,
                                     )

    @staticmethod
    def transcribe(
            temp_folder: str,
            model_name: str,
            video_path: str,
            whisper_folder_path: str,
    ) -> str:
        setup2323()
        audio_id = datautils.gen_random_string(10)
        audio_path = os.path.join(temp_folder, f"{audio_id}.wav")
        logger.debug(f"Extracting audio from video {video_path} to {audio_path}")
        VideoUtils.extract_audio(video_path, audio_path)

        # Scarica il modello di Whisper
        logger.debug(f"Loading Whisper model {model_name}")
        modello = Whisper.get_model_obj_from_lib(model_name, whisper_folder_path)

        # Trascrive l'audio e restituisce il testo
        logger.debug(f"Transcribing audio {audio_path}")
        risultato = modello.transcribe(audio_path)
        return risultato["text"]


    @staticmethod
    def transcribe_old(
        video_path: str,
        audio_path: str,
        model_path: str,
        transcription_path: str | None = None
    ):

        ignore_context_ssl()

        # Estrarre l'audio dal video
        video = mp.VideoFileClip(video_path)
        video.audio.write_audiofile(audio_path)

        # Caricare il modello Whisper
        model = whisper.load_model(model_path)

        # Trascrivere l'audio
        result = model.transcribe(audio_path)
        if transcription_path is not None:
            # Salvare la trascrizione su un file di test
            with open(transcription_path, 'w') as f:
                f.write(result["text"])
        return result
