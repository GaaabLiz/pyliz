# Qt Fluent Widgets

`pylizlib.qtfw` raccoglie componenti basati su PySide6-Fluent-Widgets per impostazioni e interfacce desktop. Include modelli di configurazione, validatori, widget riutilizzabili e helper per la composizione delle UI.

## Aree principali

| Package | Contenuto |
| --- | --- |
| `domain/` | Modelli per impostazioni e dati software |
| `model/` | Validatori e helper per la configurazione Fluent |
| `widgets/` | Card, dialog, input, indicatori di progresso ed elementi testuali |
| `util/` | Helper per layout e operazioni UI |
| `ui/` | Demo dei componenti |

## Dipendenze e test

L'extra `qtfw` installa PySide6 e PySide6-Fluent-Widgets:

```bash
uv sync --extra qtfw
```

I test unitari si trovano in `test/unit/qtfw/`; i test dei flussi composti sono in `test/integration/qtfw/`. Per i componenti Qt generici, consultare [qt/README.md](../qt/README.md).
