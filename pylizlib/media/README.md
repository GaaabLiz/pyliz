# Media

`pylizlib.media` fornisce modelli e strumenti per lavorare con immagini, video
e audio. `LizMedia` raccoglie percorso, metadati, sidecar e informazioni di
scansione; gli altri moduli gestiscono operazioni specifiche.

## Aree principali

| Package o modulo | Contenuto |
| --- | --- |
| `lizmedia.py` | `LizMedia` e risultati di ricerca dei file multimediali |
| `domain/` | Tipi per sorgenti, audio e video |
| `compute/` | Selezione dei frame e campionamento dei video |
| `util/` | Sorgenti, immagini, metadati e lettura dei video |
| `view/` | Presentazione tabellare dei risultati |

Per sorgenti da file o base64, vedere `resolve_media_source` in
`pylizlib.media.util.source`. `LizMedia` è anche il payload usato dalle
scansioni AI, descritte in [ai/README.md](../ai/README.md).

## Dipendenze

Le funzioni di elaborazione multimediale richiedono l'extra `media`:

```bash
uv sync --extra media
```

## Test

I test unitari sono in `test/unit/media/`. Le integrazioni AI sono in
`test/integration/ai/` e possono richiedere modelli e accesso a Internet.
