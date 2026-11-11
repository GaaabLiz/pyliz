# Manutenzione del sistema snapshot

L'API pubblica rimane disponibile tramite `pylizlib.core.os.snap` e i moduli
storici. Il refactor separa le responsabilità interne conservando formati,
firme, valori restituiti e comportamenti in caso di errore.

## Da dove iniziare

| Esigenza | Modulo da leggere |
|---|---|
| API su uno snapshot | `manager.py` |
| API sul catalogo e backup preventivi | `catalogue.py` |
| Modelli, enum, configurazione e invarianti | `domain.py` |
| Creazione, duplicazione e cancellazione | `operations/lifecycle.py` |
| Installazione e rimozione delle copie installate | `operations/install.py` |
| Aggiornamento delle copie interne dal sistema | `operations/sync.py` |
| Pianificazione ed esecuzione degli edit | `operations/edits.py` |
| Backup e ripristino | `operations/archives.py` |
| Generazione e parsing dei nomi dei backup | `operations/backup_names.py` |
| Import/export del catalogo | `operations/transfers.py` |
| Percorsi contenuti nello storage | `storage/paths.py` |
| Scansione e politiche sui link | `storage/tree.py` |
| Pubblicazione delle directory e pulizia | `storage/publication.py` |
| Primitive di lettura e scrittura ZIP | `storage/archives.py` |
| Conversione JSON e file descriptor protetti | `storage/metadata.py` |
| Scansione delle voci del catalogo | `storage/catalogue.py` |
| Dipendenze di una singola operazione | `storage/context.py` |
| Journal e recupero delle transazioni | `storage/transactions.py` |
| Copia di un'associazione nel suo storage | `storage/association.py` |
| Strategie di copia e sorgenti stabili | `copy_strategy.py` |
| Validazione e confronto dei manifest | `integrity.py` |
| Query, ricerca e risoluzione dei percorsi | `searcher.py` |
| Contratti delle callback | `callbacks.py` |
| Confronto delle associazioni e ordinamento | `diff.py`, `sorting.py` |
| Generazione di esempi casuali | `factories.py` |

Le scritture dei metadati preparano un file temporaneo nella stessa directory,
sincronizzano i suoi contenuti, conservano i byte precedenti in un sidecar
`.previous` e pubblicano con `os.replace`. Se il flush finale della directory
fallisce dopo la rinomina, `MetadataDurabilityError.published` distingue il
JSON già visibile da una scrittura non pubblicata. Su SMB/NFS un `fsync`
completato è comunque soltanto la conferma del sistema/server: la libreria non
può attestare che il server abbia persistito i byte su supporto stabile.
`SnapshotManager.install()` segnala con `SnapshotInstallMetadataError` un errore
di `date_last_used` dopo il commit dei dati. L'eccezione indica che le directory
sono già state installate, espone `metadata_published` (True, False o None se
l'adapter non può determinarlo). In modalità sostituzione lascia le copie
precedenti temporanee per il recupero; il merge non crea sempre copie di backup.
Un adapter alternativo dovrebbe esporre `published` e
`durability_confirmed` sulle eccezioni di scrittura post-pubblicazione.

I backup e i ripristini delle directory associate richiedono che tutte le
associazioni siano presenti. Se manca una sorgente o una cartella nell'archivio,
viene sollevata `SnapshotIncompleteError`; `missing_folders` contiene i percorsi
originali mancanti e `unexpected_entries` le voci dell'archivio senza
corrispondenza. Il ripristino controlla l'insieme completo prima di modificare
le destinazioni.

La destinazione di un backup deve risolversi fuori dagli alberi che verranno
archiviati. Questo evita di includere ZIP precedenti e viene controllato anche
quando la destinazione usa un alias o un link simbolico.

I nuovi backup AD e SD includono `.pyliz_backup_manifest.json` con versione,
tipo, ID e nome snapshot, data, prefisso, OS di provenienza e associazioni
(ID, indice, nome interno e percorso originario). Il restore e
`list_backups()` leggono questi dati dall'archivio; rinominare lo ZIP non cambia
il tipo o l'identità. Prima di
installare, ripristinare o rimuovere copie, la libreria verifica che le
destinazioni non siano critiche, sovrapposte al catalogo o coincidenti/annidate
fra loro. Se un percorso non può essere risolto, l'operazione viene rifiutata.
I backup possono essere ripristinati anche dopo aver eliminato lo snapshot dal
catalogo. I vecchi manifest AD e gli archivi precedenti senza manifest
mantengono il percorso di compatibilità con i metadati del catalogo o col nome
legacy. Per cambiare destinazione,
`SnapshotCatalogue.restore_backup_with_mapping(zip_path, {folder_id: path})`
accetta una mappa dagli ID persistenti delle associazioni ai nuovi percorsi; le
associazioni non indicate mantengono il percorso salvato nell'archivio.

`utils.py` e `serializer.py` conservano le vecchie API come facciate. Le nuove
implementazioni interne usano direttamente i moduli responsabili, evitando di
passare dall'esportazione aggregata di `snap.__init__`.

## Composizione e interfacce

Manager e catalogo coordinano le operazioni; non contengono più i grandi
algoritmi di copia, pubblicazione o ripristino. I servizi ricevono dipendenze
esplicite e non ereditano da un manager generale.

`SnapshotStorage` viene costruito a ogni invocazione del manager usando i suoi
attributi pubblici correnti. Conserva il riferimento al modello e alle
impostazioni, senza copiarli. Le destinazioni catturate dal manager continuano
a essere confrontate con i percorsi richiesti, per rilevare cambiamenti di ID
o del nome del JSON.

I contratti sono limitati alle capacità utilizzate:

- `DirectoryCopyStrategy` e `SourceSnapshotProvider` mantengono le ABC pubbliche
  esistenti e i controlli runtime sui tipi.
- `SnapshotMetadata` descrive salvataggio, lettura, aggiornamento parziale e
  accesso ai byte necessari al recupero. L'adapter predefinito è il serializer.
- `SnapshotPathLookup` descrive l'unica capacità del catalogo richiesta dalla
  ricerca; la firma storica del costruttore resta disponibile.
- `SnapshotLookup` permette il lookup usato dal restore delle associazioni.
- `CatalogueQuery` espone le letture necessarie ai trasferimenti ZIP.

La copia usa `SnapshotSettings.copy_metadata_mode`. Il default `BASIC` mantiene
il comportamento corrente: contenuti con `copy2`, metadati standard dei file e
delle sottocartelle, senza copiare gli attributi della directory radice
associata. Si seleziona il livello esteso con
`SnapshotSettings(copy_metadata_mode=CopyMetadataMode.EXTENDED)`. `EXTENDED`
decora la strategia configurata e conserva anche gli
attributi della radice, owner e group quando il processo ha i permessi
necessari, extended attributes (inclusi gli ACL esposti come attributi), ACL
DACL e alternate data streams su Windows, e i hardlink interni a ciascun albero
copiato. Se un metadato richiesto non è copiabile, la copia fallisce prima della
pubblicazione. Le caratteristiche non esposte dal sistema operativo o non
supportate dal filesystem di destinazione non sono garantibili; hardlink che
collegano associazioni diverse non vengono preservati perché le associazioni
sono copiate separatamente. Symlink e junction restano rifiutati in entrambe le
modalità. La modalità vale per le copie directory: i backup e gli export ZIP
non trasportano owner, ACL, extended attributes, ADS o topologia dei hardlink.

I record `EditMove`, `EditPlan`, `InstallReplacement`, `SyncReplacement` e
`RestoreReplacement` danno nomi espliciti ai dati prima conservati in tuple o
dizionari. I modelli contenuti restano mutabili: un record frozen non congela
lo snapshot e non ne introduce una copia.

## Journal e recupero dopo un arresto

Le sostituzioni di snapshot, le modifiche delle associazioni, la sincronizzazione,
l'installazione e il ripristino delle associazioni registrano le fasi in
`.pyliz_transactions` sullo stesso storage dei dati coinvolti. Il journal viene
pubblicato atomicamente tramite `SnapshotSerializer`; gli aggiornamenti del suo
stato precedono le azioni che la recovery deve completare o annullare. Le rinomine
sincronizzano le directory coinvolte quando il filesystem lo supporta. Su SMB,
NFS e piattaforme che non offrono questa conferma, la libreria può rilevare e
recuperare stati lasciati da un arresto del processo, ma non può attestare la
persistenza fisica sul server.

La recovery viene eseguita quando il catalogo carica gli snapshot e prima delle
successive operazioni che modificano o copiano i relativi alberi. Lo stato
`prepared` viene annullato; `commit_decided` viene completato; `committed` ripete
soltanto la pulizia. Se un journal è illeggibile o una copia attesa manca, la
recovery si ferma e conserva journal e copie disponibili invece di proseguire
sopra dati ambigui. Le copie precedenti vengono eliminate soltanto dopo che il
journal registra il commit.

| Flusso | Ordine e limite da conservare |
|---|---|
| Creazione | Preparare associazioni e JSON nello staging, poi pubblicare la radice. La recovery completa la pubblicazione se il commit era già deciso. |
| Edit | Pianificare sulle identità persistite, spostare gli originali, pubblicare e salvare; se la pubblicazione JSON non avviene, ripristinare directory, byte e modello. Se avviene ma il flush fallisce, mantenere il nuovo stato e conservare le directory rimosse ancora nello staging. |
| Sincronizzazione | Preparare tutte le copie, sostituire, aggiornare dimensioni/manifest e salvare; ripristinare copie e metadati in memoria secondo il protocollo esistente. |
| Installazione | Rifiutare prima dello staging destinazioni coincidenti o annidate; verificare e preparare tutte le copie prima di modificare i target; salvare `date_last_used` dopo il commit dei contenuti. |
| Merge di installazione | Sostituire le collisioni di primo livello; non introdurre un merge ricorsivo. |
| Restore `_ad` | Ripristinare le associazioni riconosciute con staging e journal; il recupero completa o annulla lo swap dopo un arresto. |
| Pulizia dopo commit | Registrare gli errori e proseguire, senza riattivare il rollback di dati già pubblicati. |

Una correzione che modifica questi limiti richiede una decisione funzionale e
propri test: non va inserita in uno spostamento di codice.

## Altri vincoli di compatibilità

- Le associazioni calcolano ancora `mb_size` nel costruttore quando manca;
  `validate()` normalizza ancora `original_path` e viene chiamato dalle
  proprietà che già lo facevano.
- I default `SnapshotSettings()` dei due costruttori pubblici mantengono la
  condivisione storica. Non aggiungere copie o ricostruzioni implicite.
- Il diff usa `folder_id` come identità stabile e conserva l'ordine di aggiunte,
  rimozioni e rinomine. Le azioni legacy vengono risolte prima delle modifiche.
- Il JSON conserva UTF-8, indentazione, date ISO e fallback legacy. Gli
  aggiornamenti parziali preservano campi extra senza costruire un modello;
  tutte le scritture predefinite sono pubblicate atomicamente e conservano la
  versione precedente nel sidecar `.previous`.
- Il serializer risolve i propri hook nell'ordine storico: leggere/validare,
  preparare i dati, selezionare il converter, codificare, risolvere il writer.
- I controlli sui link prima e dopo I/O non sono duplicazioni da eliminare.
  Traversal per backup, storage e ricerca mantengono politiche distinte.
- Il manifest persistito e il fingerprint interno della copia verificata
  restano rappresentazioni differenti. La verifica per tentativi non equivale
  a una sorgente congelata dal filesystem/provider.
- La presenza di una callback può attivare la scansione dei byte nella copia.
  Create mantiene l'adapter anche senza osservatore; install passa `None`.
- Nella ricerca soltanto `False` interrompe il ciclo corrente, prima di leggere
  quel file. La ricerca degli snapshot successivi continua.
- L'import del catalogo gestisce gli errori per voce e legge inizialmente solo
  l'ID; l'import singolo valida invece l'intero modello.

## Verifiche prima di modificare

Dalla root del repository:

```sh
.venv/bin/python -m pytest test/core/os/snap -q --disable-warnings
.venv/bin/ruff check pylizlib/core/os/snap
```

I test di caratterizzazione sono in `test_refactor_contracts.py`; quelli dei
moduli estratti e delle strategie sono in `test_refactor_modules.py`.
`test_public_api.py` confronta le dichiarazioni pubbliche con la fixture della
revisione precedente al refactor e richiede docstring per classi, funzioni e
callback annidate.

Per modifiche ai flussi filesystem verificare sia il successo sia errori di
copia, rinomina, salvataggio e cleanup. Confrontare contenuti, JSON e stato in
memoria. Usare copie locali isolate: gran parte dei vecchi test condivide una
root di fixture e non è predisposta per esecuzione parallela. Le prove Windows
nella suite simulano le API ACL; non sostituiscono una verifica su Windows reale.
