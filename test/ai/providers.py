import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pylizlib.ai.providers import JoyTagProvider


class JoyTagProviderSecurityTestCase(unittest.TestCase):
    def test_model_and_executable_definition_use_immutable_revisions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_dir = Path(temp_dir)
            model_path = model_dir / "model"
            model_path.mkdir()
            (model_path / "top_tags.txt").write_text("tag\n", encoding="utf-8")
            code_path = model_dir / "Models.py"
            code_path.write_text(
                "class Model:\n"
                "    def eval(self): return self\n"
                "    def to(self, device): return self\n"
                "class VisionModel:\n"
                "    @staticmethod\n"
                "    def load_model(path): return Model()\n",
                encoding="utf-8",
            )

            torch = types.ModuleType("torch")
            torch.cuda = types.SimpleNamespace(is_available=lambda: False)
            torch.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False))
            torch.device = lambda name: name

            torchvision = types.ModuleType("torchvision")
            torchvision.__path__ = []
            transforms = types.ModuleType("torchvision.transforms")
            transforms.__path__ = []
            functional = types.ModuleType("torchvision.transforms.functional")
            torchvision.transforms = transforms
            transforms.functional = functional

            hub = types.ModuleType("huggingface_hub")
            snapshot_download = MagicMock(return_value=str(model_path))
            hf_hub_download = MagicMock(return_value=str(code_path))
            hub.snapshot_download = snapshot_download
            hub.hf_hub_download = hf_hub_download

            with patch.dict(
                sys.modules,
                {
                    "torch": torch,
                    "torchvision": torchvision,
                    "torchvision.transforms": transforms,
                    "torchvision.transforms.functional": functional,
                    "huggingface_hub": hub,
                },
            ):
                provider = JoyTagProvider(model_dir=temp_dir)
                model, _, device, _, _ = provider._get_runtime()

            self.assertEqual(device, "cpu")
            self.assertIsNotNone(model)
            self.assertEqual(snapshot_download.call_args.kwargs["revision"], "6b7f16331a6ccf0fdce37d5a9564715f6e772b22")
            self.assertEqual(hf_hub_download.call_args.kwargs["revision"], "df9e86f69b37ede2560de24503c18ac199e9b3f0")
            self.assertEqual(hf_hub_download.call_args.kwargs["repo_type"], "space")


if __name__ == "__main__":
    unittest.main()
