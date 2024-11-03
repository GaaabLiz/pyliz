import os
import tempfile

import moviepy.editor as mp
import whisper
from loguru import logger

from media.video_helper import VideoUtils
from network.ssl import ignore_context_ssl
from util import datautils


class Whisper:


    @staticmethod
    def get_model_obj(model_name: str, model_path: str):
        ignore_context_ssl()
        # Imposta la directory personalizzata per i modelli
        logger.debug(f"Setting WHISPER_CACHE_DIR to {model_path}")
        os.environ["WHISPER_CACHE_DIR"] = model_path
        # Carica il modello, che verrà scaricato se non già presente
        logger.debug(f"Loading Whisper model {model_name}")
        modello = whisper.load_model(model_name)
        return modello

    @staticmethod
    def transcribe(
            model_name: str,
            video_path: str,
            model_path: str,
    ) -> str:
        ignore_context_ssl()
        audio_id = datautils.gen_random_string(10)
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = f"{temp_dir}/audio-{audio_id}.wav"
        logger.debug(f"Extracting audio from video {video_path} to {audio_path}")
        VideoUtils.extract_audio(video_path, audio_path)

        # Scarica il modello di Whisper
        logger.debug(f"Loading Whisper model {model_name}")
        modello = Whisper.get_model_obj(model_name, model_path)

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
