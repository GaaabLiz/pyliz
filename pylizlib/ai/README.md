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

### Setup consigliato per piattaforma

- **macOS (CPU/MPS)**

```bash
uv pip install -e '.[ai-macos]'
```

- **Linux con GPU NVIDIA (CUDA)**

```bash
uv pip install -e '.[ai-linux-nvidia]'
```

> Nota: per Linux NVIDIA servono driver CUDA compatibili lato host; `torch` usera `cuda` automaticamente quando disponibile.

I test unitari in `test/ai/ai_media_scanner.py` usano provider stub e non richiedono i modelli AI reali.

## Test di integrazione reali

È stato aggiunto anche `test/ai/ai_media_scanner_integration.py`.

Questo test:

- scarica immagini da internet;
- usa `/Users/gabliz/Developer/pyliz/test_local/ai_media_scanner_integration` come cartella di lavoro temporanea/cache;
- esercita davvero `TAGS`, `NSFW` e `OCR` tramite `AiMediaScanner`.

Se l'ambiente non ha ancora le dipendenze AI richieste o non ha connettività internet, i test vengono marcati come `skipped` in modo esplicito.

Esecuzione:

```bash
cd /Users/gabliz/Developer/pyliz
python -m pytest test/ai/ai_media_scanner.py test/ai/ai_media_scanner_integration.py test/media/util/source.py -q
```

Per salvare report persistenti in `test_local`:

```bash
cd /Users/gabliz/Developer/pyliz
mkdir -p /Users/gabliz/Developer/pyliz/test_local/ai_media_scanner_reports
python -m pytest test/ai/ai_media_scanner_integration.py -vv \
  --junitxml=/Users/gabliz/Developer/pyliz/test_local/ai_media_scanner_reports/integration_junit.xml \
  | tee /Users/gabliz/Developer/pyliz/test_local/ai_media_scanner_reports/integration_run.log
```

