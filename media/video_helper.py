import ffmpeg


class VideoUtils:

    @staticmethod
    def extract_audio(video_path, audio_path):
        # Estrae solo la traccia audio dal video
        ffmpeg.input(video_path).output(audio_path).run(overwrite_output=True)