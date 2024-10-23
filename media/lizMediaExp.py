from media.liz_media import LizMedia
from util import fileutils


class LizMediaExporter:

    def __init__(self, media: LizMedia):
        self.media = media

    def export_to_json(self):
        fileutils.write_json_to_file(self.media.path, self.media.file_name + ".json", self.media.to_json_only_ai())
