import os

import cv2
import ffmpeg
import numpy as np

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.path import get_filename, check_path, check_path_file
from pylizlib.media.compute.frameselector import FrameSelector
from pylizlib.media.domain.video import FrameOptions
from pylizlib.media.util.image import save_ndarrays_as_images


class VideoUtils:

    @staticmethod
    def extract_audio(video_path, audio_path, use_existing=False):
        if use_existing and os.path.exists(audio_path):
            logger.debug(f"Audio file for {get_filename(video_path)} already exist: {audio_path}")
            return
        ffmpeg.input(video_path).output(audio_path).run(overwrite_output=True)

    # @staticmethod
    # def _extract_audio_librosa(video_path: str, target_sampling_rate) -> Tuple[np.ndarray, int]:
    #     """Extract audio from video file and return as numpy array with sampling rate using librosa"""
    #     try:
    #         # Load audio using librosa
    #         raw_audio, original_sampling_rate = librosa.load(
    #             video_path,
    #             sr=target_sampling_rate,
    #             mono=True
    #         )
    #
    #         # Ensure float32 dtype and normalize
    #         raw_audio = raw_audio.astype(np.float32)
    #         if np.abs(raw_audio).max() > 1.0:
    #             raw_audio = raw_audio / np.abs(raw_audio).max()
    #
    #         logger.debug(f"Raw audio shape: {raw_audio.shape}, dtype: {raw_audio.dtype}")
    #
    #         return raw_audio, original_sampling_rate
    #
    #     except Exception as e:
    #         logger.error(f"Error extracting audio with librosa: {str(e)}")
    #         raise


    @staticmethod
    def extract_frame_advanced(
            video_path,
            frame_folder,
            frame_selector: FrameSelector,
            frame_options: FrameOptions = FrameOptions(),
            use_existing=True
    ):
        # # controllo se esistono già i frame
        # if use_existing and len(os.listdir(frame_folder)) > 0:
        #     logger.debug(f"Frames already exist in {frame_folder}. Reading existing frames...")
        #     frames = imgutils.load_images_as_ndarrays(frame_folder)
        #     if len(frames) > 0:
        #         return frames
        #     else:
        #         logger.warning(f"Frames has been found in {frame_folder}, but no frames were loaded. Extracting frames again...")
        #         shutil.rmtree(frame_folder)

        # estratto i frame con il frame selector
        frame_list = frame_selector.select_frames(video_path, frame_options)
        frames_list_images = [frame.image for frame in frame_list]
        save_ndarrays_as_images(frames_list_images, frame_folder)
        return frame_list


    @staticmethod
    def extract_frames_thr(
            video_path,
            output_folder,
            difference_threshold=30,
            use_existing=True
    ):
        check_path_file(video_path)
        check_path(output_folder, True)

        # Se esistono già i frame, non fare nulla
        if use_existing and len(os.listdir(output_folder)) > 0:
            logger.debug(f"Frames already exist in {output_folder}. Exiting frame extraction.")
            return

        # Apri il video
        cap = cv2.VideoCapture(video_path)

        # Contatore per numerare i frame
        frame_count = 0
        saved_frame_count = 0

        # Leggi il primo frame
        ret, prev_frame = cap.read()
        if not ret:
            cap.release()
            cv2.destroyAllWindows()
            raise Exception("OPenCV error: Error reading video")

        # Converti il primo frame in scala di grigi
        prev_frame_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

        # Salva il primo frame
        file_name = os.path.basename(video_path).split(".")[0]
        frame_path = os.path.join(output_folder, f"{file_name}_frame_{saved_frame_count}.jpg")
        cv2.imwrite(frame_path, prev_frame)
        saved_frame_count += 1

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # Converti il frame corrente in scala di grigi
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Calcola la differenza assoluta media tra il frame corrente e quello precedente
            diff = cv2.absdiff(frame_gray, prev_frame_gray)
            mean_diff = np.mean(diff)

            # Se la differenza è maggiore della soglia, salva il frame
            if mean_diff > difference_threshold:
                file_name = os.path.basename(video_path).split(".")[0]
                frame_path = os.path.join(output_folder, f"{file_name}_frame_{saved_frame_count}.jpg")
                cv2.imwrite(frame_path, frame)
                saved_frame_count += 1
                prev_frame_gray = frame_gray  # Aggiorna il frame precedente
                logger.trace(f"Frame {frame_count} saved because threshold exceeded: {mean_diff}")

            frame_count += 1
            logger.trace(f"Frame {frame_count} processed, {saved_frame_count} frames saved")

        # Rilascia la cattura del video e chiudi le finestre
        cap.release()
        cv2.destroyAllWindows()
