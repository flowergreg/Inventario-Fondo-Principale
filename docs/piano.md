# Piano di lavoro

Obiettivo: nome (in qualsiasi grafia) → tutte le sue varianti → tutti i punti dell'inventario in cui compare (voce + segmento).

| Fase | Contenuto | Stato |
|---|---|---|
| 0 | Struttura del repository, `CLAUDE.md`, `docs/piano.md`, sorgente in `sorgenti/` | da fare |
| 1 | Parsing delle voci (testo, coda, annotazioni, numeri anomali) | fatto, da verificare sul report |
| 2 | Segmentazione interna con i soli riferimenti originali | fatto, da verificare sul report |
| 3 | Estrazione delle menzioni di persone e luoghi, con posizione | da fare |
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
