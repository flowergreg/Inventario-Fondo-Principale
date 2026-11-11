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

## Fase 5 — santi

Le menzioni «santo» sono un insieme misto, classificato in `dati/liste/santi_decisioni.tsv` (forma, classe, forma normalizzata, nota): luoghi (S. Daniele e S. Vito sono quasi sempre i paesi; S. Giovanni di Manzano = San Giovanni al Natisone), titoli e parole (S. Eccell., S. Sede, S. Uffizio), persone con l'iniziale S. o con nome Santo, forme latine e friulane (S. Petri Martyris → San Pietro Martire; S. Zorz → San Giorgio). Le altre abbreviazioni si sciolgono per regola (entita.py, `espandi_santo`): S. → San / Santa / Sant' / Santo, SS. → Santi / Santissimo / Santissima, S.ta → Santa; la forma sciolta è una variante, così «San Pietro» trova «S. Pietro». Nessun collegamento automatico a Wikidata: le etichette dei santi non portano «San» e la ricerca per etichetta dà omonimi o pagine di disambiguazione.

## Fase 7 — ricerca

- `script/ricerca.py`: indice (voci, segmenti, espansioni dal lessico in entrambi i sensi ma senza chiusura transitiva, entità con varianti e menzioni) e ricerca su tre livelli: entità, testo (tutte le parole espanse vicine, senza attraversare virgole, punti e virgola, due punti, a capo e parentesi), approssimata (una lettera di differenza, solo se il resto non trova nulla). Particelle e titoli della domanda non contano.
- `script/cerca.py "domanda"` da riga di comando; `--prove` esegue la batteria di prove.
- `script/pagina.py` scrive `web/index.html`: un solo file con indice e logica in JavaScript (stessi risultati della versione Python), funziona offline. Lo stile sta nelle variabili CSS in cima al file.
- Ordine completo: estrai.py → lessico.py → entita.py → collega_luoghi.py → collega_persone.py → arricchisci.py → pagina.py.

## Fase 6 — da preparare (promemoria)
- Tabella di coppie di persone con lo stesso nome (anche equivalente: Ludovico/Lodovico) e cognomi che
  differiscono di una lettera (≈90 coppie, più quelle con nomi equivalenti), con le voci, da segnare sì/no.
  Le coppie confermate vanno in `normalizzazioni_curatore.tsv` (unione delle entità ed espansione della ricerca).
  Casi già noti: Teck/Tech (voci 606, 3766, 1552 / 652, 914, 525); voce 667 «di Teck Pagine» scomposta male.
- Proposte grafiche di arricchisci.py in attesa (Bellone/Belloni, Delfino/Dolfin, Gallizioli/Gallicioli,
  Giustiniani/Giustinian, Pascaleo/Pasquale, Sommaripa/Summaripa, Sommariva/Summaripa).

## Fase 6 — blocco 1 (unioni), eseguito
- Principio del curatore: la forma di riferimento raccoglie **grafie**, non identifica persone; gli omonimi
  nei risultati sono naturali. La pagina parla di «forma di riferimento», non di «persona».
- `dati/liste/unioni_curatore.tsv` (tipo, forma_a, forma_b, decisione, nota, riferimento), dal tabellone
  `revisione/fase6_1_unioni_curatore.xlsx`:
  - `sì`: le entità si uniscono (in entita.py, `unisci_curatore`, transitivo); resta la forma con più
    menzioni, a parità la più breve; le forme unite stanno nella nota («forme unite dal curatore: A | B»);
  - `grafia`: stessa grafia, persone diverse (Ricci / Rizzi): entità distinte che ricevono l'una le forme
    dell'altra come varianti `manuale`, così la ricerca le trova entrambe e i collegamenti Wikidata restano separati;
  - `no`: restano separate; tipo `cognome` `sì`: espansione di ricerca per tutta la famiglia (Delfino ↔ Dolfin).
- collega_luoghi.py e collega_persone.py applicano le decisioni manuali anche alle forme unite e cercano
  su Wikidata anche con quelle; la nota delle unioni non abbassa l'affidabilità.
- Correzioni puntuali in `persone_curatore.tsv`: non persone (Forum Iulii, Ecclesia Aquileiensis, Thesaurus,
  Natale, incipit sanscriti), Geremia profeta, B. Vergine (Madonna), Vidussio Carnico, Morandi / Serravallo,
  Giovanni Girolamo Gradenigo.
- Famiglia di Girolamo (Gerolamo, Geronimo, Hieronimo, Hieronymus, Zerolamo…) tra le varianti equivalenti.

## Fase 6 — nomi di battesimo, eseguito
- `dati/liste/nomi_equivalenti.tsv` (forma, nome, nota, riferimento), dal tabellone
  `revisione/fase6_nomi_curatore.xlsx`: 93 equivalenze (Petrus = Pietro, Zuane = Giovanni, Nicola = Nicolò,
  Beltrame = Bertrando, Roland = Orlando…). entita.py le aggiunge alle varianti equivalenti (chiavi delle
  entità e ricerca, in ogni direzione); i nomi «Giacomo o Jacopo» valgono solo per la ricerca, senza chiusura.
  Escluse dal curatore: Alvise = Luigi, Zorzi = Giorgio, Erich = Erico.
- Intestazioni: se l'intestazione contiene una variante (Zuane, Piero) e tra le forme lette c'è la forma di
  riferimento con lo stesso numero di nomi e senza più iniziali, vince quest'ultima.
- Colonna `entita.alias`: le altre intestazioni dell'entità (forme lette e forme unite). Unioni del curatore e
  decisioni manuali di collegamento valgono per qualunque di esse, anche se l'intestazione cambia.

## Fase 6 — blocco 2 (correzioni), eseguito
- `revisione/fase6_2_correzioni.csv` (decisioni del curatore, con colonna «verifica e fonti»): 85 righe
  applicate in `persone_curatore.tsv` (scomposizioni sbagliate, non persone, nomi invertiti), una unione
  (Corgnali) in `unioni_curatore.tsv`, Brazzà distinto da Brazzacco (`normalizzazioni_curatore.tsv`) e
  classificazioni per voce (`classificazioni_manuali.tsv`: Brazzà 1235 famiglia, 3931 predicato; «Este» 2003-2005).
- Nuova lista `dati/liste/varianti_curatore.tsv` (tipo, intestazione, forma, nota): forme indicate dal curatore
  che non compaiono nel testo (Geronimiano, Germiniano, Graziani Publio Augusto per Agostino de Gerolami;
  Bonaparte; Midolini/Mijlinus…). entita.py le aggiunge come varianti `manuale` dell'entità.
- Verifiche in rete prima delle proposte: Dizionario Biografico dei Friulani (ricerca limitata al sito) e fonti
  generali; Wikidata solo via SPARQL, mai identificativi indovinati (Eleonora d'Este 1643-1722 = Q3721832).

## Fase 6 — blocchi 3 e 4, eseguiti
- Blocco 3 (`revisione/fase6_3_correzioni.csv`): ordine nome/cognome dedotto, epiteti (Carlo Magno), non persone;
  correzioni in `persone_curatore.tsv`.
- Blocco 4 (`revisione/fase6_4_wikidata.csv`): 133 collegamenti incerti; decisioni esplicite in
  `persone_collegamenti.tsv` (QID confermato o sostituito, vuoto = nessun collegamento) e `luoghi_collegamenti.tsv`.
  Principio: niente collegamento quando la forma raccoglie più persone omonime, perché sulla pagina il
  collegamento varrebbe per tutte le voci. Restano 19 collegamenti «media» (compatibili, non verificabili).
- Nella pagina l'etichetta di Wikidata non sostituisce la forma di riferimento: ne diventa una variante di
  ricerca solo se il collegamento è sicuro (Cassono → Gastone della Torre).

### Fase 6, scomposizioni e Dizionario Biografico dei Friulani
- Scomposizioni (`revisione/fase6_5_scomposizioni_curatore.csv`): 155 decisioni del curatore in `dati/liste/persone_curatore.tsv`, più «Msgr. Giusto» Fontanini (606) e «Savorgnani del Monte» (famiglia, 604). Gesù Cristo e San Francesco d'Assisi sono registrati come santi; varianti del curatore per Fior (Adalgiso, Giso, Gjiso), Gyrowetz/Jírovec, Murad IV, Ignaz Franz von Mosel.
- Indice del Dizionario riscaricato: l'espressione precedente fondeva le schede senza nome di battesimo con le successive (2318 → 2690 schede); «altri nomi» da 264 schede.
- Principi del curatore per i collegamenti (`dati/liste/dbf_collegamenti.tsv`, generato dalla tabella `revisione/fase6_6_dbf.csv`):
  - più schede compatibili: si collegano tutte, con forma e anni, e il lettore sceglie;
  - anni assenti o solo in parte compatibili: il link si mette comunque;
  - «no» (altra epoca): il link si toglie solo quando la voce esclude con certezza la persona (Amalteo Ascanio, Antonini Alfonso e altri 15); negli altri casi gli anni della voce sono di copie, edizioni, depositi o del contenuto e il link resta (Belgrado, Edo, Grimani Marino…);
  - una scheda trovata per cognome principale esclude quelle trovate solo attraverso gli altri nomi (Angeli Angelo, non Bandarini Angelo); negli altri nomi i nomi di battesimo non valgono come cognome.
  - escluso Foscarini Alvise (luogotenente nel 1637, non Ludovico Foscarini).
- Forme diverse collegate alla stessa scheda (Haedus Petrus / Edo Pietro) diventano varianti di ricerca l'una dell'altra; restano entità distinte, da validare.
- Pagine indicate dal curatore fuori dal Dizionario (fonte «curatore» in `fonti_curatore.tsv`): Antiche case di Udine per Adolfo della Porta.
- Docx corretto dal curatore (Clemente, Univ. Cattol.); decisioni riallineate. Le lettere di partizione alfabetica («A-K.», «L-Z.») non entrano nel nome. «Carlomagno» è la stessa entità di Carlo Magno.
- Link al Dizionario sempre con forma e date della scheda (dall'indice); la forma della scheda è variante di ricerca (Altan Enrico per «Altani Enrico»). Avvertenza sugli omonimi nel piè di pagina; «trascrizione a cura di» spostata in fondo.
- Luogo + «di/da» + nome completo («Padova di Giacomo Belgrado», «Aquileia di A. Altan») diventa due menzioni, luogo e persona (21 casi); esclusi i nomi di battesimo (Ciro di Pers) e «Monte», «Sacco», «Mels».
- Pagina: spunta «anche parte di parola» (ogni parola di almeno 3 lettere vale anche dentro parole più lunghe, varianti comprese); tolto il tempo di ricerca; «Trascrizione dall'inventario manoscritto a cura di Gregorio Grasselli» in fondo.
- La forma di riferimento mostrata è quella della scheda del Dizionario quando le schede collegate concordano (Fabrizio, Daniele); la forma interna resta quella dell'inventario, perché le decisioni del curatore vi fanno riferimento.
- Unione Arigonii I. B. / Arrigoni G. B. / Arigone Giovanni Battista (curatore); «Fabricio» (102) persona a sé.
- Validazione in blocco del curatore: 4622 entità in `dati/liste/validazioni.tsv` (tipo, forma di riferimento). Le forme nuove o cambiate da una rigenerazione tornano «proposto» e la pagina le segnala «da validare».
- `.nojekyll` alla radice: la pagina si può pubblicare con GitHub Pages (branch, cartella radice) all'indirizzo …/web/.
- GitHub Pages pubblica la cartella `docs/` (copia di `web/index.html` scritta da `pagina.py`, più `.nojekyll`): la radice intera (22 MB) andava in timeout.

### Fase 6, correzioni dopo le prove sulla pagina
- Santi: il nome del santo senza le specificazioni dell'edificio o del luogo (`nomi_santo` in entita.py): San Pietro di Osoppo → San Pietro, Madonna del Carmine → Madonna, «San Pietro - S. Canciano» → due santi; restano gli epiteti del santo (d'Assisi, da Padova, d'Aquino, Martire, Battista). Nella ricerca le forme con specificazione non valgono come varianti del santo (si trovano nel testo).
- Evidenziazione (`ev_inizio`, `ev_fine` in `menzioni`, calcolati in entita.py; testo e menzione invariati): si tolgono titoli, iniziali isolate estranee al nome, luoghi e il titolo dell'opera dopo il punto («Vittorio Emanuele II», «De Vit D.co.»); l'intestazione spezzata «Del Torso, Enrico» e la correzione tra quadre «Z. [Mario]» entrano nel tratto. Eccezioni in `dati/liste/evidenziazioni_curatore.tsv`.
- Menzioni con più persone: tabella `menzioni_entita`, così «Antonio e Girolamo Savorgnan» si trova da entrambi.
- Domanda fatta di nomi di luogo: la persona si trova solo se il cognome coincide con le parole cercate (Brazzà sì, «da Udine» no).
- Correzioni puntuali: Pier Antonio Zorzi, De Vit Domenico, Iacopino del Torso, Brazzà (Pietro, Giacomo, Antonio, Ascanio), Corgnali, i due Tristano Savorgnan (entrambi i link), famiglia Savorgnan (949, 1016, 1503), G. P. de Vecchi, Giovanni e Antonio Savorgnan, Maria-Letizia Bonaparte, Maria Teresa, de Zorzi Antoine = Antonio Zorzi. Tolta la variante «Beata Vergine di Screncis di Bertiolo» (con il santo senza specificazioni avrebbe esteso Bertiolo a tutte le voci di Santa Maria).
- Le classificazioni manuali possono creare una menzione che l'estrazione non ha colto, cercandone la forma nel testo della voce (Fiore di Premariacco, Giovanni da Udine, Odorico da Pordenone, «P. A. card. Zorzi»).
- Collegamenti del curatore: Fiore dei Liberi, Odorico Pilosio (566, «S.» = ser), Odorico da Pordenone, Giovanni da Udine detto il Ricamatore, Giulio Andrea Pirona; Tristano Savorgnan (1377-1440) solo nella voce 1549, altrove Tristano di Pagano Savorgnan del Monte; Giovanni Savorgnan (941).
- Pagina: le «forme cercate» sono cliccabili e avviano la ricerca di quella forma.
- Altre correzioni del curatore: Pier Paolo Locatelli (tutte le forme Locadello/Locadelli), Paolo Diacono (con Paulo; Paulo e Paulum = Paolo), discepoli di San Paolo, santi Giovanni e Paolo (618), Stella Francesco Maria ed Eusebio Simone, Candotti G. B., «Ave Maris Stella» = Madonna, Paolo Sarpi, Colloredo Fabio ed Ermes, famiglia Colloredo Mels, Ippolito Peres, Paolo Moretti, Paolo de Mutina.
- Pagina: casella «Segnala un errore» in fondo; invia il testo e la ricerca in corso a un modulo Google (configurazione in `dati/liste/segnalazioni.json`: indirizzo formResponse e codici dei campi), senza lasciare la pagina.
- Regola «quondam»: un nome senza cognome separato da «q.», «q.m», «qm.», «quondam», «fu» da una persona con cognome ne prende il cognome (figlio e padre; «Agostino e Nicolò q. …» due persone; non un luogo in testa alla menzione). Le persone nuove restano «proposto».
- Titolo tra cognome e nome nell'intestazione («Faidutti, mons. Luigi»): l'evidenziazione lo comprende.
- Le varianti del testo usano solo la parte evidenziata (Candotti non risponde più a «Maris Stella»); per i santi si scartano solo le varianti con specificazione (Osoppo), non le forme diverse (Ave Maris Stella = Madonna).
- Segnalazioni: modulo Google configurato; casella su una riga nel piè di pagina.
- Cognome precedente anche negli elenchi a trattini («- Cernazai, Giuseppe.») e con un titolo nella parentesi («Brazzoni (nob. Antonio»): 18 menzioni collegate in più. Correzioni del curatore: Joppi (Vincenzo, Antonio, Alessandro), P. Zorutti = Pietro, de Franceschi (senza «di Osoppo»), de Mutina Giovanni; Tolstoi Lev Nikolaevič.
- Segnalazioni: la dicitura chiarisce che le grafie diverse sono quelle del manoscritto.
- Una domanda fatta solo di parole di solito ignorate (titoli, particelle: «abate», «conte») si cerca così com'è nel testo.
- Correzioni del curatore: abate Domenico Ongaro e abate Giuseppe Bianchi (forme col solo cognome), Tolstoi (tutte le forme), Fabbricj Gion. Maria, Parravicini L. A., Foi Amadio (Rizzi nato Foi), Grimani Domenico, i Barnaba (783, 1488, 1490, 1916), A. Joppi = Antonio; 102: Barnaba di Prampero, traduttore dell'«Orlando Innamorato».
- Dicitura in testa: «Strumento non ufficiale, a cura di Gregorio Grasselli: non è un servizio della Biblioteca Civica «V. Joppi»».
- Cambio di nome del repository (Inventario_Joppi → Inventario-Fondo-Principale, per non far pensare al Fondo Joppi): GitHub Pages non reindirizza il vecchio indirizzo; `rimando/index.html` è la pagina da pubblicare in un repository con il vecchio nome perché il vecchio link continui a funzionare (conserva anche la ricerca dopo #).
- Le annotazioni tra quadre sono mostrate nel testo della voce al punto in cui stavano (colonna `posizione`), con la loro etichetta; senza posizione, in fondo.
- Testo in calce riscritto dal curatore, con i link a Wikidata e al Dizionario Biografico dei Friulani.
- Fabio della Forza = Fabio Sforza (curatore), con link al Dizionario.
- La ricerca nel testo mostra tutte le occorrenze nella voce (fino a 5 punti, poi «e altri N»), non solo la prima.
- Classificazioni manuali di luogo con forma di riferimento (Castello di Lientz → Lienz). Evidenziazione: dopo un'iniziale si toglie la parola estranea al nome della persona («Candotti G. B. Litanie»). Ricerca nel testo: il tratto evidenziato arriva fino alla prima occorrenza di ogni parola cercata.
- Correzioni del curatore: Camillo (III) di Colloredo, Domenico Del Bianco (Meni Muse), Bindo Chiurlo, il Burchiello (Domenico di Giovanni, Q1058842), Giustiniano Pozzi, ser Lorenzo Giustiniano, Antonio Gazzoletti («Falco Lovaria» è l'opera), Giambattista Pighi, Zocculuti, i Strassoldo (Rizzardo, Panfilo, Giovanni, Soldoniero, Gian Felice), Concina Daniele Vincenzo senza la scheda di Daniele (de) Concina, Megaluzza = Megaluzzi.
- Correzioni del curatore: Antonio Belloni (forme col solo cognome; link al Dizionario senza la barra finale, che dava 404, come altri sei), Francesco Porzio, Sebastiano Decio, Decio Basilio Cecina, Gregorio Amaseo, Francesco e Luigi Duodo, Giuseppe Greatti, Francesco Rota (menzioni create), Angelo Maria Cortenovis.
- Nomi indicati dal curatore: valgono tutte le parole del nome, anche se il lessico ne legge una come luogo («Maria Vittoria»), tranne titoli e abbreviazioni.
- Correzioni del curatore: Attems (Maria Vittoria, Francesco come «Attems (d')», Carlo Michele), Percoto (Giovanni Maria, Caterina), i Manzano nelle carte di famiglia (lo storico Francesco del Dizionario solo dove è lui; gli altri Francesco del Settecento in «Manzano (sec. XVIII), Francesco»), Cecchino Nievo, famiglie Pavona e Tobia, Pavona Antonio, Giovanni Battista, Gentile e il compositore Pietro Alessandro, il compositore Domenico Pecile (solo la scheda Domenico Quirico).
- Nella forma del curatore le parole prima della barra valgono sempre come nome («Vittoria / Colonna»: il lessico dà «Vittoria» per parola comune). Applicata così anche «L. / Serravallo» (blocco 1).
- Le forme del testo che nominano più persone non sono varianti di ciascuna (Carlomagno non risponde più ad «Antonini», Valentinis a «Delfino»).
- Correzioni del curatore: Vittoria Colonna (Q255368), Accoramboni (Q379412), Florio, Paris, Valvasone di Maniago; Florio Francesco e Daniele; Elena Manzano («Helenae Manzanae»); Nicoletti Marcantonio (Dizionario), Valentino, Michele, Ottaviano, Antonio; Bianchi Lorenzo; Wolf Alessandro; Antonini Lodovica, Rosa Deciani, Prospero (Dizionario: Francesco Prospero), Adriano, Francesco (Dizionario); Frangipane Cornelio (due schede) e Luigi; Tommaso Orca; Delfino.
- Variante per la consultazione privata (prima «terminale anni '80», ora tema scuro semplice, carattere senza grazie): `web/retro/index.html`, stessa pagina e stessi dati con un foglio di stile aggiunto (RETRO in pagina.py); non pubblicata.
- Versione terminale pubblicata nel repository `Inventario_Joppi` (ramo main, radice): https://flowergreg.github.io/Inventario_Joppi/ — senza righe di scansione e senza la fascia laterale di Teche; va ricopiata da `web/retro/index.html` a ogni rigenerazione.
- Correzioni del curatore: Cergnocco = Cergneu (Giovanni Battista, Dizionario), Belgrado Francesco, della Frattina Dorotea, Braida Tommaso, Marzona Leonardo in tutte le voci musicali (3725: famiglie Marzona e Pascoli), Valvasone di Maniago Jacopo (652-681, Dizionario) distinto dai Maniago, Ailino di Maniago, Giovanni di Ailino (Dizionario), Maniago P., Daniele e Antonio, Pietro di Montereale Mantica (339, il testo va corretto), Valerio Rossi senza «di Maniago».

### Fase 7, controllo dei cognomi più frequenti (a gruppi di dieci)
- Cognomi 41-52 (Prampero … Rossini): decisioni del curatore in `revisione/fase7_cognomi_41_52_curatore.csv`. Unito il P. Bernardo Maria de Rubeis (4 forme e una quindicina di «De Rubeis» da soli); Gradenigo Giovanni Agostino (monaco) e Gian Girolamo; Carli Gian Rinaldo con Carli Rubbi; Asquini Fabio Maria (cardinale) separato da Fabio; Flaminio de Rubeis / De Rossi in entrambe le forme (650); Maria Della Chiave e Maria de Rubeis (4518); Goricizza = Gorisizza; restano non sciolti «Ca.° Prampero», «G. della Porta», «T. de Rubeis».
- Regole generali: «Sindaco» è un titolo; la particella scritta prima del cognome entra nell'evidenziazione («de Grassi Luigi»).
- Cognomi 52-61 (Bini … Zorutti): decisioni in `revisione/fase7_cognomi_52_61_curatore.csv`. Le iniziali che il curatore dichiara indecidibili («indecidibile», «troppo generico», «resta G.» nella nota) non vengono sciolte in automatico nemmeno quando c'è un solo candidato.
- Cognomi 62-71 (Grimani … Mistruzzi): decisioni in `revisione/fase7_cognomi_62_71_curatore.csv` (40: «Colloredo-De Marchi» da correggere nel docx).
- Cognomi 72-100 (Puppi … Follini): decisioni in `revisione/fase7_cognomi_72_100_curatore.csv`. Fontanini nella 606 distinti per titolo (ab. → Domenico, can. → Girolamo, Msgr./senza titolo → Giusto); «Torre» separato tra torrente e famiglia della Torre; il patriarca Bertrando riunito in tutte le forme (Beltrame, Beltramo); chi cerca «Fabrizi» trova anche Fabrizio, Fabricio, Fabricius, Fabricii. Bloccati tre collegamenti automatici a Wikidata non pertinenti (Paolo Rota, Francesco Giusti, Michele della Torre nella 541).
- Controllo forme isolate e intestazioni malformate: corrette circa 70 intestazioni (titoli, luoghi o parole lette come persone: «Austriaca, Vienna», «Loquitur, Roma», «Venzone del Chir.°, Bellina Giacomo»…); «di Udine», «d'Aquileia», «di Gorizia», «di Concordia», «del Friuli», «Grado» isolati diventano luoghi; I. N. = Ippolito Nievo; nuove parole non-nome (Fin, Processo, Allegro…). Bloccati cinque collegamenti automatici a Wikidata non pertinenti. Le 50 forme isolate più frequenti in `revisione/fase7_forme_isolate.csv`, in attesa delle decisioni del curatore.
- Forme isolate (decisioni in `revisione/fase7_forme_isolate_curatore.csv`): circa 900 menzioni collegate (Fondo Tessitori → Luigi Pio Tessitori; prof. Carlo Minelli con la voce del Dizionario Biografico degli Italiani; provenienze Pirona → Giulio Andrea, l'abate → Jacopo; famiglie Elti, Pertoldeo, Savorgnan, Braida, di Manzano…; «Autrice» → l'autrice della voce). Restano irrisolvibili Modotti, Biasutti, «Mons. Nicoletti», il can. Vittorio; Delfino senza decisione.
- Controllo luoghi: le 244 menzioni di luogo senza collegamento erano quasi tutte parole (Scena, Sala, Rosario, Gazza Ladra…), persone (Canova, Muratori, Tommaseo, Palestrina, Romanello Manin…) o famiglie (Cucagna, Frattina, Cergneu…): ora riclassificate, nessuna menzione di luogo resta scollegata. «Fiume» distinto per voce (città di Fiume, Fiume Veneto, il fiume del Pordenonese). Identificativi Wikidata/GeoNames verificati via SPARQL per Torre (torrente), Fiume, castelli di Soffumbergo, Zucco e Prampero, Cimpello, Ceresetto, Iutizzo, Pieve di Rosa, Portis, Cusano. In `entita.py` la forma di riferimento indicata dal curatore per una voce prevale sul lessico («Riva» = Riva del Garda nella 2557).
- Pagina: tasto fisso «↑» in basso a sinistra, compare scorrendo i risultati e riporta alla casella di ricerca. Voce 836: «C. XIII» è il canto del Paradiso, non Clemente XIII; Ovidio collegato.
- Iniziali (decisioni in `revisione/fase7_iniziali_curatore.csv`): 19 sciolte o corrette (Amarli, Bellini, Trevisanato, Madrisio, Capodagli, Fabio di Colloredo 1833, Giacomo Zambelli…), 5 lasciate come iniziali. Tasto «↑»: sul computer seleziona anche il testo della casella.
- Forme latine: unite alla persona italiana (Bellonus/Bellonum → Antonio Belloni, Jacobi/Jacobus Stellini → Jacopo Stellini, Nicolai Canussii, Georgium Cichinum…); intestazioni costruite su frasi latine corrette («Opus Lucretii Trei» → Lucrezio Treo, «Comitis Jacobi Purliliensis» → Jacopo di Porcia); salmi e titoli tolti dalle persone; «Iulium Castrum» ed «Ecclesiae Forojuliensis» → Cividale; bloccati cinque collegamenti automatici a Wikidata. Casi dubbi in `revisione/fase7_forme_latine.csv`.
