# AI media scanner

`AiMediaScanner` esegue una o più scansioni AI su un singolo media e restituisce un oggetto `LizMedia` arricchito.

## Tool supportati

- `TAGS` → JoyTag
- `NSFW` → NudeNet
- `OCR` → EasyOCR

Sono accettati anche alias come `JOYTAG` e `TAG-JOYTAG`.

## Esempio rapido

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

## Input base64

```python
media = scanner.scan(
    base64_content=my_base64_payload,
    file_name="image.png",
    tools=["OCR"],
)
```

Per input base64 senza `file_name`, è supportato anche il formato data URI, ad esempio:

```text
data:image/png;base64,...
```

## Dipendenze opzionali

Installare l'extra `ai` per abilitare gli scanner reali:

```bash
pip install .[ai]
```

I test unitari in `test/ai/ai_media_scanner.py` usano provider stub e non richiedono i modelli AI reali.

