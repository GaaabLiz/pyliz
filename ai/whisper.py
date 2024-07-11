import moviepy.editor as mp
import whisper

from network.ssl import ignore_context_ssl


def transcribe(
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
