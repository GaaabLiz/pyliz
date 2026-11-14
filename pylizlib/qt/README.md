# Qt

`pylizlib.qt` contiene componenti basati su PySide6 per interfacce desktop: configurazione e preferenze, menu e toolbar, risorse grafiche, widget e task in background.

## Aree principali

| Package o modulo | Contenuto |
| --- | --- |
| `domain/` | Tipi per configurazione, preferenze, temi, risorse e menu |
| `handler/` | Gestione di configurazione, azioni, toolbar e operazioni concorrenti |
| `util/` | Creazione di azioni e helper per layout e preferenze |
| `widget/` | Widget riutilizzabili, come selettori di percorso e status bar |
| `scripts.py` | Generazione di risorse Qt e moduli Python da file `.qrc` e CSS |
| `debug/` | Supporto per ispezionare operazioni durante lo sviluppo |

`Operation` e `OperationRunner` organizzano task, segnali, progresso, cancellazione ed esecuzione concorrente. `ResHandler` e i tipi in `domain/` gestiscono risorse grafiche e temi.

## Dipendenze e test

Installare l'extra `qt` per usare questi componenti:

```bash
uv sync --extra qt
```

I test unitari sono in `test/unit/qt/`; i flussi con widget reali sono in `test/integration/qt/`.
