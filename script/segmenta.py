#!/usr/bin/env python3
"""Fase 2 — Segmentazione delle voci.

Divide `voci.testo` secondo i soli riferimenti presenti nel testo e popola la
tabella `segmenti` di dati/inventario.sqlite. Nessuna numerazione inventata:
l'etichetta di ogni segmento è il riferimento originale.

Regola generale: un riferimento apre un segmento solo se sta all'inizio di
una proposizione (inizio voce, a capo, dopo «. », «; », «, », oppure dopo
«contenente», «contiene», «di:» …), eventualmente preceduto da parole di
collegamento («a», «al», «segue a», «cui segue a», «preceduta a»…). Così
«di carte 321» o «mancano le carte 1 a 4» non aprono segmenti.

Famiglie di riferimenti:
- fogli/carte/pagine: fol., folio, f., ff., c., cc., carte, pag., p., pp.…;
  dopo il primo di questi, valgono anche i numeri nudi («14-28») purché
  crescenti rispetto al precedente;
- fascicoli: Fasc. 2°, Fasc. V;
- N. 5, N.° 5;
- elenchi numerati: 1°, 2°… / 1) 2)… / 1. 2.… — devono cominciare da 0 o 1
  e procedere di uno in uno (altrimenti «16°» di un formato aprirebbe un
  segmento);
- lettere: a) b)…, A) A.2) E bis) — devono cominciare da a/A o seguire la
  lettera precedente con salto al più di due;
- elenchi alfabetici dichiarati (ELENCHI_ALFABETICI): il nome fa da etichetta.

Uso: python3 script/segmenta.py [percorso_sqlite]
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
DB_PREDEFINITO = RADICE / "dati" / "inventario.sqlite"
DIAGNOSTICA = RADICE / "dati" / "diagnostica_segmenta.json"

# Voci trattate come elenchi alfabetici: numero → modalità.
# «virgole»: nomi separati da virgola dopo i due punti (2134);
# «paragrafi»: un nome all'inizio di ogni paragrafo (525).
ELENCHI_ALFABETICI = {
    "2134": "virgole",
    "525": "paragrafi",
}

# ---------------------------------------------------------------------------
# Espressioni regolari
# ---------------------------------------------------------------------------

# Punti in cui può cominciare una proposizione.
RX_DELIMITATORE = re.compile(
    r"(?:\n|[.;,:?!)»\]…]\s+|\b(?:[Cc]ontenente|[Cc]ontenendo|[Cc]ontiene|[Cc]ontengono|[Cc]omprende|[Cc]omprendente|[Cc]omprendono)\s+)"
)
CONNETTIVI = {
    "a", "al", "ai", "alla", "alle", "da", "dal", "dalla", "dai", "nel", "nella",
    "nei", "in", "segue", "seguono", "cui", "preceduta", "preceduto", "e", "ed",
    "poi", "indi", "quindi", "così", "il", "lo", "la", "i", "gli", "le", "dei", "delle", "quali", "cui",
}
RX_CONNETTIVI = re.compile(r"((?:[^\W\d_]+\s+){0,3})")

NUM = r"(?:\d+|(?-i:[IVXLC]+)\b)(?:\s?[rv]\b°?|\s?t°)?"
INTERVALLO = NUM + r"(?:\s?(?:-|–)\s?" + NUM + r"|\sa\s(?:carte\s|pag\.\s|fol\.\s)?" + NUM + r")?"
RX_FOGLI = re.compile(
    r"(?:fol(?:l|io|ii)?\.?|fogli?o?|ff?\.|cc?\.|cart(?:e|a|\.)|pag(?:g|ina|ine)?\.?|pp?\.)"
    r"\s?" + INTERVALLO + r"(?![\d°])",
    re.I,
)
RX_FASC = re.compile(r"[Ff]asc(?:icolo|\.°?)\s?(?:\d+°?|[IVXLC]+\b)")
# libri: «libro 1», «lib. 3», «l.15»
RX_LIBRO = re.compile(r"(?:[Ll]ibro|[Ll]ib\.|l\.)\s?(\d+|[IVXLC]+\b)")
# parole che dopo un numero indicano una consistenza, non un rinvio
RX_CONTEGGIO = re.compile(
    r"(?:pezz|fogl|cart|cc\b|lett|fasc|vol|bust|pacc|docum|esempl|copi|pagin|pp?\b)", re.I)
RX_CONTEGGIO_NUDO = re.compile(r"(?:carte|cc\.|c\.|fogli|ff\.|pagine|pp\.|p\.)", re.I)
RX_N = re.compile(r"N(?:\.°|°|\.|r\.)\s?\d+")
RX_NUDO = re.compile(r"(\d+)(?:\s?(?:-|–)\s?\d+)?(?:\.ª\))?(?=\s+[^\d\s°)])")
# due numeri per un solo elemento: «8 e 9.)», «154 e 155)»
RX_NUMERATO_COPPIA = re.compile(r"(\d+)\s(?:e|ed)\s(\d+)(°|\.\)|\))")
# volumi: «Il vol. I contiene», «Volume II»
RX_VOLUME = re.compile(r"[Vv]ol(?:ume|\.)\s?(\d+°?|[IVXLC]+\b)")
# opere: «Op. I», «Op. IV.»
RX_OPERA = re.compile(r"Op\.\s?([IVXLC]+)\b")
# elenchi numerati, anche a catena: «1°, 2°, 3°, 4° e 5°»
RX_NUMERATO = re.compile(
    r"(\d+)(?:(?:\s?(?:-|a)\s?\d+)+(?=\)))?(?:\s?bis)?(°\)?|\.\)|\)|\.(?=\s))"
    r"((?:(?:(?<=\))\s|\s?(?:,|e|ed|-|a)\s?)(?:il\s|l')?\d+(?:°|\)))*(?:\s?a\s\d+\s?incl?\.?\)?)?)"
)
RX_ABBREVIAZIONE = re.compile(
    r"\b(?:fol|foll|f|ff|c|cc|car|cart|pag|pagg|p|pp|n|nn|fasc|vol|voll|lib|t|tom|cap|sec|ep|fab|art|num|ms|mss|cod|an|ann)$", re.I)
# parole che dopo «carte N» indicano la consistenza del pezzo
RX_CONSISTENZA = re.compile(
    r",?\s*(?:legat|rileg|riunit|sciolt|unit|cucit|numerat|non numer|con numer|bianch|scritt|complessiv|in copert|in-\d|nn\b|/\d|di complessiv|di carte|di cc|(?:di\s)?pag(?:\.|ine\b))", re.I)
# un ordinale seguito da queste parole è un aggettivo («1° foglio», «18° secolo»)
RX_ORDINALE_AGGETTIVO = re.compile(
    r"(?>fol(?:io|\.)|foglio|carta|c\.|pagina|pag\.|p\.|secolo|sec\.|verso|recto|r\.|v\.)(?!\s?\d)")
# un ordinale seguito da queste parole descrive, non elenca («il 2° e l'ultimo bianchi»)
RX_ORDINALE_DESCRITTIVO = re.compile(r"(?:e l'ultim|ed ultim|e ultim|bian)", re.I)
# formati del manoscritto: «in-8°», «in 4°», «formato 16°»
RX_FORMATO_PRIMA = re.compile(r"(?:\bin-?|formato|form\.)\s*$", re.I)
RX_ROMANO = re.compile(r"([IVXL]+)\)")
ROMANI = {"I": 1, "V": 5, "X": 10, "L": 50}


def valore_romano(r):
    tot, prec = 0, 0
    for ch in reversed(r):
        v = ROMANI[ch]
        tot = tot - v if v < prec else tot + v
        prec = max(prec, v)
    return tot
RX_MESE = re.compile(
    r"(?:gen(?:naio|n?\.)|feb(?:braio|b?r?\.)|mar(?:zo|\.)|apr(?:ile|\.)|mag(?:gio|g?\.)"
    r"|giu(?:gno|\.)|lug(?:lio|\.)|ago(?:sto|\.)|set(?:tembre|t?\.)|ott(?:obre|\.)"
    r"|nov(?:embre|\.)|dic(?:embre|\.))", re.I)
RX_LETTERA = re.compile(r"\(?([A-Za-z])(\.\d+)?(\s?bis)?\)")


def ultimo_numero(etichetta):
    """Ultimo numero di un'etichetta, con gli intervalli abbreviati sciolti:
    «142-43)» → 143, «115-16-17)» → 117, «188-89)» → 189."""
    numeri = re.findall(r"\d+", etichetta)
    primo, ultimo = int(numeri[0]), int(numeri[-1])
    if ultimo < primo:
        base = 10 ** len(numeri[-1])
        ultimo = primo - primo % base + ultimo
    return ultimo


def riferimento_a(testo, pos):
    """Se in `pos` comincia un riferimento, restituisce (famiglia, testo, valore)."""
    m = RX_FASC.match(testo, pos)
    if m:
        return "fascicolo", m.group(0), None
    m = RX_LIBRO.match(testo, pos)
    if m:
        n = m.group(1)
        return "libro", m.group(0), int(n) if n.isdigit() else valore_romano(n)
    m = RX_N.match(testo, pos)
    if m:
        return "numero", m.group(0), None
    m = RX_FOGLI.match(testo, pos)
    if m:
        v = re.search(r"\d+", m.group(0))
        return "fogli", m.group(0), int(v.group(0)) if v else 0
    m = RX_OPERA.match(testo, pos)
    if m:
        return "opera", m.group(0), valore_romano(m.group(1))
    m = RX_VOLUME.match(testo, pos)
    if m:
        n = m.group(1).rstrip("°")
        return "volume", m.group(0), int(n) if n.isdigit() else valore_romano(n)
    m = RX_NUMERATO_COPPIA.match(testo, pos)
    if m:
        return "numerato", m.group(0), (int(m.group(1)), int(m.group(2)))
    m = RX_NUMERATO.match(testo, pos)
    if m:
        return "numerato", m.group(0), (int(m.group(1)), ultimo_numero(m.group(0)))
    m = RX_ROMANO.match(testo, pos)
    if m and (pos + len(m.group(0)) >= len(testo) or testo[pos + len(m.group(0))] in " \n"):
        if len(m.group(1)) > 1:
            return "romano", m.group(0), valore_romano(m.group(1))
        # «I)», «V)», «X)» possono essere lettere o numeri romani: si decide dopo
        return "romano_o_lettera", m.group(0), valore_romano(m.group(1))
    m = RX_LETTERA.match(testo, pos)
    if m and (pos + len(m.group(0)) >= len(testo) or testo[pos + len(m.group(0))] in " \n."):
        return "lettera", m.group(0), m.group(1)
    m = RX_NUDO.match(testo, pos)
    if m:
        return "nudo", m.group(0), int(m.group(1))
    return None


def candidati(testo):
    """Posizioni di inizio proposizione, con l'eventuale riferimento che le apre."""
    posizioni, deboli = {0}, set()
    for m in RX_DELIMITATORE.finditer(testo):
        # il punto di un'abbreviazione («fol. 33», «sec. 7°», «Un f. XXVII)»)
        # di norma non chiude una proposizione: la posizione vale solo come
        # «debole», cioè per proseguire esattamente un elenco già avviato
        if testo[m.start()] == "." and RX_ABBREVIAZIONE.search(testo, 0, m.start()):
            deboli.add(m.end())
            continue
        posizioni.add(m.end())
    # ogni a capo apre una proposizione, anche dopo un'abbreviazione («nn.¶b)»);
    # così pure la virgoletta d'apertura («1.) Serie…»)
    for m in re.finditer(r"\n|«", testo):
        posizioni.add(m.end())
    deboli -= posizioni
    for inizio in sorted(posizioni | deboli):
        if inizio >= len(testo):
            continue
        # salta fino a tre parole di collegamento
        m = RX_CONNETTIVI.match(testo, inizio)
        parole = m.group(1).split()
        for k in range(len(parole), -1, -1):
            if all(p.lower() in CONNETTIVI for p in parole[:k]):
                break
        pos = inizio
        for p in parole[:k]:
            pos = testo.index(p, pos) + len(p)
            while pos < len(testo) and testo[pos] == " ":
                pos += 1
        # elisione: «l'8°», «L'11°»
        if testo.startswith(("l'", "L'", "l’", "L’"), pos) and pos + 2 < len(testo) and testo[pos + 2].isdigit():
            pos += 2
        r = riferimento_a(testo, pos)
        if r:
            yield inizio, pos, r, inizio in deboli


# Livelli di suddivisione, dal più alto: si usa il più alto che abbia almeno
# due elementi. Pagine e carte (fogli, nudo) indicano spesso solo la posizione
# nel manoscritto e valgono solo se non c'è una suddivisione più alta.
LIVELLI = ["opera", "volume", "fascicolo", "libro", "romano", "numerato", "lettera", "numero", "fogli"]
SALTO_MASSIMO = 15   # salto massimo ammesso in un elenco numerato (numeri omessi)


def segmenta_riferimenti(testo, scarti):
    """Restituisce la lista di (inizio, etichetta, famiglia) dei confini."""
    accettati = {f: [] for f in LIVELLI}
    serie_fogli = None        # ultimo valore di fogli/pagine accettato
    ultimo = {"numerato": None, "romano": None, "libro": None, "opera": None, "volume": None}
    per_stile = {}
    ultima_lettera = None
    fine_ultimo = -1          # fine dell'ultimo riferimento accettato
    for inizio, pos, (famiglia, etichetta, valore), debole in candidati(testo):
        # niente candidati dentro un riferimento già accettato («Al fol.| 23»)
        if inizio < fine_ultimo:
            continue
        a_capo_vero = inizio == 0 or testo[inizio - 1] == "\n"
        dopo_due_punti = testo[:inizio].rstrip().endswith(":")
        a_capo = a_capo_vero or dopo_due_punti
        con_connettivo = pos > inizio
        dopo = testo[pos + len(etichetta):].lstrip(" ")
        prima = testo[max(0, pos - 12):pos]
        if famiglia == "romano_o_lettera":
            if ultimo["romano"] is not None and 0 < valore - ultimo["romano"] <= 3:
                famiglia = "romano"
            elif valore == 1 and ultima_lettera != "h":
                famiglia = "romano"
            else:
                famiglia, valore = "lettera", etichetta[0]
        if famiglia in ("fogli", "nudo", "numero"):
            # il riferimento deve introdurre un contenuto, non chiudere una
            # frase («16°, pp. 8.» è una consistenza, non un rinvio)
            # (dentro una serie di carte già avviata la virgola è ammessa:
            # «; carte 13, sonetto del co. Giorgio Pulcenigo»)
            if not dopo or dopo[0] in ".;)\n" or (
                    dopo[0] == "," and serie_fogli is None and not con_connettivo and not a_capo):
                continue
        if famiglia == "numero" and RX_CONTEGGIO.match(dopo):
            continue
        if famiglia == "nudo" and RX_CONTEGGIO_NUDO.match(dopo):
            continue                          # «seguono 12 carte bianche»
        if famiglia in ("fogli", "nudo", "fascicolo") and RX_CONSISTENZA.match(dopo):
            continue                          # «Fasc. 4 di complessive carte 78»
        if debole and famiglia not in ("numerato", "romano", "libro", "lettera"):
            continue                          # «carte 21 legate in copertina»
        if famiglia == "fogli":
            # «cc. 31», «carte 35», «ff. 18», «pp. 8» senza parola di
            # collegamento sono di norma consistenze: valgono solo a capo
            # (dentro una serie già avviata valgono anche senza collegamento)
            conteggio = re.match(r"(?:cc?\.|cart[ea.]|ff?\.|pp?\.)", etichetta, re.I)
            if conteggio and not con_connettivo and not a_capo and serie_fogli is None:
                continue
            # dopo i due punti una serie di carte comincia da 1 («e cioè: cart. 1 …»);
            # altrimenti è una consistenza («3 copie: cc. 45 …»)
            if (conteggio and not con_connettivo and not a_capo_vero and dopo_due_punti
                    and serie_fogli is None and valore > 1):
                continue
            serie_fogli = valore
        elif famiglia == "nudo" and ultimo["numerato"] is not None and re.match(
                r"\d+\s?(?:a|-)\s?\d+\s+incl?\b", testo[pos:]) and (
                ultimo["numerato"] < valore <= ultimo["numerato"] + SALTO_MASSIMO):
            # «32 a 40 incl.»: voce di un elenco numerato che copre più numeri
            famiglia = "numerato"
            etichetta = re.match(r"\d+\s?(?:a|-)\s?\d+\s+incl?\.?", testo[pos:]).group(0)
            ultimo["numerato"] = int(re.findall(r"\d+", etichetta)[-1])
        elif famiglia == "nudo":
            if serie_fogli is None or valore >= 1000 or not (serie_fogli <= valore <= serie_fogli + 300):
                continue
            if RX_MESE.match(dopo):
                continue
            serie_fogli = valore
            famiglia = "fogli"
        elif famiglia in ("numerato", "romano", "libro", "opera", "volume"):
            primo, fine_catena = valore if famiglia == "numerato" else (valore, valore)
            if primo >= 1000:
                continue                      # è un anno, non una numerazione
            # prosecuzione esatta dell'elenco in corso (anche con altra forma:
            # «4° …; 5. …; 6° …»)
            seguito = ultimo[famiglia] is not None and primo == ultimo[famiglia] + 1
            if debole and (not seguito or not re.match(r"[^\W\d_]|[«\"(]", dopo)):
                continue
            if famiglia == "volume" and RX_CONSISTENZA.match(dopo):
                continue
            if etichetta.endswith("°") or etichetta.endswith("°."):
                # formato («in-8°», «16°, pp. 8»), aggettivo («1° foglio»), data
                # («1° aprile»), descrizione («il 2° e l'ultimo bianchi»), oppure
                # parte di un'enumerazione di ordinali («dei secoli 11°, 12° e 13°»)
                if (RX_FORMATO_PRIMA.search(prima)
                        or (dopo and dopo[0] in ";)") or (dopo[:1] == "," and not seguito)
                        or RX_ORDINALE_AGGETTIVO.match(dopo) or RX_MESE.match(dopo)
                        or RX_ORDINALE_DESCRITTIVO.match(dopo)
                        or re.search(r"\d°\s*,\s*$", testo[:inizio])):
                    continue
            # la forma «1.» apre un elenco solo a capo o dopo i due punti
            if (famiglia == "numerato" and etichetta.endswith(".") and ultimo["numerato"] is None
                    and not a_capo and not testo[:inizio].rstrip().endswith(":")):
                continue
            # ogni forma («1°», «1)», «1°)», «1.») ha la sua sequenza: un
            # sottoelenco «1°) 2°)» dentro «23)» non interrompe l'elenco principale
            stile = famiglia if famiglia in ("romano", "libro", "opera", "volume") else (
                "°)" if etichetta.endswith("°)") else etichetta[-1])
            prec = per_stile.get(stile)
            if prec is None and famiglia == "romano" and ultimo["numerato"] == primo - 1:
                ok = True                     # «1) … II) … III)»: serie mista
            elif seguito:
                ok = True
            elif prec is None:
                ok = primo in (0, 1, 2)       # a volte il primo elemento non è numerato
            else:
                # un elenco può ricominciare da 1 (sottoelenchi: «il I: 1°… il II: 1°…»)
                # (tollerato un piccolo passo indietro: «4° e 6° …; 5° …»)
                ok = primo in (0, 1) or prec - 2 <= primo <= prec + SALTO_MASSIMO
            if not ok:
                if prec is not None:          # i numeri isolati (formati, anni) non si annotano
                    scarti.append((etichetta, "numerazione fuori sequenza"))
                continue
            ultimo[famiglia] = fine_catena
            per_stile[stile] = fine_catena
        elif famiglia == "lettera":
            l = valore.lower()
            if debole and not (ultima_lettera and ord(l) - ord(ultima_lettera) == 1):
                continue
            if l == "a":
                pass                          # un nuovo elenco può ricominciare
            elif ultima_lettera is None:
                scarti.append((etichetta, "lettera iniziale diversa da a"))
                continue
            elif not (0 <= ord(l) - ord(ultima_lettera) <= 2):
                scarti.append((etichetta, "lettera fuori sequenza"))
                continue
            ultima_lettera = l
        accettati[famiglia].append((inizio, etichetta.strip(), famiglia))
        fine_ultimo = pos + len(etichetta)

    # si sceglie il livello più alto con almeno due elementi (le catene
    # «1°, 2° e 3°» contano per più elementi)
    def peso(lista):
        return sum(max(1, len(re.findall(r"\d+", e))) if f == "numerato" else 1
                   for _, e, f in lista)
    for livello in LIVELLI:
        if peso(accettati[livello]) >= 2:
            scelti = accettati[livello]
            # «il 2° in cartone» prima di «Il 1° …, il 2° …»: un elenco che
            # comincia da 2 vale solo se prosegue con 3
            if livello == "numerato" and len(scelti) >= 2:
                v = [int(re.findall(r"\d+", e)[0]) for _, e, _ in scelti[:2]]
                if v[0] == 2 and v[1] != 3:
                    scarti.append((scelti[0][1], "numerazione fuori sequenza"))
                    scelti = scelti[1:]
            if livello == "romano" and accettati["numerato"][:1] and (
                    accettati["numerato"][0][0] < scelti[0][0]):
                scelti = accettati["numerato"][:1] + scelti   # «1)» che apre una serie romana
            return scelti, []
    isolati = [c for l in LIVELLI for c in accettati[l]]
    return [], isolati


# ---------------------------------------------------------------------------
# Elenchi alfabetici
# ---------------------------------------------------------------------------

def elenco_virgole(testo):
    """2134: preambolo fino ai primi due punti, poi un nome per segmento;
    l'eventuale frase finale dopo l'ultimo nome è la chiusura."""
    dp = testo.index(":") + 1
    while dp < len(testo) and testo[dp] == " ":
        dp += 1
    voci, inizio, profondita = [], dp, 0
    for i in range(dp, len(testo)):
        ch = testo[i]
        if ch == "(":
            profondita += 1
        elif ch == ")":
            profondita -= 1
        elif ch == "," and profondita == 0:
            voci.append((inizio, i))
            inizio = i + 1
            while inizio < len(testo) and testo[inizio] == " ":
                inizio += 1
    ultimo = testo[inizio:]
    chiusura = None
    m = re.search(r"\.\s+(?=[A-Z])", ultimo)
    if m:
        voci.append((inizio, inizio + m.start()))
        chiusura = inizio + m.end()
    else:
        voci.append((inizio, len(testo)))
    # etichetta = il nome come scritto, senza la punteggiatura che lo separa
    confini = [(a, testo[a:b].strip().rstrip(",").strip(), "elenco") for a, b in voci]
    return confini, chiusura


def elenco_paragrafi(testo):
    """525: ogni paragrafo che comincia con un nome breve (al più quattro
    parole, iniziale maiuscola, seguito da «.» o «,») apre un segmento;
    gli altri paragrafi proseguono il precedente."""
    confini, pos = [], 0
    for k, riga in enumerate(testo.split("\n")):
        if k > 0:
            m = re.match(r"((?:[A-Z]\.\s)?([^\W\d][^.,\n(]*?)(?:\s?\([^)]*\))?)(?:\.|,)\s", riga)
            if m and len(m.group(2).split()) <= 4 and m.group(2)[0].isupper():
                confini.append((pos, m.group(1), "elenco"))
        pos += len(riga) + 1
    return confini


# ---------------------------------------------------------------------------

# Riferimenti posti dopo il contenuto o tra parentesi:
# «Domenico Ongaro, 9 lett. (…), carte 3-23; Giuseppe Bini…, carte 26-44;»
# «A. Altan (carte 1-18) Estratti…», «(Fasc. I da carte 1 a 39)».
_REF = r"(?:carte|cart\.|c\.|fol\.|pag\.)\s?(?:\d+|[IVXLC]+\b)(?:\s?(?:-|a)\s?(?:\d+|[IVXLC]+\b))?(?:\s?[rv]\b)?"
RX_REF_INTERNO = re.compile(
    r"\(\s*(?P<par>(?:[Ff]asc\.\s?(?:[IVX]+|\d+)\s)?(?:da\s)?" + _REF + r")\s*\)"
    r"|,\s(?P<coda>" + _REF + r")(?=\s*(?:[;.\n]|$))")
RX_FINE_PROPOSIZIONE = re.compile(r"(?:[;:]\s+|\.\s+(?=[A-Z«\"])|\n)")


def riferimenti_in_coda(testo, minimo=2):
    """Confini per le voci in cui il riferimento segue il contenuto o sta
    tra parentesi dopo un nome. Servono almeno due riferimenti."""
    fini = [m.end() for m in RX_FINE_PROPOSIZIONE.finditer(testo)
            if not (testo[m.start()] == "." and (
                RX_ABBREVIAZIONE.search(testo, 0, m.start())
                or re.search(r"(?:^|\s)(?:[A-Z]|Vol|Voll|Lib|Fasc)$", testo[:m.start()])))]
    confini, fine_prec = [], None
    for m in RX_REF_INTERNO.finditer(testo):
        etichetta = m.group("par") or m.group("coda")
        inizio_prop = max([f for f in fini if f <= m.start()], default=0)
        parole = len(testo[inizio_prop:m.start()].split())
        if m.group("par") and parole <= 4:
            confine = inizio_prop                 # rinvio dopo un nome, in testa
        elif fine_prec is not None and fine_prec > inizio_prop - 1:
            confine = fine_prec                   # segue il rinvio precedente
        else:
            confine = inizio_prop
        if confini and confine <= confini[-1][0]:
            continue
        confini.append((confine, etichetta, "coda"))
        # il segmento successivo comincia dopo la punteggiatura che chiude il rinvio
        f = m.end()
        while f < len(testo) and testo[f] in " ;.,)\n":
            f += 1
        fine_prec = f
    return confini if len(confini) >= minimo else []


RX_RINVIO_FINALE = re.compile(
    r"(?:da\s)?((?:carte|cart\.|c\.|fol\.|pag\.)\s?\d+(?:\s?(?:-|a)\s?\d+)?)[.;]?\s*$")


# Segmentazioni stabilite a mano per le voci a suddivisione discorsiva:
# dati/segmentazioni_manuali.json → {numero: [{"inizio": testo, "etichetta": …, "tipo": …}]}
MANUALI = RADICE / "dati" / "segmentazioni_manuali.json"
# Voci le cui segnalazioni sono state verificate (numerazione davvero lacunosa
# nell'originale, ecc.): dati/segmentazioni_verificate.json → {numero: nota}
_VER = RADICE / "dati" / "segmentazioni_verificate.json"
VERIFICATE = {k: v for k, v in (json.loads(_VER.read_text(encoding="utf-8")) if _VER.exists() else {}).items()
              if not k.startswith("_")}


def segmentazione_manuale(numero, testo, regole):
    confini, da = [], 0
    chiusura = None
    for r in regole:
        pos = testo.find(r["inizio"], da)
        if pos < 0:
            raise ValueError(f"voce {numero}: «{r['inizio']}» non trovato")
        if r.get("tipo") == "chiusura":
            chiusura = pos
            break
        if r["etichetta"] not in testo[pos:]:
            raise ValueError(f"voce {numero}: etichetta «{r['etichetta']}» assente dal testo")
        confini.append((pos, r["etichetta"], "manuale"))
        da = pos + 1
    return confini, chiusura


def costruisci_segmenti(numero, testo, scarti, manuali=None):
    chiusura = None
    modo = ELENCHI_ALFABETICI.get(numero)
    if modo == "virgole":
        confini, chiusura = elenco_virgole(testo)
    elif modo == "paragrafi":
        confini = elenco_paragrafi(testo)
    elif manuali and numero in manuali:
        confini, chiusura = segmentazione_manuale(numero, testo, manuali[numero])
    else:
        confini, isolati = segmenta_riferimenti(testo, scarti)
        if not confini:
            # rinvii posti dopo il contenuto o tra parentesi; un eventuale
            # rinvio isolato in testa a una proposizione fa parte della serie
            confini = sorted(riferimenti_in_coda(testo, minimo=1)
                             + [c for c in isolati if c[2] in ("fogli", "fascicolo")])
            pulito = []
            for c in confini:
                if not pulito or c[0] > pulito[-1][0]:
                    pulito.append(c)
            confini = pulito if len(pulito) >= 2 else []
            if not confini:
                for c in isolati:
                    scarti.append((c[1], "riferimento isolato"))
    if not confini:
        return [("voce_intera", "", 0, len(testo), None)]
    # il primo pezzo può avere il rinvio in coda («…; da carte 1 a 35. Da carte 36 …»):
    # il preambolo che termina con un rinvio diventa un segmento con quell'etichetta
    if modo is None and confini[0][2] in ("fogli", "coda"):
        pre = testo[:confini[0][0]]
        m = RX_RINVIO_FINALE.search(pre)
        if m:
            dp = pre.rfind(":", 0, m.start())
            inizio = dp + 1 if dp >= 0 else 0
            while inizio < len(pre) and pre[inizio] in " \n":
                inizio += 1
            confini = [(inizio, m.group(1), "coda")] + confini
    segmenti = []
    if testo[: confini[0][0]].strip():
        segmenti.append(("preambolo", "", 0, confini[0][0], None))
    limiti = [c[0] for c in confini[1:]] + [chiusura if chiusura is not None else len(testo)]
    for (inizio, etichetta, famiglia), fine in zip(confini, limiti):
        segmenti.append(("riferimento", etichetta, inizio, fine, famiglia))
    if chiusura is not None:
        segmenti.append(("chiusura", "", chiusura, len(testo), None))
    # i segmenti non devono includere spazi/separatori finali
    puliti = []
    for tipo, etichetta, a, b, famiglia in segmenti:
        while b > a and testo[b - 1] in " \n":
            b -= 1
        puliti.append((tipo, etichetta, a, b, famiglia))
    return puliti


def valore_etichetta(etichetta, famiglia):
    """Valore numerico di un'etichetta di elenco (per controllarne la continuità)."""
    if famiglia == "lettera":
        m = re.search(r"[A-Za-z]", etichetta)
        return ord(m.group(0).lower()) - ord("a") + 1 if m else None
    m = re.search(r"\d+", etichetta)
    if m:
        return int(m.group(0))
    m = re.search(r"\b[IVXL]+\b", etichetta)
    return valore_romano(m.group(0)) if m else None


def dubbi_per_voce(numero, testo, segmenti):
    """Segnalazioni da controllare: soprattutto la continuità delle numerazioni,
    che rivela riferimenti persi (es. «Fasc.° 2°») o presi per errore."""
    dubbi = []
    if numero in ELENCHI_ALFABETICI or numero in VERIFICATE:
        return dubbi                          # elenco di nomi o voce già verificata
    rif = [s for s in segmenti if s[0] == "riferimento"]
    for tipo, etichetta, a, b, famiglia in rif:
        if len(testo[a:b].strip()) - len(etichetta) < 8:
            dubbi.append(f"segmento quasi vuoto «{etichetta}»")
    pre = [s for s in segmenti if s[0] == "preambolo"]
    if rif and pre and (pre[0][3] - pre[0][2]) > 600:
        dubbi.append(f"preambolo lungo ({pre[0][3] - pre[0][2]} caratteri)")
    prec = None
    per_stile = {}
    tutti = {valore_etichetta(e, f) for _, e, _, _, f in rif}
    for _, e, _, _, f in rif:
        if f == "numerato":
            n = re.findall(r"\d+", e)
            tutti.update(range(int(n[0]), ultimo_numero(e) + 1))
    if any(s[4] == "coda" for s in rif):
        rif = []                              # rinvii a carte: niente controllo di continuità
    for tipo, etichetta, a, b, famiglia in rif:
        if famiglia not in ("numerato", "romano", "libro", "fascicolo", "lettera", "opera", "volume"):
            continue
        v = valore_etichetta(etichetta, famiglia)
        if v is None:
            continue
        # ogni forma di numerazione ha la sua sequenza («6° … 1. 2. 3. … 7°»)
        m = re.search(r"(°\)|\.\)|°|\)|\.)\s*$", etichetta)
        stile = famiglia if famiglia != "numerato" else (
            ")" if re.search(r"incl?\b", etichetta) or not m else m.group(1))
        prec = per_stile.get(stile)
        if prec is None and not per_stile and v > 1:
            dubbi.append(f"la numerazione comincia da «{etichetta}»")
        elif (prec is not None and v > prec[0] + 1 and v != 1
              and not (famiglia == "lettera" and prec[0] == 9 and v == 11)   # i) k): niente j
              and not set(range(prec[0] + 1, v)) <= tutti):   # mancanti presenti in altra forma («5.»)
            dubbi.append(f"la numerazione salta da «{prec[1]}» a «{etichetta}»")
        per_stile[stile] = (ultimo_numero(etichetta) if famiglia == "numerato" else v, etichetta)
    return dubbi


def main():
    percorso_db = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PREDEFINITO
    con = sqlite3.connect(percorso_db)
    con.execute("DELETE FROM segmenti")
    dubbie, scartati = {}, {}
    manuali = json.loads(MANUALI.read_text(encoding="utf-8")) if MANUALI.exists() else {}
    manuali = {k: v for k, v in manuali.items() if not k.startswith("_")}
    for vid, numero, testo in con.execute("SELECT id, numero, testo FROM voci ORDER BY id").fetchall():
        scarti = []
        segmenti = costruisci_segmenti(numero, testo, scarti, manuali)
        for ordine, (tipo, etichetta, a, b, _) in enumerate(segmenti, start=1):
            con.execute(
                "INSERT INTO segmenti (voce, ordine, tipo, etichetta, testo, inizio, fine)"
                " VALUES (?,?,?,?,?,?,?)",
                (vid, ordine, tipo, etichetta, testo[a:b], a, b))
        d = dubbi_per_voce(numero, testo, segmenti)
        if d:
            dubbie[numero] = d
        if scarti:
            scartati[numero] = scarti
    con.commit()
    n_seg = con.execute("SELECT count(*) FROM segmenti").fetchone()[0]
    n_voci = con.execute(
        "SELECT count(DISTINCT voce) FROM segmenti WHERE tipo != 'voce_intera'").fetchone()[0]
    con.close()
    DIAGNOSTICA.write_text(json.dumps({"dubbie": dubbie, "scartati": scartati},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Voci segmentate: {n_voci} — segmenti totali: {n_seg}")


if __name__ == "__main__":
    main()
