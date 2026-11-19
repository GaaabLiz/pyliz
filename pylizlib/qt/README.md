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

Per mostrare l’ETA all’avvio, puoi passare una durata iniziale in secondi con
`OperationInfo("Ricerca", "Cerca nei file", estimated_duration=8.0)`.
La stima si ricalibra man mano che i task avanzano. Senza una durata iniziale, l’ETA appare dopo due avanzamenti distinti,
così la fase di preparazione prima del primo aggiornamento resta fuori dal calcolo del ritmo di lavoro.
Il segnale `op_eta_update` viene emesso quando cambia il valore visualizzato.

## Dipendenze e test

Installare l'extra `qt` per usare questi componenti:

```bash
uv sync --extra qt
```

I test unitari sono in `test/unit/qt/`; i flussi con widget reali sono in `test/integration/qt/`.
