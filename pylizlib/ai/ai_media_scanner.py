from __future__ import annotations

from pathlib import Path

from pylizlib.ai.domain import AiScanResult, AiScanTool, AiToolScanner
from pylizlib.ai.providers import EasyOcrProvider, JoyTagProvider, NudeNetProvider
from pylizlib.media.lizmedia import LizMedia
from pylizlib.media.util.source import resolve_media_source


class AiMediaScanner:
    """
    Orchestrates one or more AI scans on a single media file and maps the results onto LizMedia.
    """

    def __init__(self, providers: list[AiToolScanner] | None = None):
        active_providers = providers if providers is not None else [JoyTagProvider(), NudeNetProvider(), EasyOcrProvider()]
        self._providers = {provider.tool: provider for provider in active_providers}

    def scan(
        self,
        *,
        tools: list[str],
        media_path: str | Path | None = None,
        base64_content: str | None = None,
        file_name: str | None = None,
    ) -> LizMedia:
        normalized_tools = AiScanTool.normalize_many(tools)
        source = resolve_media_source(media_path=media_path, base64_content=base64_content, file_name=file_name)

        try:
            media = LizMedia(source.path)
            media.base64_content = source.base64_content

            aggregate = AiScanResult()
            for tool in normalized_tools:
                provider = self._providers.get(tool)
                if provider is None:
                    raise ValueError(f"No provider configured for AI scan tool '{tool.value}'.")
                aggregate.merge(provider.scan(media))

            media.apply_ai_scan_result(
                tags=aggregate.tags,
                nsfw=aggregate.nsfw,
                ocr_text=aggregate.ocr_text,
                has_ocr_text=aggregate.ocr_detected,
                file_name=file_name or media.file_name,
            )
            return media
        except Exception:
            if source.is_temporary and source.path.exists():
                source.path.unlink(missing_ok=True)
            raise

    def scan_media(
        self,
        *,
        tools: list[str],
        media_path: str | Path | None = None,
        base64_content: str | None = None,
        file_name: str | None = None,
    ) -> LizMedia:
        return self.scan(
            tools=tools,
            media_path=media_path,
            base64_content=base64_content,
            file_name=file_name,
        )


