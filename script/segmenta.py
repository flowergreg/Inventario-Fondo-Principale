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
    r"(?:\n|[.;,]\s+|\b(?:[Cc]ontenente|[Cc]ontiene|[Cc]ontengono|[Cc]omprende)\s*:?\s+|\b(?:seguenti|cioè|di):\s+)"
)
CONNETTIVI = {
    "a", "al", "ai", "alla", "alle", "da", "dal", "dalla", "dai", "nel", "nella",
    "nei", "in", "segue", "seguono", "cui", "preceduta", "preceduto", "e", "ed",
    "poi", "indi", "quindi",
}
RX_CONNETTIVI = re.compile(r"((?:[A-Za-zà]+\s+){0,3})")

NUM = r"\d+(?:\s?[rv]°?|\s?t°)?"
INTERVALLO = NUM + r"(?:\s?(?:-|–)\s?" + NUM + r")?"
RX_FOGLI = re.compile(
    r"(?:fol(?:l|io|ii)?\.?|fogli?o?|ff?\.|cc?\.|carte|carta|pag(?:g|ina|ine)?\.?|pp?\.)"
    r"\s?" + INTERVALLO + r"(?![\d°])",
    re.I,
)
RX_FASC = re.compile(r"[Ff]asc(?:icolo|\.)\s?(?:\d+°?|[IVXLC]+\b)")
# parole che dopo un numero indicano una consistenza, non un rinvio
RX_CONTEGGIO = re.compile(
    r"(?:pezz|fogl|cart|cc\b|lett|fasc|vol|bust|pacc|docum|esempl|copi|pagin|pp?\b)", re.I)
RX_N = re.compile(r"N(?:\.°|°|\.|r\.)\s?\d+")
RX_NUDO = re.compile(r"(\d+)(?:\s?(?:-|–)\s?\d+)?(?:\.ª\))?(?=\s+[^\d\s°)])")
# elenchi numerati, anche a catena: «1°, 2°, 3°, 4° e 5°»
RX_NUMERATO = re.compile(
    r"(\d+)(?:\s?bis)?(°|\)|\.(?=\s))"
    r"((?:\s?(?:,|e|ed|-|a)\s?\d+(?:°|\)))*)"
)
RX_ABBREVIAZIONE = re.compile(
    r"\b(?:fol|foll|f|ff|c|cc|car|pag|pagg|p|pp|n|fasc)$", re.I)
RX_MESE = re.compile(
    r"(?:gen(?:naio|n?\.)|feb(?:braio|b?r?\.)|mar(?:zo|\.)|apr(?:ile|\.)|mag(?:gio|g?\.)"
    r"|giu(?:gno|\.)|lug(?:lio|\.)|ago(?:sto|\.)|set(?:tembre|t?\.)|ott(?:obre|\.)"
    r"|nov(?:embre|\.)|dic(?:embre|\.))", re.I)
RX_LETTERA = re.compile(r"([A-Za-z])(\.\d+)?(\s?bis)?\)")


def riferimento_a(testo, pos):
    """Se in `pos` comincia un riferimento, restituisce (famiglia, testo, valore)."""
    m = RX_FASC.match(testo, pos)
    if m:
        return "fascicolo", m.group(0), None
    m = RX_N.match(testo, pos)
    if m:
        return "numero", m.group(0), None
    m = RX_FOGLI.match(testo, pos)
    if m:
        v = re.search(r"\d+", m.group(0))
        return "fogli", m.group(0), int(v.group(0))
    m = RX_NUMERATO.match(testo, pos)
    if m:
        ultimi = re.findall(r"\d+", m.group(3)) if m.group(3) else []
        ultimo = int(ultimi[-1]) if ultimi else int(m.group(1))
        return "numerato", m.group(0), (int(m.group(1)), ultimo)
    m = RX_LETTERA.match(testo, pos)
    if m and (pos + len(m.group(0)) >= len(testo) or testo[pos + len(m.group(0))] in " \n"):
        return "lettera", m.group(0), m.group(1)
    m = RX_NUDO.match(testo, pos)
    if m:
        return "nudo", m.group(0), int(m.group(1))
    return None


def candidati(testo):
    """Posizioni di inizio proposizione, con l'eventuale riferimento che le apre."""
    posizioni = {0}
    for m in RX_DELIMITATORE.finditer(testo):
        # il punto di un'abbreviazione di riferimento («fol. 33») non chiude
        # una proposizione
        if testo[m.start()] == "." and RX_ABBREVIAZIONE.search(testo, 0, m.start()):
            continue
        posizioni.add(m.end())
    for inizio in sorted(posizioni):
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
        r = riferimento_a(testo, pos)
        if r:
            yield inizio, pos, r


def segmenta_riferimenti(testo, scarti):
    """Restituisce la lista di (inizio, etichetta) dei segmenti."""
    confini = []
    serie_fogli = None        # ultimo valore di fogli/pagine accettato
    ultimo_numerato = None
    ultima_lettera = None
    fine_ultimo = -1          # fine dell'ultimo riferimento accettato
    for inizio, pos, (famiglia, etichetta, valore) in candidati(testo):
        # niente candidati dentro un riferimento già accettato («Al fol.| 23»)
        if inizio < fine_ultimo:
            continue
        a_capo = inizio == 0 or testo[inizio - 1] == "\n"
        con_connettivo = pos > inizio
        dopo = testo[pos + len(etichetta):].lstrip(" ")
        if famiglia in ("fogli", "nudo", "numero"):
            # il riferimento deve introdurre un contenuto, non chiudere una
            # frase («16°, pp. 8.» è una consistenza, non un rinvio)
            if not dopo or dopo[0] in ".,;)\n":
                continue
        if famiglia == "numero" and RX_CONTEGGIO.match(dopo):
            continue
        if famiglia == "fogli":
            # «cc. 31», «carte 35», «ff. 18», «pp. 8» senza parola di
            # collegamento sono di norma consistenze: valgono solo a capo
            if (re.match(r"(?:cc?\.|cart[ea]|ff?\.|pp\.)", etichetta, re.I)
                    and not con_connettivo and not a_capo):
                continue
            serie_fogli = valore
        elif famiglia == "nudo":
            if serie_fogli is None or valore >= 1000 or not (serie_fogli <= valore <= serie_fogli + 300):
                continue
            if RX_MESE.match(dopo):
                continue
            serie_fogli = valore
        elif famiglia == "numerato":
            primo, ultimo = valore
            # la forma «1.» apre un elenco solo a capo o dopo i due punti
            if (etichetta.endswith(".") and ultimo_numerato is None and not a_capo
                    and not testo[:inizio].rstrip().endswith(":")):
                continue
            atteso = {0, 1} if ultimo_numerato is None else {ultimo_numerato, ultimo_numerato + 1}
            if primo not in atteso:
                scarti.append((etichetta, "numerazione fuori sequenza"))
                continue
            ultimo_numerato = ultimo
        elif famiglia == "lettera":
            l = valore.lower()
            if ultima_lettera is None:
                if l != "a":
                    scarti.append((etichetta, "lettera iniziale diversa da a"))
                    continue
            elif not (0 <= ord(l) - ord(ultima_lettera) <= 2):
                scarti.append((etichetta, "lettera fuori sequenza"))
                continue
            ultima_lettera = l
        confini.append((inizio, etichetta.strip(), famiglia))
        fine_ultimo = pos + len(etichetta)
    # un elenco numerato o letterale di un solo elemento non è un elenco
    # («1° cappellano», «a) …» senza «b)»): si scarta
    for famiglia in ("numerato", "lettera"):
        membri = [c for c in confini if c[2] == famiglia]
        if len(membri) == 1 and len(re.findall(r"\d+", membri[0][1])) <= 1:
            scarti.append((membri[0][1], "elenco di un solo elemento"))
            confini.remove(membri[0])
    # un riferimento isolato non divide la voce: di norma è una consistenza
    # («pag. 140 formato protocollo», «Fasc. 3.»); la voce resta intera
    if len(confini) == 1:
        scarti.append((confini[0][1], "riferimento isolato"))
        confini = []
    return confini


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

def costruisci_segmenti(numero, testo, scarti):
    chiusura = None
    modo = ELENCHI_ALFABETICI.get(numero)
    if modo == "virgole":
        confini, chiusura = elenco_virgole(testo)
    elif modo == "paragrafi":
        confini = elenco_paragrafi(testo)
    else:
        confini = segmenta_riferimenti(testo, scarti)
    if not confini:
        return [("voce_intera", "", 0, len(testo), None)]
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


def dubbi_per_voce(numero, testo, segmenti):
    dubbi = []
    rif = [s for s in segmenti if s[0] == "riferimento"]
    for tipo, etichetta, a, b, famiglia in segmenti:
        if tipo == "riferimento" and len(testo[a:b].strip()) - len(etichetta) < 8:
            dubbi.append(f"segmento quasi vuoto «{etichetta}»")
    pre = [s for s in segmenti if s[0] == "preambolo"]
    if rif and pre and (pre[0][3] - pre[0][2]) > 600:
        dubbi.append(f"preambolo lungo ({pre[0][3] - pre[0][2]} caratteri)")
    famiglie = {s[4] for s in rif}
    if len(famiglie - {"nudo"}) > 1:
        dubbi.append("famiglie di riferimenti miste: " + ", ".join(sorted(f for f in famiglie if f)))
    return dubbi


def main():
    percorso_db = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PREDEFINITO
    con = sqlite3.connect(percorso_db)
    con.execute("DELETE FROM segmenti")
    dubbie, scartati = {}, {}
    for vid, numero, testo in con.execute("SELECT id, numero, testo FROM voci ORDER BY id").fetchall():
        scarti = []
        segmenti = costruisci_segmenti(numero, testo, scarti)
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
