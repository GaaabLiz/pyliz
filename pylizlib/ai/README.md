# AI media scanner

`AiMediaScanner` runs one or more AI scans on a single media file and returns an
enriched `LizMedia` object.

## Supported tools

- `TAGS` → JoyTag
- `NSFW` → NudeNet
- `OCR` → EasyOCR

Aliases such as `JOYTAG` and `TAG-JOYTAG` are also accepted.

## Quick example

```python
from pylizlib.ai import AiMediaScanner

scanner = AiMediaScanner()
media = scanner.scan(
    media_path="/absolute/path/image.jpg",
    tools=["TAGS", "OCR", "NSFW"],
)

print(media.ai_tags)
print(media.ai_has_ocr_text)
print(media.ai_nsfw)
```

## Base64 input

```python
media = scanner.scan(
    base64_content=my_base64_payload,
    file_name="image.png",
    tools=["OCR"],
)
```

For base64 input without `file_name`, data URI format is also supported, for
example:

```text
data:image/png;base64,...
```

## Optional dependencies

Install the `ai` extra to enable the real scanners:

```bash
pip install .[ai]
```

### Recommended platform setup

- **macOS (CPU/MPS)**

  `ai-macos` remains available as a compatibility alias for the `ai` extra.

```bash
uv pip install -e '.[ai-macos]'
```

- **Linux with an NVIDIA GPU (CUDA)**

```bash
uv pip install -e '.[ai-linux-nvidia]'
```

> Note: Linux with NVIDIA requires compatible CUDA drivers on the host; `torch`
> automatically uses `cuda` when available.

Unit tests in `test/unit/ai/ai_media_scanner.py` use stub providers and do not
require real AI models.

## Real integration tests

Integration tests are grouped by feature in
`test/integration/ai/test_media_scanner.py`.

This test:

- downloads images from the internet;
- uses `test_local/ai_media_scanner_integration` as a temporary work/cache directory;
- exercises `TAGS`, `NSFW`, and `OCR` through `AiMediaScanner` with real providers.

If the environment does not have the required AI dependencies or internet
connectivity, the tests are explicitly marked as `skipped`.

Run them with:

```bash
uv run pytest test/unit/ai/ai_media_scanner.py test/integration/ai/test_media_scanner.py test/unit/media/util/source.py -q
```

To save persistent reports under `test_local`:

```bash
mkdir -p test_local/ai_media_scanner_reports
uv run pytest test/integration/ai/test_media_scanner.py -vv \
  --junitxml=test_local/ai_media_scanner_reports/integration_junit.xml \
  | tee test_local/ai_media_scanner_reports/integration_run.log
```
