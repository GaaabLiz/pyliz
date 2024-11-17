import os

import cv2
import ffmpeg
import numpy as np
from loguru import logger

from pylizlib.os import pathutils


class VideoUtils:

    @staticmethod
    def extract_audio(video_path, audio_path):
        # Estrae solo la traccia audio dal video
        ffmpeg.input(video_path).output(audio_path).run(overwrite_output=True)

    @staticmethod
    def extract_frames(video_path, output_folder, difference_threshold=30):
        pathutils.check_path_file(video_path)
        pathutils.check_path(output_folder, True)

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

            frame_count += 1
            logger.debug(f"Frame {frame_count} processed, {saved_frame_count} frames saved")

        # Rilascia la cattura del video e chiudi le finestre
        cap.release()
        cv2.destroyAllWindows()
