# Core utilities

`pylizlib.core` raccoglie servizi e modelli riutilizzabili dalle altre parti
della libreria: configurazione, dati, rete, filesystem e operazioni di sistema.
I moduli sono importabili dalle rispettive sotto-cartelle, ad esempio
`pylizlib.core.os.paths` o `pylizlib.core.network`.

## Aree principali

| Package | Contenuto |
| --- | --- |
| `app/` | Configurazione INI e TOML e percorsi applicativi |
| `data/` | JSON, regex, conversioni, utilità e ricerca testuale a blocchi |
| `domain/`, `handler/`, `log/` | Modelli condivisi, supporto al progresso e logging |
| `network/` | Richieste HTTP, download e helper SSL |
| `os/paths/` | Normalizzazione, identità, containment e sicurezza dei path |
| `os/filesystem/` | File, directory, alberi, metadati, lock e scritture atomiche |
| `os/archives/zip/` | Validazione, estrazione e pubblicazione di ZIP |
| `os/windows/` | Adapter per funzionalità specifiche di Windows |
| `os/snap/` | Snapshot, catalogo, backup, restore, ricerca e recovery |

Le API snapshot pubbliche sono esposte da `pylizlib.core.os.snap`, tra cui
`Snapshot`, `SnapshotManager` e `SnapshotCatalogue`. Per i flussi e le garanzie
di sicurezza, consultare [la guida snapshot](os/snap/README.md).

I moduli `os/path.py`, `os/file.py` e `os/utils.py` mantengono gli import legacy;
il nuovo codice dovrebbe preferire `os/paths/` e `os/filesystem/`.

## Test

I test unitari seguono la struttura del package in `test/unit/core/`. I flussi
completi degli snapshot sono raccolti in `test/integration/snap/`.
