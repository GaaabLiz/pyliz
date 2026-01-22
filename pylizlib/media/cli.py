import logging
import os
from datetime import datetime

from pylizlib.core.app.pylizapp import PylizApp, PylizDirFoldersTemplate
from pylizlib.media import media_app
from pylizlib.media.script import organizer

# Initialize PylizApp
app = PylizApp("pyliz_media")
app.add_template_folder(PylizDirFoldersTemplate.LOGS)

# Setup Logger
log_folder = app.get_folder_template_path(PylizDirFoldersTemplate.LOGS)
timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
log_filename = f"pyliz_media_{timestamp}.log"
log_path = os.path.join(log_folder, log_filename)

# Create file handler
file_handler = logging.FileHandler(log_path)
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# Configure Root Logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
# Remove existing handlers to avoid console output or duplicates
if root_logger.hasHandlers():
    root_logger.handlers.clear()
root_logger.addHandler(file_handler)

# Create logger (optional, just for this module if needed, otherwise use root)
logger = logging.getLogger("pyliz_media") # This will now inherit from root and use the file handler


@media_app.command()
def temp():
    """
    Template command for media_app.
    """
    print("This is a temporary command in media_app.")


if __name__ == "__main__":
    media_app()