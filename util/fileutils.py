import os
import platform
from datetime import datetime


def is_image_file(path: str) -> bool:
    image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.svg']
    return os.path.splitext(path)[1] in image_extensions


def is_video_file(path: str) -> bool:
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.3gp']
    return os.path.splitext(path)[1] in video_extensions


def is_audio_file(path: str) -> bool:
    audio_extensions = ['.mp3', '.wav', '.ogg', '.flac', '.wma', '.aac', '.m4a']
    return os.path.splitext(path)[1] in audio_extensions


def is_text_file(path: str) -> bool:
    text_extensions = ['.txt', '.doc', '.docx', '.pdf', '.odt', '.rtf', '.tex']
    return os.path.splitext(path)[1] in text_extensions


def is_image_or_video_file(path: str) -> bool:
    return is_image_file(path) or is_video_file(path)


def is_file_dup_in_dir(path:str, file_name:str) -> bool:
    for root, dirs, files in os.walk(path):
        if file_name in files:
            return True
    return False


def get_file_c_date(path_to_file) -> datetime:
    """
    Try to get the date that a file was created, falling back to when it was
    last modified if that isn't possible.
    See http://stackoverflow.com/a/39501288/1709587 for explanation.
    """
    if platform.system() == 'Windows':
        timestamp = os.path.getctime(path_to_file)
    else:
        stat = os.stat(path_to_file)
        try:
            timestamp = stat.st_birthtime
        except AttributeError:
            # We're probably on Linux. No easy way to get creation dates here,
            # so we'll settle for when its content was last modified.
            timestamp = stat.st_mtime

    # Convert timestamp to datetime object
    return datetime.fromtimestamp(timestamp)