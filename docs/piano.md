# Piano di lavoro

Obiettivo: nome (in qualsiasi grafia) → tutte le sue varianti → tutti i punti dell'inventario in cui compare (voce + segmento).

| Fase | Contenuto | Stato |
|---|---|---|
| 0 | Struttura del repository, `CLAUDE.md`, `docs/piano.md`, sorgente in `sorgenti/` | da fare |
| 1 | Parsing delle voci (testo, coda, annotazioni, numeri anomali) | fatto, da verificare sul report |
| 2 | Segmentazione interna con i soli riferimenti originali | fatto, da verificare sul report |
| 3 | Estrazione delle menzioni di persone e luoghi, con posizione | campione rivisto; revisione per forme su tutto l'inventario |
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
- Revisione su tutto l'inventario per forme: `python3 script/revisione_forme.py` → `report/fase_3_revisione_forme.md`. Decisioni globali in `dati/liste/decisioni_forme.tsv` (forma, tipo: persona | luogo | santo | opera | nessuno), eccezioni per voce in `dati/liste/classificazioni_manuali.tsv`.

## Lessico e scrematura (decisione del curatore)
La classificazione persona/luogo serve soprattutto a scegliere la fonte (enciclopedica o geografica); per la ricerca conta che ogni **parola** dei nomi sia ricondotta alla sua forma normalizzata (Zuane → Giovanni, Udene → Udine), comunque sia classificata la menzione. `python3 script/lessico.py` crea la tabella `lessico` (forma, parte, stato, forma normalizzata, origine, riferimento, gruppo grafico, occorrenze, voci) e `report/fase_3_lessico.md`, che elenca solo ciò che non è già normale:
- luoghi: normale se nome ufficiale ISTAT/GeoNames (o sua forma breve), altrimenti da normalizzare con proposta;
- nomi di battesimo: normale se forma italiana corrente (Wikidata), da normalizzare se abbreviati, latini, friulani, veneti (`dati/liste/nomi_varianti.tsv`);
- cognomi: da verificare nelle fonti (fase 5); varianti grafiche e simili come candidati;
- doppia lettura: nomi ufficiali di luoghi friulani e veneti che sono anche cognomi o famiglie (Savorgnano luogo ≠ Savorgnan famiglia): non si uniscono d'ufficio.
- Normalizzazione: le parole fatte solo di cifre romane non si semplificano (XVII ≠ XVI).
- **Forma normalizzata sempre italiana**, mai inglese (Sicilie → Sicilia, non Sicily) né latina (Julii → Giulio, non Julius). I luoghi esteri prendono il nome italiano dai nomi alternativi di GeoNames o da Wikidata (`dati/liste/geonames_it.tsv`); a parità di forma vince la città, non il quartiere. I nomi latini si convertono per regola (J/I+vocale → Gi, -ius → -io, -tius → -zio, -ae → -a, -onis → -one; irregolari: Petrus → Pietro, Thomas → Tommaso, Hieronymus → Girolamo) e il risultato deve esistere nella lista dei nomi italiani.
- «Jac.», «Jacobum»: «Giacomo o Jacopo», da decidere con le fonti enciclopediche.
- Corrispondenza per forma normalizzata (Tajedo → Taiedo) solo con luoghi friulani e veneti o capoluoghi: Ceresetto non diventa Cereseto, Carreri non diventa Careri.
- Corrispondenze GeoNames lontane dalla forma (Homo → Qom, Sion → Gerusalemme) restano «da verificare».
- Varianti grafiche dei cognomi (Bosio/Bossio): si segnala il gruppo, nessuna forma imposta; la forma di riferimento verrà dalle fonti.
- Decisioni del curatore e decisioni dal contesto della voce: `dati/liste/normalizzazioni_curatore.tsv` (forma, parte, forma normalizzata, origine `curatore`|`contesto`, nota), applicate per ultime. Parte «parola» = non è un nome (Bozze, Madonne, Januarii → gennaio).

## Fase 4 — esecuzione

`python3 script/entita.py` crea le tabelle `entita` (con `chiave` e `nota` per la revisione), `varianti`, `identificatori` (vuota fino alla fase 5), collega `menzioni.entita` e scrive `report/fase_4_entita.md`. Tutte le entità sono «proposto».
- Luoghi: un'entità per forma di riferimento; forma breve e nome ufficiale insieme (Cividale = Cividale del Friuli); le corrispondenze incerte restano a sé.
- Persone: chiave = nomi di battesimo in forma italiana + cognomi normalizzati, indipendente dall'ordine, senza titoli e senza «di/de/da» (gli articoli restano: Della Torre ≠ Torre). I cognomi si normalizzano solo graficamente (Savorgnan resta Savorgnan), salvo le correzioni del curatore.
- Le iniziali (G. B. Pirona) si uniscono a un nome completo solo se compatibile e unico; altrimenti restano a sé e sono segnalate.
- «Gasparo e Carlo Gozzi»: due entità, il cognome finale vale per entrambi.
- Nomi o cognomi isolati non fanno entità (possono indicare una famiglia o più persone): restano trovabili con la normalizzazione e il lessico.
- Segnalati per la revisione: famiglie con omonimi noti, entità presenti in molte voci, cognomi in grafie diverse.
- Correzioni puntuali del curatore sulle persone: `dati/liste/persone_curatore.tsv` (voce, testo, persone separate da «|»; «Rodolfo / Barnaba» = nomi / cognome; voce vuota = ovunque).
- Iniziali: si sciolgono prima con il nome intero nella stessa voce, poi con un'unica persona compatibile; altrimenti restano iniziali.
- Cognomi uguali a nomi di battesimo (Wolf, Venerio, Florio, Del Bianco): se nessuna parola è riconosciuta come cognome, lo è quella preceduta da un articolo o da una particella (Del Bianco, de Zorzi, De Luca); altrimenti vale la regola dei compilatori: **Cognome Nome all'inizio della voce, Nome Cognome all'interno** (Zeno Apostolo in apertura; Aldo Stella nel testo). Papi e sovrani (Benedetto XIII) fanno entità senza cognome. Esclusi i papi e sovrani (numerale), i santi (S.) e le coppie di soli nomi con Maria, Battista… Segnalati nel report (sezione 3 bis).
- Equivalenze: Gerolamo = Girolamo; Cortinovis = Cortenovis (stessa famiglia di barnabiti); «Barnabita» è un titolo.
- Ordine Cognome Nome anche nelle intestazioni e negli elenchi interni alla voce (menzione preceduta da a capo, «. », «, », «; » e seguita da punteggiatura: «Delfino Daniele.», «…, Zorzi Carlo Maria, …»). Prima della posizione vale il cognome già presente nella stessa voce (Paulino Fabio accanto ad Alessandro e Gio. Batta Paulino). Le coppie di soli nomi (Marco Antonio, Anna Maria) non si spezzano.
- Un punto seguito subito da minuscole, senza spazio, non chiude la parola: «C.sse», «S.ri» (vale in estrai.py e nel lessico).
- In `persone_curatore.tsv`, «santo:Nome» assegna la menzione a un santo (St. Claude, San Daniele); persone vuote = la menzione non è una persona.
- Ordine dei nomi, in quest'ordine di prova: articolo o particella; cognome già presente nella stessa voce (anche dall'intestazione: «Abel Federico» → «Federico Abel» più avanti); cognome di un'intestazione di altra voce; inizio della voce (Cognome Nome); ordine prevalente nella voce (contato sulle menzioni con cognome riconosciuto); intestazioni interne (dopo a capo, «; » o un punto di fine frase, non dopo «prof.», «cav.»); altrimenti Nome Cognome.
- Stesse parole con cognome dedotto in ordini diversi tra le voci (Gaetano Donizetti / Donizetti Gaetano; Liliano Giulio 56–58): una sola entità, prevale l'intestazione di voce.
- Cognome abbreviato all'iniziale («Z. Girolamo» nella voce «Zorzi, Mario»): si scioglie con l'unico cognome della voce che comincia con quella lettera.
- Cognome scritto subito prima della menzione: «Pecile, Gabriele Luigi» (in apertura di frase), «De Rubeis (Gio. Fran.)».
- «Giacomo de Sit.»: dopo una particella, il punto finale chiude la frase.
- Nomi doppi fusi uniti nella chiave: Giandomenico = Gian Domenico = Gio. Domenico.
- Una decisione «cognome» del curatore non tocca la riga di luogo della stessa forma (Trento).
- Il cognome abbreviato all'iniziale si scioglie solo con il cognome dell'intestazione della voce (non con un cognome qualsiasi della voce: «G. Gius. Bellina»).
- Un nome non prosegue oltre un a capo (estrai.py): «Har Dās.» / «Complessivamente 120 cc.».
- Patronimici esclusi dalla chiave: «Alessandro di Nicolò di Manzano», «q. Taddio».
- Parti di «X e Y Cognome» prima dell'ultima: nessuna deduzione, il cognome finale vale per tutte (Gian Mario e Antonio Tommasi).
- Cognomi in -i preferiti ai nomi (i nomi italiani non finiscono in -i, salvo Giovanni, Luigi…): «Rossi Lazzaro».
- Numerali romani col punto di fine frase («Onorio III.»), ultima parola col punto di fine frase («Treo.»), articolo tra parentesi dopo il cognome («Pace (della) Carlo Maria» = della Pace), «N. H.» (Nobil Homo), «Madonna …» = santo; un articolo seguito da un titolo è del titolo («del Sr. F. Barnaba»).
- Varianti dello stesso nome unite nella chiave: Raffaele = Raffaello, Daniele = Daniel = Daniello, Gaspare = Gaspero = Gasparo, Flaminio = Flaminius, Lodovico = Ludovico, Giuseppe = Gioseffo, Girolamo = Gerolamo, Jacopo = Jacobo.
- Abbreviazioni di nome non sciolte confrontate per radice («Gasp.» solo con Gaspare/Gaspero, «Fl.» con Flaminio); «D.» dopo un'iniziale o dopo Gian/Giovanni è Domenico, non «don».

## Fase 5 — luoghi

`python3 script/collega_luoghi.py`: per ogni entità di luogo, candidati GeoNames (IT.txt, cities5000) e Wikidata (etichetta italiana con P1566; elementi noti con almeno 10 voci di Wikipedia; codice ISTAT P635 per i comuni). Regole: Friuli e Veneto prima del resto; il comune prevale sulle frazioni omonime e Wikidata punta all'elemento del comune, non al «capoluogo dell'omonimo comune»; forme brevi dei comuni friulani (Colloredo = Colloredo di Monte Albano, Gradisca = Gradisca d'Isonzo); un elemento molto più noto prevale su una frazione omonima (Parigi, Romania, Carnia regione storica, Tagliamento fiume); parole che nel testo sono cognomi e corrispondono solo a frazioni fuori Friuli: affidabilità bassa. Decisioni puntuali in `dati/liste/luoghi_collegamenti.tsv` (vuoto = non è un luogo). Scrive `identificatori` (stato, affidabilità, nota), `alias_esterni` (alias it/la/fur, varianti solo dopo conferma) e `report/fase_5_luoghi.md`. La descrizione breve di Wikidata compare solo nel report.
- Lettura critica di tutti i luoghi (anche quelli ad affidabilità alta): le forme che non sono luoghi passano a parola, cognome, opera o santo, e i luoghi prendono la forma normalizzata italiana corretta (normalizzazioni_curatore.tsv, origine `contesto`); le scelte di località in luoghi_collegamenti.tsv. Se più elementi Wikidata hanno lo stesso codice ISTAT (comune e frazione capoluogo) vince il comune. Una decisione «cognome» vale anche sulle menzioni di luogo, salvo che la nota la limiti ai nomi di persona (Trento).

## Fase 5 — persone

`python3 script/collega_persone.py`: per ogni persona con un nome per intero, ricerca su Wikidata delle forme «Nome Cognome», «Nome di/da Cognome», «papa X» tra etichette e alias italiani (esseri umani). Punteggio: +2 nato o morto in Friuli/Veneto (comuni ISTAT e località friulane, non le frazioni omonime di città d'altre regioni); +1 date compatibili con gli anni scritti vicino alle menzioni (200 caratteri); −3 nato dal 1880 in poi dopo quegli anni (omonimi moderni); senza anni, i nati dopo il 1920 passano in coda e non sono mai «alta». Si salvano Wikidata e, da lì, VIAF, SBN, DBI. Decisioni dal contesto in `dati/liste/persone_collegamenti.tsv` (QID scelto, «accetta», «anni:A-B», «come:Intestazione», vuoto = nessun collegamento). Date e descrizioni compaiono solo nel report.

## Fase 5 — ricadute sul lessico

`python3 script/arricchisci.py` (dopo lessico.py, entita.py, collega_luoghi.py, collega_persone.py): per i collegamenti ad affidabilità alta, etichetta e alias di Wikidata (it, la, fur) diventano varianti `fonte_esterna` dell'entità (escluse sigle e forme sotto le tre lettere); i cognomi «da verificare» delle persone collegate diventano «normali» (origine Wikidata); le grafie diverse di Wikidata (Delfino/Dolfin) sono solo proposte per il curatore, perché il lessico vale per tutte le menzioni della parola. Ordine completo di esecuzione: estrai.py → lessico.py → entita.py → collega_luoghi.py → collega_persone.py → arricchisci.py.
