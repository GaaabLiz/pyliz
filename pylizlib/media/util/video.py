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
    """
    Utility class for video processing, including audio extraction, 
    frame extraction, and metadata retrieval (duration, FPS, creation date).
    """

    @staticmethod
    def extract_audio(video_path: str, audio_path: str, use_existing: bool = False):
        """
        Extracts the audio track from a video file using ffmpeg.

        Args:
            video_path: Path to the source video file.
            audio_path: Destination path for the extracted audio file.
            use_existing: If True, skips extraction if the audio file already exists.
        """
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
            video_path: str,
            frame_folder: str,
            frame_selector: FrameSelector,
            frame_options: FrameOptions = FrameOptions(),
            use_existing: bool = True
    ):
        """
        Extracts a set of frames from a video using a specific selector strategy.
        Saves the frames as images in the specified folder.

        Args:
            video_path: Path to the video file.
            frame_folder: Destination folder for the images.
            frame_selector: The strategy to use for selecting frames (e.g. Dynamic, Uniform).
            frame_options: Configuration settings for the selector.
            use_existing: Reserved for future optimization (currently always extracts).

        Returns:
            The list of extracted Frame objects.
        """
        # Extract frames using the provided selector
        frame_list = frame_selector.select_frames(video_path, frame_options)
        frames_list_images = [frame.image for frame in frame_list]
        save_ndarrays_as_images(frames_list_images, frame_folder)
        return frame_list


    @staticmethod
    def extract_frames_thr(
            video_path: str,
            output_folder: str,
            difference_threshold: int = 30,
            use_existing: bool = True
    ):
        """
        Extracts frames from a video based on a pixel difference threshold.
        Saves the frames as JPEGs in the output folder.

        Args:
            video_path: Path to the video.
            output_folder: Destination directory.
            difference_threshold: Mean absolute difference threshold to trigger a frame save.
            use_existing: If True and the folder is not empty, skips extraction.
        """
        check_path_file(video_path)
        check_path(output_folder, True)

        # Skip if frames already exist
        if use_existing and len(os.listdir(output_folder)) > 0:
            logger.debug(f"Frames already exist in {output_folder}. Exiting frame extraction.")
            return

        # Open the video
        cap = cv2.VideoCapture(video_path)

        # Counters for metadata
        frame_count = 0
        saved_frame_count = 0

        # Read the first frame
        ret, prev_frame = cap.read()
        if not ret:
            cap.release()
            cv2.destroyAllWindows()
            raise Exception("OpenCV error: Error reading video")

        # Convert the first frame to grayscale
        prev_frame_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

        # Save the first frame
        file_name = os.path.basename(video_path).split(".")[0]
        frame_path = os.path.join(output_folder, f"{file_name}_frame_{saved_frame_count}.jpg")
        cv2.imwrite(frame_path, prev_frame)
        saved_frame_count += 1

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # Convert current frame to grayscale
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Calculate the absolute difference between frames
            diff = cv2.absdiff(frame_gray, prev_frame_gray)
            mean_diff = np.mean(diff)

            # Save frame if threshold is exceeded
            if mean_diff > difference_threshold:
                file_name = os.path.basename(video_path).split(".")[0]
                frame_path = os.path.join(output_folder, f"{file_name}_frame_{saved_frame_count}.jpg")
                cv2.imwrite(frame_path, frame)
                saved_frame_count += 1
                prev_frame_gray = frame_gray  # Update previous frame
                logger.trace(f"Frame {frame_count} saved because threshold exceeded: {mean_diff}")

            frame_count += 1
            logger.trace(f"Frame {frame_count} processed, {saved_frame_count} frames saved")

        # Rilascia la cattura del video e chiudi le finestre
        cap.release()
        cv2.destroyAllWindows()

    @staticmethod
    def get_video_creation_date(path: str) -> float | None:
        """
        Retrieves the creation date of the video as a POSIX timestamp.
        Uses ffprobe to extract metadata tags like 'creation_time'.
        """
        try:
            from datetime import datetime
            probe = ffmpeg.probe(path)
            tags = probe.get('format', {}).get('tags', {})
            # Try apple specific tag first as it is more reliable for iPhone videos
            date_str = tags.get('com.apple.quicktime.creationdate') or tags.get('creation_time')
            if date_str:
                # Handle Z and other ISO formats
                try:
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    return dt.timestamp()
                except ValueError:
                    # Fallback for older python or slightly different formats
                    pass
        except Exception as e:
            logger.error(f"Errore nel recupero della data di creazione del video: {e}")
        return None

    @staticmethod
    def get_video_duration_seconds(path: str) -> float | None:
        """
        Retrieves the duration of the video in seconds using ffprobe.
        """
        try:
            probe = ffmpeg.probe(path)
            duration = float(probe['format']['duration'])
            return duration
        except Exception as e:
            logger.error(f"Error getting video duration: {str(e)}")
        return None

    @staticmethod
    def get_video_frame_rate(path: str) -> float | None:
        """
        Retrieves the frame rate (FPS) of the video using OpenCV.
        """
        try:
            video = cv2.VideoCapture(path)
            if not video.isOpened():
                logger.error("Error: could not open video.")
                return None

            # Get frame rate
            fps = video.get(cv2.CAP_PROP_FPS)
            video.release()

            return fps
        except Exception as e:
            logger.error(f"Error calculating video frame rate: {e}")
            return None
