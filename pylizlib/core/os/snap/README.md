# Manutenzione del sistema snapshot

L'API pubblica rimane disponibile tramite `pylizlib.core.os.snap` e i moduli
storici. Il refactor separa le responsabilità interne conservando formati,
firme, valori restituiti e comportamenti in caso di errore.

## Da dove iniziare

| Esigenza | Modulo da leggere |
|---|---|
| API su uno snapshot | `manager.py` |
| API sul catalogo e backup preventivi | `catalogue.py` |
| Dichiarazioni pubbliche dei modelli, enum, azioni e configurazione | `domain.py` |
| Validazione e operazioni sulle associazioni | `association_model.py` |
| Validazione, metadati e clonazione degli snapshot | `snapshot_model.py` |
| Creazione, duplicazione e cancellazione | `operations/lifecycle.py` |
| Installazione e rimozione delle copie installate | `operations/install.py` |
| Aggiornamento delle copie interne dal sistema | `operations/sync.py` |
| Pianificazione ed esecuzione degli edit | `operations/edits.py` |
| Facciata compatibile backup e ripristino | `operations/archives.py` |
| Creazione e ispezione degli archivi | `operations/backup/creation.py`, `inspection.py` |
| Piano, staging e pubblicazione del restore | `operations/backup/planning.py`, `restore.py` |
| Codec e regole delle associazioni archiviate | `operations/backup_manifest.py`, `backup/associations.py` |
| Generazione e parsing dei nomi dei backup | `operations/backup_names.py` |
| Import/export del catalogo | `operations/transfers.py` |
| Percorsi contenuti nello storage | `storage/paths.py` |
| Scansione rigorosa e politiche sui link | `core/os/filesystem/tree.py`; deleghe in `storage/tree.py` |
| Pubblicazione delle directory e pulizia | `storage/publication.py` |
| Primitive di lettura e scrittura ZIP | `core/os/archives/zip/`; deleghe in `storage/archives.py` |
| Limiti predefiniti per import e restore ZIP | `storage/archive_limits.py` |
| Conversione JSON snapshot | `storage/metadata.py` |
| File descriptor protetti e scritture atomiche | `core/os/filesystem/atomic.py` |
| Scansione delle voci del catalogo | `storage/catalogue.py` |
| Dipendenze di una singola operazione | `storage/context.py` |
| Persistenza e facciata journal | `storage/transactions.py` |
| Codec, dispatch e handler di recupero | `storage/recovery/` |
| Copia di un'associazione nel suo storage | `storage/association.py` |
| Contratti e classi pubbliche delle strategie | `copy_strategy.py` |
| Implementazioni sequenziale e verificata | `copying/file_strategies.py` |
| Implementazione della copia dei metadati estesi | `copying/metadata_strategy.py` |
| Implementazione provider, sessioni e capability metadata | `copying/provider.py`, `copying/session.py`, `copying/contracts.py` |
| Validazione e confronto dei manifest | `integrity.py` |
| Query pubbliche e risoluzione dei percorsi | `searcher.py` |
| Adapter di configurazione live e risultati | `searching.py` |
| Motore testuale, encoding, finestre e preview | `core/data/text/` |
| Ripristino del modello e stato di acquisizione | `model_state.py` |
| Contratti delle callback | `callbacks.py` |
| Confronto delle associazioni e ordinamento | `diff.py`, `sorting.py` |
| Generazione di esempi casuali | `factories.py` |

I percorsi che iniziano con `core/` sono relativi a `pylizlib/`. Gli altri sono
relativi a questo package. Le primitive generali non importano `snap`: possono
essere usate per altri dati e filesystem. In particolare:

- `core/os/paths/` distingue forma lessicale, identità filesystem e containment;
- `core/os/filesystem/` contiene alberi, metadati, fingerprint, capacità, entry,
  scrittura atomica e conferma delle rinomine;
- `core/os/windows/` isola drive, descrittori di sicurezza e alternate data streams,
  caricando i binding nativi soltanto quando chiamati;
- `core/os/archives/zip/` valida, estrae e pubblica archivi generici;
- `core/data/text/` legge testo e raccoglie match tramite contratti strutturali.

Le policy su ID, nomi riservati, associazioni, formati legacy e stati di commit
rimangono in `snap`. I vecchi moduli di storage restano disponibili come adapter
di compatibilità; il codice condiviso ha una sola implementazione.

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
precedenti temporanee per il recupero. Il merge registra invece le sostituzioni
delle entry di primo livello e le relative copie di rollback: non ricostruisce
un backup ricorsivo dell'intera destinazione.
Un adapter alternativo dovrebbe esporre `published` e
`durability_confirmed` sulle eccezioni di scrittura post-pubblicazione.

I backup e i ripristini delle directory associate richiedono che tutte le
associazioni siano presenti. Se manca una sorgente o una cartella nell'archivio,
viene sollevata `SnapshotIncompleteError`; `missing_folders` contiene i percorsi
originali mancanti e `unexpected_entries` le voci dell'archivio senza
corrispondenza. Il ripristino controlla l'insieme completo prima di modificare
le destinazioni.

## Ricerca dei contenuti

`SnapshotSearchParams` usa una lettura a blocchi e limita i candidati a
`max_files` (default 10.000), i risultati a `max_results` (default 1.000) e il
testo mostrato per riga a `max_line_preview_chars` (default 4.096). La
paginazione usa `result_offset`; in `search_list()` la pagina è condivisa fra
tutti gli snapshot. Le estensioni sono confrontate senza distinzione fra
maiuscole e minuscole e possono essere composte, ad esempio `.TAR.GZ`.

Se non viene indicata `encoding`, la ricerca riconosce BOM e UTF-16 senza BOM
con testo ASCII, prova UTF-8 e usa Windows-1252 se il testo non è UTF-8 valido. Se la
decodifica fallisce più avanti nel file, il file viene riletto con Windows-1252.
I file che il campione iniziale identifica come binari vengono saltati; un
errore di decodifica testuale non viene descritto come file binario. Per altri
codici si può impostare `encoding` esplicitamente.

Le query di testo e regex possono attraversare le righe. Il contenuto è letto
con blocchi da `chunk_size` (default 65.536 **caratteri decodificati**); il campione
iniziale per l'encoding è invece di 8.192 byte. Le regex hanno un timeout per
operazione di matching (`regex_timeout_seconds`, default 0,1 s), non una scadenza
globale della ricerca. `max_context_chars` (default 1.048.576 caratteri) è il
budget del contesto trattenuto fra i blocchi. Non impone una lunghezza massima
rigida a ciascun match: uno span più lungo può essere trovato quando entra nella
finestra corrente, ma non è garantito fra chunk e coda EOF. Solo `False`
interrompe la ricerca dello snapshot
corrente; la callback viene richiamata anche durante la lettura, così può
interrompere un file molto grande.

## Dimensioni e tempi di acquisizione

`SnapDirAssociation` non misura la sorgente nel costruttore o durante il
caricamento del JSON. Se `mb_size` manca resta `None`, così un lookup non avvia
scansioni potenzialmente lente su percorsi di rete. Dopo una copia riuscita,
create, aggiunta, edit e sincronizzazione calcolano `mb_size` dal manifest della
copia effettivamente acquisita. Una directory vuota acquisita ha dimensione
zero; un valore legacy sconosciuto resta distinto da zero fino alla prossima
acquisizione.

Le callback di copia non superano il 100% e ricevono un aggiornamento terminale
anche per alberi vuoti o quando la sorgente cambia dimensione durante la copia.
Senza callback, create non esegue la scansione preliminare dei byte per stimare
il progresso.

`date_created` conserva il significato storico di creazione dell'oggetto
metadata. `capture_started_at` e `capture_completed_at` registrano invece
l'inizio e la fine dell'ultima acquisizione completa eseguita da create o sync,
come timestamp UTC con offset esplicito (`+00:00`). Gli snapshot legacy hanno
entrambi i campi a `None` finché non vengono acquisiti di nuovo.

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

Import e restore SD rifiutano alberi che contengono lo storage operativo
`.pyliz_transactions` alla radice dello snapshot. L'import del catalogo verifica
tutti gli ingressi prima di pubblicare la prima voce. La riserva comprende le
varianti di maiuscole e i suffissi di punti/spazi che possono diventare alias
su Windows. Anche gli ID snapshot non possono occupare questo namespace.
I journal vengono creati localmente dalle operazioni; gli archivi trasportano
dati, senza introdurre istruzioni da eseguire al lookup successivo. Una cartella
con quel nome dentro i dati di un'associazione resta un normale contenuto.

La scrittura degli ZIP accetta anche timestamp sorgente precedenti al 1980 e li
limita all'intervallo rappresentabile dal formato. Import e restore controllano
prima dell'estrazione il numero di voci, il totale dei byte non compressi e lo
spazio disponibile, includendo il secondo staging necessario alla pubblicazione.
I limiti predefiniti sono 100 GiB e 1.000.000 di voci e si possono modificare o
disabilitare con `SnapshotSettings.max_archive_uncompressed_bytes` e
`max_archive_entries`. Import e restore SD usano il filesystem del catalogo per
lo staging; il restore AD sceglie il volume di una destinazione associata. Si può
impostare `SnapshotSettings.archive_temp_directory` per scegliere un altro
volume. Il controllo verifica anche lo spazio per la copia finale, ma non riserva
capacità contro scritture concorrenti.

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
- `MetadataCopyCapability` permette alla strategia estesa di mantenere aperta
  la sorgente stabile durante la copia degli attributi, senza dipendere dalla
  classe concreta del provider.
- `TextSearchConfiguration`, `MatchPage` e `TimedPattern` espongono al motore
  testuale soltanto configurazione live, pagine isolate per retry e matching
  con timeout. Il motore non conosce nomi o modelli snapshot.

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

`SnapDirAssociation.copy_install_to()` copia prima in uno staging privato e
pubblica soltanto il risultato completo. Una destinazione già presente, anche
comparsa durante la copia, causa un errore e non viene eliminata dal cleanup.
La pulizia gestisce esclusivamente lo staging posseduto dalla chiamata; manifest
in uscita e metadati dell'associazione vengono aggiornati dopo la pubblicazione.

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

- Le associazioni mantengono `mb_size=None` finché il contenuto non è acquisito;
  le misure salvate derivano dai manifest della copia. `validate()` normalizza
  `original_path` in un percorso assoluto ancorato alla
  directory corrente al momento della costruzione e viene chiamato dalle
  proprietà che già lo facevano. La normalizzazione è lessicale e non segue i
  link simbolici. Il JSON rifiuta percorsi relativi; su Windows i drive di rete
  mappati vengono convertiti nel percorso UNC quando la mappatura è disponibile.
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
- Una callback attiva la stima dei byte e riceve il completamento dei percorsi
  vuoti. Create passa `None` quando non c'è un osservatore, evitando la scansione
  preliminare; install passa `None` allo stesso modo.
- Nella ricerca soltanto `False` interrompe lo snapshot corrente; la callback
  viene chiamata prima di ciascun file e durante le letture a blocchi.
- L'import del catalogo gestisce gli errori per voce e legge inizialmente solo
  l'ID; l'import singolo valida invece l'intero modello.

## Verifiche prima di modificare

Dalla root del repository:

```sh
.venv/bin/python -m pytest test/core/test_documentation_contracts.py \
    test/core/os/snap test/core/os/filesystem test/core/os/paths \
    test/core/data/text -q --disable-warnings
.venv/bin/ruff check pylizlib/core/os/snap pylizlib/core/os/filesystem \
    pylizlib/core/os/paths pylizlib/core/os/windows pylizlib/core/os/archives \
    pylizlib/core/data/text
make docs-snap
```

I test di caratterizzazione sono in `test_refactor_contracts.py`; quelli dei
moduli estratti e delle strategie sono in `test_refactor_modules.py`.
`test_public_api.py` e `test_second_refactor_contracts.py` confrontano firme,
default, identità e campi pubblici con le fixture precedenti ai due refactor.
`test/core/test_documentation_contracts.py` richiede sezioni Google tipizzate
per parametri, ritorni/yield e campi dichiarati, oltre alla riga vuota prima
dei blocchi di commento. Questi controlli strutturali affiancano la review del
significato e i test comportamentali; non provano da soli la correttezza del testo.

La preview HTML è in `temp_local/docs_snap_preview/index.html` e viene generata
con il gruppo `dev` già dichiarato nel progetto. L'HTML storico sotto `docs/`
va rigenerato esplicitamente prima di pubblicare la documentazione aggiornata.

Per modifiche ai flussi filesystem verificare sia il successo sia errori di
copia, rinomina, salvataggio e cleanup. Confrontare contenuti, JSON e stato in
memoria. Usare copie locali isolate: gran parte dei vecchi test condivide una
root di fixture e non è predisposta per esecuzione parallela. I test nativi Windows
richiedono un runner Windows e dichiarano gli skip per capacità non disponibili;
i mock di drive, ACL e ADS verificano separatamente errori e ordine delle chiamate.
Una suite locale su un altro OS non dimostra l'equivalenza delle chiamate Win32.
I backend drive/ADS conservano quindi i binding esistenti dietro il nuovo confine:
una loro sostituzione richiede prima prove native di conformità. Anche SMB/NFS
richiedono un ambiente reale per dichiarare garanzie aggiuntive di persistenza.

## Log nell'applicazione

Il logger condiviso `PylizLib` mantiene il proprio `NullHandler`: la libreria non
installa handler e non cambia il livello globale. L'applicazione configura il
logging secondo le proprie esigenze. Gli eventi INFO descrivono le operazioni
e il recupero effettivo; DEBUG espone fasi, decisioni del journal già persistite,
formato dei backup e conteggi della ricerca. Query, contenuti dei file, preview
e JSON completi non vengono aggiunti ai log. Alcuni messaggi contengono ID e
percorsi necessari a identificare la fase; l'applicazione gestisce la loro
visibilità.
