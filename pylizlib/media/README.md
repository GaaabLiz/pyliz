# Media

`pylizlib.media` provides models and tools for working with images, video, and
audio. `LizMedia` groups the path, metadata, sidecar files, and scan information;
the other modules handle specific operations.

## Main areas

| Package or module | Contents |
| --- | --- |
| `lizmedia.py` | `LizMedia` and media-file search results |
| `domain/` | Types for sources, audio, and video |
| `compute/` | Frame selection and video sampling |
| `util/` | Sources, images, metadata, and video reading |
| `view/` | Tabular presentation of results |

For file or base64 sources, see `resolve_media_source` in
`pylizlib.media.util.source`. `LizMedia` is also the payload used by AI scans,
documented in [ai/README.md](../ai/README.md).

## Dependencies

Media processing features require the `media` extra:

```bash
uv sync --extra media
```

## Tests

Unit tests are under `test/unit/media/`. AI integrations are under
`test/integration/ai/` and may require models and internet access.
