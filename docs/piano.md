# Piano di lavoro

Obiettivo: nome (in qualsiasi grafia) → tutte le sue varianti → tutti i punti dell'inventario in cui compare (voce + segmento).

| Fase | Contenuto | Stato |
|---|---|---|
| 0 | Struttura del repository, `CLAUDE.md`, `docs/piano.md`, sorgente in `sorgenti/` | da fare |
| 1 | Parsing delle voci (testo, coda, annotazioni, numeri anomali) | fatto, da verificare sul report |
| 2 | Segmentazione interna con i soli riferimenti originali | fatto, da verificare sul report |
| 3 | Estrazione delle menzioni di persone e luoghi, con posizione | in corso: campione da rivedere |
| 4 | Raggruppamento delle varianti in entità (proposte) | da fare |
| 5 | Arricchimento da fonti esterne: forma d'intestazione e varianti note | da fare |
| 6 | Revisione del curatore, partendo dai nomi più frequenti | da fare |
| 7 | Interfaccia di ricerca: risultati con etichetta e segmento evidenziato | da fare |

## Fase 1 — Parsing
Un record per ogni numero d'inventario. Testo integrale intatto; riga di coda scomposta (supporto, volumi, stato, provenienza); annotazioni separate per tipo; intestazioni di sezione riconosciute e non confuse con voci. Report: numero di voci, numeri anomali, numeri mancanti o fuori sequenza, voci senza coda, residui.

## Fase 2 — Segmentazione
Divisione delle voci lunghe secondo i riferimenti presenti nel testo: ordinali (71 → «4°»), fogli/carte/pagine (10 → «fol. 45-47»; 102 → «19-23»), fascicoli (505 → «Fasc. 2°»), lettere (2635 → «a)»). Dove non ci sono riferimenti: voce intera. Report delle voci segmentate in modo dubbio, da controllare a campione.

## Fase 3 — Estrazione
Persone e luoghi, ciascuno con voce, segmento e posizione nel testo. Le correzioni tra quadre del curatore diventano varianti con origine `correzione_curatore`. Prima su campione (voci 1–100, 464–497, 2134), poi su tutto.

## Fase 4 — Raggruppamento
Nota del curatore: forme come «Sandaniello» possono indicare un luogo (San Daniele) ma anche una persona; prima di associarle a una forma normalizzata di luogo va controllato che non esista una persona storica con lo stesso nome normalizzato.

Proposta di entità che riuniscono le grafie dello stesso nome (Cortenovis/Cortinovis, Sbroiavacca/Sbrojavacca, Valvason/Valvasone, Jacopo/Giacomo, Utinum/Udine, Civitas Austriae/Cividale). Gli omonimi non si uniscono senza conferma.

## Fase 5 — Fonti esterne
Persone: Wikidata (ponte verso DBI e VIAF), VIAF, Nuovo Liruti, SBN, CERL Thesaurus. Luoghi: Wikidata, GeoNames, codici ISTAT; Pleiades per i luoghi antichi. Si prendono forma d'intestazione e varianti, con identificativo e URL.

## Fase 6 — Revisione
Pagina semplice per confermare o scartare raggruppamenti e collegamenti, ordinati per frequenza.

## Fase 7 — Ricerca
L'utente digita una grafia qualsiasi; la ricerca passa per normalizzazione + varianti e restituisce l'elenco dei punti (numero di voce, etichetta del segmento, testo del segmento con il nome evidenziato).

## Esecuzione (fasi 1 e 2)
```
python3 script/parser.py     # crea dati/inventario.sqlite (voci, annotazioni)
python3 script/segmenta.py   # popola la tabella segmenti
python3 script/report.py     # scrive report/report_fasi_1_2.md
```
Decisioni confermate dal curatore:
- `voci.testo` esclude coda e annotazioni; `voci.testo_integrale` conserva tutto; ogni annotazione registra la posizione.
- Valgono come coda anche «Provenienza: …» e il supporto isolato («Cartaceo»).
- Riferimenti ammessi oltre a quelli elencati: folio, foglio, f., ff., cc., elenchi «1)», «1.», «A)», «A.2)», «E bis)», solo a inizio proposizione e in sequenza.
- Elenchi alfabetici dichiarati in `segmenta.py` (2134, 525): il nome fa da etichetta.
- Preambolo e chiusura sono segmenti senza etichetta, di tipo distinto da `voce_intera`.
- Le annotazioni sul cambio di mano e sui catalogatori (es. dopo la voce 1596-bis) riguardano l'indice, non la voce: `annotazioni.sede = 'indice'`, `voce` vuota.
- Intestazioni di sezione: valgono come sezione solo se chiuse da una riga «Fine …» («Fine Archivio Manzano», «Fine sezione «Archivio della Porta»», «Fine Archivio Braida»); «Letteratura storica Friulana» non ha fine e non si propaga.
- «Omissione del n.° 3078: numero omesso.» diventa la voce 3078 (`tipo_numero = omesso`), con il testo intatto.
- Code intermedie (2691, 3790): la coda riguarda il testo che la precede; il testo successivo resta testo della voce.
- Segmentazione per livelli: fascicoli > numeri romani > elenchi numerati (1°, 1), 1.) > lettere > N. > carte/pagine. Le carte/pagine contano solo se non c'è una suddivisione più alta (es. 24: valgono 1°…10°, le pagine indicano solo la posizione).
- Esclusi: anni, formati («in-8°», «16°, pp. 8»), ordinali aggettivi («1° foglio», «del 1° libro»), consistenze («carte 21 legate», «FF. 2/9»), riferimenti isolati.
- Rinvii in coda o tra parentesi («…, carte 3-23;», «(carte 1-18)») aprono segmenti se sono almeno due.
- Voci a suddivisione discorsiva non riducibile a regole: `dati/segmentazioni_manuali.json` (5, 56, 1006, 1250), modificabile dal curatore.
- Nuovi livelli: opere («Op. I»), volumi («Il vol. I»), libri («libro 1», «lib. 3», «l.15»); forme «1.)», «8 e 9.)», «54) 55)», «32 a 40 incl.», «Fasc.° 2°», intervalli abbreviati («142-43)»).
- Il rinvio in coda al primo pezzo («…; da carte 1 a 35. Da carte 36…») apre il primo segmento.
- Controllo di qualità: continuità della numerazione (salti, inizio diverso da 1), per ogni forma separatamente. Le segnalazioni verificate dal curatore stanno in `dati/segmentazioni_verificate.json`; un elenco vuoto in `dati/segmentazioni_manuali.json` forza la voce intera.
- Elenchi annidati: etichetta composta con « › » («2° › 3°», «33) › a)», «II cartolare › 1°»). Un sottoelenco della stessa forma vale solo se l'elenco superiore prosegue dopo di esso o se l'elemento padre lo annuncia nella sua prima proposizione («5° Cartolare contenente tre fascicoli: 1° …»); un elenco di forma diversa dentro un elemento è sempre subordinato. Una seconda serie con gli stessi numeri della prima la ridescrive e resta in successione (1344, 1475). Padri non numerati ma nominati («il I», «Il II cartolare») diventano segmenti con quell'etichetta.

## Fase 3 — decisioni del curatore
- Si estraggono anche coda e annotazioni (sede registrata); i nomi nelle citazioni («…») si includono senza segnarli.
- Predicati nobiliari («Ermes di Colloredo»): una sola menzione di persona, nessun legame con il luogo. «di/da» + città (provenienza) si separa: «Pagani di Udine» → Pagani + Udine.
- Santi: tipo `santo`, da dirimere (persona, chiesa o luogo) in base alla quantità.
- Istituzioni: non si estraggono; si estrae il luogo che contengono.
- Liste: luoghi da ISTAT e GeoNames (peso forte/medio/debole), nomi di battesimo da Wikidata (it, la, fur), liste manuali in `dati/liste/`.
- Esecuzione: `python3 script/liste_esterne.py` (una volta), `python3 script/estrai.py [--campione]`, `python3 script/report_fase3.py`.
