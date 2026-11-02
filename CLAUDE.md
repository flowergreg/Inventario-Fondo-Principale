# Inventario del Fondo Principale (Biblioteca Civica «V. Joppi», Udine) — regole di progetto

## Scopo
Database di supporto alla ricerca nella trascrizione dell'inventario dei manoscritti del Fondo Principale (voci 1–4519, a cura di Gregorio Grasselli).

Unico obiettivo: chi cerca un nome di persona o di luogo, in qualsiasi grafia, deve trovare **tutte** le voci in cui compare e, quando la voce lo permette, il punto preciso della voce (segmento). Non si registrano ruoli, biografie, date o altre informazioni sulle persone.

## Regole fisse
1. **Il testo dell'inventario non si altera mai.** Normalizzazioni, correzioni e forme ufficiali vivono in campi separati.
2. I file in `sorgenti/` sono di sola lettura.
3. **Segmenti etichettati solo con riferimenti presenti nel testo** (1°, 2°…; fol.; carte / c.; pag. / p.; Fasc.; N.; a) b)…). Nessuna numerazione progressiva inventata. Se la voce non ha riferimenti interni, il segmento è la voce intera. Negli elenchi alfabetici (es. 2134) il nome stesso fa da riferimento.
4. **Ogni variante registra la sua origine**: `testo` (voce e posizione), `correzione_curatore` (forme tra quadre, es. «Marlupino [Morlupino]»), `fonte_esterna` (nome fonte e identificativo), `manuale`.
5. I raggruppamenti automatici in entità hanno stato `proposto`; diventano `validato` solo dopo conferma del curatore.
6. **Mai perdere testo**: ciò che il parser non sa classificare va in un campo `residuo` e nel report.
7. Fonti esterne solo tramite API o dati aperti (Wikidata, VIAF, GeoNames…). Si conservano forma, identificativo e URL; mai il testo delle voci biografiche.
8. Si lavora su branch, mai direttamente su main. Commit, messaggi, codice commentato e documentazione in italiano.

## Struttura della sorgente (`sorgenti/Inventario_Fondo_Principale.docx`)
- Prima della voce 1: titolo, curatore, nota introduttiva, data. Non sono voci.
- **Voce**: paragrafo che inizia (dopo tabulazione) con «numero. descrizione». Una voce può proseguire su più paragrafi fino al numero successivo.
- **Numeri anomali**: 542 a., 2528 bis, 2630/1, 2565/66 (voci fuse), 3014 bis, 1596-bis, 2559 bis, 3388 A… e numeri mancanti o saltati (es. 2726, 3078). Vanno conservati come stringa originale più una chiave di ordinamento.
- **Riga di coda**: «Supporto · n vol. · stato: x · provenienza» (campi separati da « · »; non sempre tutti presenti, a volte assente).
- **Annotazioni**: «[Nota a margine: …]», «[Commento del compilatore: …]», «[Commento a matita: …]» e simili. Natura dell'annotazione in grassetto, testo in carattere minore.
- **Intestazioni di sezione** fuori dalle voci (es. «Letteratura storica Friulana», «Archivio Manzano», «Fine Archivio Braida»).
- **Correzioni del curatore tra quadre** dentro il testo: «Marlupino [Morlupino]», «1796 [1769]».

## Schema logico (SQLite)
- `voci` (numero_originale, chiave_ordinamento, testo, coda, supporto, volumi, stato, provenienza, residuo)
- `annotazioni` (voce, tipo, testo)
- `segmenti` (id, voce, etichetta, testo, inizio, fine) — etichetta vuota = voce intera
- `menzioni` (id, segmento, testo_esatto, inizio, fine, tipo [persona | luogo], entita)
- `entita` (id, tipo, forma_intestazione, stato [proposto | validato])
- `varianti` (entita, forma, forma_normalizzata, origine, riferimento)
- `identificatori` (entita, fonte, codice, url, forma_autorizzata, data_verifica)

## Normalizzazione per la ricerca
Applicata sia alla stringa cercata sia al testo: minuscole, niente accenti né segni diacritici, j→i, y→i, doppie semplificate, punteggiatura ignorata. Copre gli scarti minimi; le varianti registrate coprono quelli che la normalizzazione non può indovinare (Jacopo/Giacomo, Utinum/Udine).

## Note per il raggruppamento (fase 4)
Le seguenti forme non creano problemi all'utente (che cerca anche solo per cognome), ma vanno riconosciute per proporre i gruppi:
- forme inverse: «Florio Daniele» / «Daniele Florio»;
- particelle tra parentesi: «Colloredo (di) Ermes», «Brazzà (di) Antonio»;
- iniziali e abbreviazioni: «G. B.», «Gio. Batta», «A. M.», «Ant.°», «Fr.», «Co.», «ab.», «mons.», «D.r»;
- forme latine: *Utini*, *Civitatis Austriae*, *Forojulii*, *Hieronymus*;
- omonimi (più Daniele Florio, più Antonio Savorgnan, i Della Torre): mai unire senza conferma.
