from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
import urllib.request
import warnings
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from pylizlib.ai.domain import AiScanResult, AiScanTool
from pylizlib.ai.utils import sample_video_frames, unique_preserving_order
from pylizlib.core.log.pylizLogger import logger

if TYPE_CHECKING:
    from pylizlib.media.lizmedia import LizMedia

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "bmp", "gif", "tiff", "tif"}
_VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm"}
_DEFAULT_MODEL_DIR = os.getenv("PYLIZ_AI_MODELS_PATH", os.path.expanduser("~/Documents/models"))


class BaseAiProvider(ABC):
    tool: AiScanTool

    @abstractmethod
    def scan(self, media: "LizMedia") -> AiScanResult:
        raise NotImplementedError


class JoyTagProvider(BaseAiProvider):
    tool = AiScanTool.TAGS

    def __init__(self, model_dir: str | None = None, confidence_threshold: float = 0.45, video_sample_frames: int = 5):
        self.model_dir = model_dir or _DEFAULT_MODEL_DIR
        self.confidence_threshold = confidence_threshold
        self.video_sample_frames = video_sample_frames
        self._model = None
        self._tag_list = None
        self._device = None
        self._tvf = None
        self._torch = None

    def scan(self, media: "LizMedia") -> AiScanResult:
        if media.extension.lstrip(".") not in _IMAGE_EXTENSIONS | _VIDEO_EXTENSIONS:
            return AiScanResult(tags=[])

        model, tag_list, device, tvf, torch = self._get_runtime()
        predicted_tags: list[str] = []

        if media.is_image:
            with Image.open(media.path) as image_file:
                image = image_file.convert("RGB")
                predicted_tags.extend(self._predict_from_image(image, model, tag_list, device, tvf, torch))
        elif media.is_video:
            for frame in sample_video_frames(media.path, max_frames=self.video_sample_frames):
                image = Image.fromarray(frame)
                predicted_tags.extend(self._predict_from_image(image, model, tag_list, device, tvf, torch))
        else:
            return AiScanResult(tags=[])

        return AiScanResult(tags=unique_preserving_order(predicted_tags))

    def _get_runtime(self):
        if self._model is not None:
            return self._model, self._tag_list, self._device, self._tvf, self._torch

        try:
            import torch
            import torchvision.transforms.functional as tvf
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise ImportError(
                "JoyTag scanning requires the optional AI dependencies. Install the 'ai' extra to enable TAGS scans."
            ) from exc

        model_path = snapshot_download(repo_id="fancyfeast/joytag", cache_dir=self.model_dir)
        py_file_path = os.path.join(model_path, "Models.py")
        if not os.path.exists(py_file_path):
            url = "https://huggingface.co/spaces/fancyfeast/joytag/resolve/main/Models.py"
            urllib.request.urlretrieve(url, py_file_path)

        spec = importlib.util.spec_from_file_location("joytag_module", py_file_path)
        joytag_module = importlib.util.module_from_spec(spec)
        sys.modules["joytag_module"] = joytag_module
        assert spec.loader is not None
        spec.loader.exec_module(joytag_module)
        vision_model = joytag_module.VisionModel

        if torch.cuda.is_available():
            device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            device = torch.device("mps")
        else:
            device = torch.device("cpu")

        with open(os.path.join(model_path, "top_tags.txt"), "r", encoding="utf-8") as handle:
            tag_list = [line.strip() for line in handle.readlines()]

        model = vision_model.load_model(model_path)
        model.eval()
        model = model.to(device)

        self._model = model
        self._tag_list = tag_list
        self._device = device
        self._tvf = tvf
        self._torch = torch
        return self._model, self._tag_list, self._device, self._tvf, self._torch

    def _predict_from_image(self, image, model, tag_list, device, tvf, torch) -> list[str]:
        resample_mode = getattr(getattr(Image, "Resampling", Image), "BILINEAR")

        image = image.resize((448, 448), resample=resample_mode)
        image_tensor = tvf.to_tensor(image)
        image_tensor = tvf.normalize(
            image_tensor,
            [0.48145466, 0.4578275, 0.40821073],
            [0.26862954, 0.26130258, 0.27577711],
        )
        image_tensor = image_tensor.unsqueeze(0).to(device)

        start_time = time.time()
        with torch.no_grad():
            batch = {"image": image_tensor}
            output = model(batch)

            if isinstance(output, dict):
                preds = output.get("tags")
                if preds is None:
                    for value in output.values():
                        if hasattr(value, "shape") and value.shape[-1] == len(tag_list):
                            preds = value
                            break
                    if preds is None:
                        preds = list(output.values())[0]
            elif isinstance(output, (tuple, list)):
                preds = output[0]
            else:
                preds = output

            if preds.dim() > 1:
                preds = preds.squeeze(0)
            preds = torch.sigmoid(preds)

        logger.debug(f"JoyTag inference completed in {round(time.time() - start_time, 2)}s for {len(tag_list)} tags.")
        return [tag_list[i] for i, prediction in enumerate(preds) if prediction > self.confidence_threshold]


class EasyOcrProvider(BaseAiProvider):
    tool = AiScanTool.OCR

    def __init__(self, model_dir: str | None = None, languages: list[str] | None = None, video_sample_frames: int = 5):
        self.model_dir = model_dir or _DEFAULT_MODEL_DIR
        self.languages = languages or ["en"]
        self.video_sample_frames = video_sample_frames
        self._reader = None

    def scan(self, media: "LizMedia") -> AiScanResult:
        reader = self._get_reader()
        texts: list[str] = []

        if media.is_image:
            texts.extend(self._extract_texts(reader.readtext(str(media.path))))
        elif media.is_video:
            for frame in sample_video_frames(media.path, max_frames=self.video_sample_frames):
                texts.extend(self._extract_texts(reader.readtext(frame)))
        else:
            return AiScanResult(ocr_text=[], ocr_detected=False)

        normalized_texts = unique_preserving_order(texts)
        return AiScanResult(ocr_text=normalized_texts, ocr_detected=bool(normalized_texts))

    def _get_reader(self):
        if self._reader is not None:
            return self._reader

        try:
            import easyocr
            import torch
        except ImportError as exc:
            raise ImportError(
                "OCR scanning requires the optional AI dependencies. Install the 'ai' extra to enable OCR scans."
            ) from exc

        self._reader = easyocr.Reader(
            self.languages,
            gpu=torch.cuda.is_available(),
            model_storage_directory=self.model_dir,
            verbose=False,
        )
        return self._reader

    @staticmethod
    def _extract_texts(results: list) -> list[str]:
        texts: list[str] = []
        for result in results:
            if isinstance(result, (tuple, list)) and len(result) >= 2:
                text = str(result[1]).strip()
                if text:
                    texts.append(text)
        return texts


class NudeNetProvider(BaseAiProvider):
    tool = AiScanTool.NSFW

    EXPLICIT_LABELS = {
        "FEMALE_BREAST_EXPOSED",
        "FEMALE_GENITALIA_EXPOSED",
        "MALE_GENITALIA_EXPOSED",
        "BUTTOCKS_EXPOSED",
        "ANUS_EXPOSED",
    }

    def __init__(self, inference_threshold: float = 0.5, video_sample_frames: int = 5):
        self.inference_threshold = inference_threshold
        self.video_sample_frames = video_sample_frames
        self._detector = None

    def scan(self, media: "LizMedia") -> AiScanResult:
        detector = self._get_detector()

        if media.is_image:
            return AiScanResult(nsfw=self._detect_image(detector, media.path))
        if media.is_video:
            for frame in sample_video_frames(media.path, max_frames=self.video_sample_frames):
                if self._detect_frame(detector, frame):
                    return AiScanResult(nsfw=True)
            return AiScanResult(nsfw=False)
        return AiScanResult(nsfw=False)

    def _get_detector(self):
        if self._detector is not None:
            return self._detector

        try:
            from nudenet import NudeDetector
        except ImportError as exc:
            raise ImportError(
                "NSFW scanning requires the optional AI dependencies. Install the 'ai' extra to enable NSFW scans."
            ) from exc

        self._detector = NudeDetector()
        return self._detector

    def _detect_image(self, detector, image_path: Path) -> bool:
        return self._contains_explicit_detection(detector.detect(str(image_path)))

    def _detect_frame(self, detector, frame) -> bool:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as handle:
            Image.fromarray(frame).save(handle.name)
            return self._detect_image(detector, Path(handle.name))

    def _contains_explicit_detection(self, detections: list[dict]) -> bool:
        for detection in detections or []:
            label = str(detection.get("class") or detection.get("label") or "").upper()
            score = float(detection.get("score") or detection.get("confidence") or 0.0)
            if score < self.inference_threshold:
                continue
            if label in self.EXPLICIT_LABELS or label.endswith("_EXPOSED"):
                return True
        return False



