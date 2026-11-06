#!/usr/bin/env python3
"""Fase 7 — indice e logica di ricerca (condivisa con la pagina web, che la riproduce in JavaScript).

Indice (`costruisci_indice`), esportato in JSON:
- voci: numero, testo, coda, annotazioni, segmenti (etichetta, inizio, fine);
- espansioni: parola normalizzata → altre parole normalizzate equivalenti, dal lessico
  (forma ↔ forma normalizzata: Zuan ↔ Giovanni, Udene ↔ Udine, Jac. → Giacomo, Jacopo),
  in senso diretto e inverso ma senza chiusura transitiva (Giacomo trova Jac., non ogni Jacopo),
  più le varianti equivalenti dei nomi di battesimo di entita.py (Ludovico ↔ Lodovico) e le grafie
  di famiglia confermate dal curatore (Delfino ↔ Dolfin);
- entità: tipo, intestazione, stato, identificativo Wikidata, varianti normalizzate
  (testo, correzioni, lessico, fonti esterne) e menzioni (voce, sede, inizio, fine).

Ricerca (`cerca`), su quattro livelli in ordine di precisione:
1. entità: tutte le parole della domanda (espanse) stanno in una variante di un'entità →
   tutte le sue menzioni, anche in grafie lontane (Ermes di Colloredo = Colloredo (di) Ermes);
2. testo: tutte le parole della domanda (espanse) nel testo normalizzato di una voce, vicine
   (entro una finestra di parole), in qualunque ordine;
3. approssimata (solo se 1 e 2 non danno nulla): ogni parola può differire di una lettera
   (parole di almeno 5 lettere).
Particelle e titoli della domanda non contano. I risultati sono raggruppati per voce, con
il segmento, un frammento con la forma evidenziata e il livello.

Normalizzazione (CLAUDE.md): minuscole, niente accenti, j→i, y→i, doppie semplificate,
punteggiatura ignorata; le parole fatte solo di cifre romane maiuscole non si semplificano.
"""

import csv
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
DB = RADICE / "dati" / "inventario.sqlite"
RX_PAROLA = re.compile(r"[^\W_]+")
RX_ROMANO = re.compile(r"^[IVXLCDM]+$")
VUOTE = {"di", "de", "da", "del", "della", "dela", "dei", "degli", "degl", "dal", "dala", "dalla", "dele", "delle",
         "d", "e", "ed", "a", "al", "il", "la", "lo", "le", "i", "gli", "in", "von", "van", "der", "den",
         "co", "conte", "contessa", "nob", "sig", "sr", "don", "d", "p", "fra", "frate", "padre", "ab", "abate",
         "mons", "monsignor", "dott", "dr", "prof", "cav", "can", "card", "vesc", "patr", "pre", "prete"}


def norm_parola(p):
    """Normalizzazione di una parola già senza punteggiatura (come normalizza.py)."""
    if RX_ROMANO.match(p):
        return p.lower()
    p = unicodedata.normalize("NFKD", p)
    p = "".join(c for c in p if not unicodedata.combining(c))
    p = p.lower().replace("j", "i").replace("y", "i")
    p = p.replace("æ", "ae").replace("œ", "oe").replace("ß", "ss")
    return re.sub(r"(\w)\1+", r"\1", p)


RX_STACCO = re.compile(r"[,;:\n\[\]]|\((?!\s*(?:di|de|da|d['’])\s*\))|(?<!\((?:di|de|da))\)")


def parole(testo):
    """[(parola normalizzata, inizio, fine, blocco)] nel testo originale. Il blocco cambia a ogni
    virgola, punto e virgola, due punti, a capo o parentesi (non «(di)»): un nome non li attraversa,
    così «Udine 1692); Gio. Ant.o» non vale come «Giovanni da Udine»."""
    testo = testo or ""
    uscita, blocco, ultimo = [], 0, 0
    for m in RX_PAROLA.finditer(testo):
        if RX_STACCO.search(testo, ultimo, m.start()):
            blocco += 1
        uscita.append((norm_parola(m.group(0)), m.start(), m.end(), blocco))
        ultimo = m.end()
    return uscita


def chiave(testo):
    return [p[0] for p in parole(testo) if p[0] and p[0] not in VUOTE]


# ---------------------------------------------------------------------------
# Indice
# ---------------------------------------------------------------------------

def costruisci_indice(db=DB):
    con = sqlite3.connect(db)
    voci, pos = [], {}
    for vid, numero, testo, coda in con.execute("SELECT id, numero, testo, coda FROM voci ORDER BY id"):
        pos[vid] = len(voci)
        voci.append({"n": numero, "t": testo or "", "c": coda or "", "a": [], "s": []})
    ann_pos = {}
    for aid, vid, testo in con.execute("SELECT id, voce, testo FROM annotazioni WHERE voce IS NOT NULL ORDER BY id"):
        ann_pos[aid] = (pos[vid], len(voci[pos[vid]]["a"]))
        voci[pos[vid]]["a"].append(testo or "")
    for vid, etichetta, ini, fin in con.execute("SELECT voce, etichetta, inizio, fine FROM segmenti "
                                                "ORDER BY voce, ordine"):
        if etichetta:
            voci[pos[vid]]["s"].append([etichetta, ini, fin])

    # espansioni dal lessico: forma ↔ forma normalizzata (solo parola ↔ parola)
    esp = defaultdict(set)
    for forma, norm in con.execute("SELECT forma, forma_normalizzata FROM lessico WHERE forma_normalizzata IS NOT NULL"):
        f = chiave(forma)
        alternative = [chiave(x) for x in re.split(r"\s+o\s+", norm)]   # «Giacomo o Jacopo»
        if len(f) != 1:
            continue
        for a in alternative:
            if len(a) == 1 and a[0] != f[0]:
                esp[f[0]].add(a[0])       # Jac. → Giacomo, Jacopo
                esp[a[0]].add(f[0])       # Giacomo → Jac. (non Jacopo)

    # varianti dello stesso nome di battesimo (le stesse che entita.py usa per le chiavi):
    # equivalenti a tutti gli effetti, quindi in ogni direzione (Ludovico ↔ Lodovico, Gian ↔ Giovanni)
    from entita import EQUIVALENTI, FUSI
    gruppi = defaultdict(set)
    for a, b in EQUIVALENTI.items():
        gruppi[b] |= {a, b}
    for a, b in FUSI.items():
        if len(b) == 1:
            gruppi[b[0]] |= {a, b[0]}
    for g in gruppi.values():
        for x in g:
            esp[x] |= g - {x}

    # nomi con due forme di riferimento («Jacobus» → «Giacomo o Jacopo»): come nel lessico, senza chiusura
    for r in csv.DictReader(open(RADICE / "dati" / "liste" / "nomi_equivalenti.tsv", encoding="utf-8"), delimiter="\t"):
        if " o " in r["nome"]:
            f = chiave(r["forma"])
            for alt in re.split(r"\s+o\s+", r["nome"]):
                a = chiave(alt)
                if len(f) == 1 and len(a) == 1:
                    esp[f[0]].add(a[0])
                    esp[a[0]].add(f[0])

    # grafie di famiglia decise dal curatore (fase 6, unioni_curatore.tsv, tipo «cognome»):
    # Delfino ↔ Dolfin, Sommariva ↔ Summaripa
    for r in csv.DictReader(open(RADICE / "dati" / "liste" / "unioni_curatore.tsv", encoding="utf-8"), delimiter="\t"):
        if r["tipo"] == "cognome" and r["decisione"] == "sì":
            a, b = chiave(r["forma_a"]), chiave(r["forma_b"])
            if len(a) == 1 and len(b) == 1 and a != b:
                esp[a[0]].add(b[0])
                esp[b[0]].add(a[0])

    # entità con varianti e menzioni
    entita = []
    stato_id = {}
    for eid, tipo, intest, stato in con.execute("SELECT id, tipo, forma_intestazione, stato FROM entita ORDER BY id"):
        stato_id[eid] = len(entita)
        entita.append({"i": eid, "t": tipo, "f": intest, "st": stato, "v": set(), "m": [], "q": None})
    for eid, forma in con.execute("SELECT entita, forma FROM varianti"):
        if re.search(r"\s(?:e|ed)\s", forma) and entita[stato_id[eid]]["t"] == "persona":
            continue           # «Girolamo e Lorenzo Carboni»: più persone, la variante confonderebbe i nomi
        k = " ".join(chiave(forma))
        if k:
            entita[stato_id[eid]]["v"].add(k)
    for eid, intest in con.execute("SELECT id, forma_intestazione FROM entita"):
        entita[stato_id[eid]]["v"].add(" ".join(chiave(intest)))
    for eid, qid in con.execute("SELECT entita, codice FROM identificatori WHERE fonte='Wikidata' "
                                "AND affidabilita='alta'"):
        if eid in stato_id:
            entita[stato_id[eid]]["q"] = qid
    for eid, url in con.execute("SELECT entita, url FROM identificatori WHERE fonte='DBF'"):
        if eid in stato_id:
            entita[stato_id[eid]]["d"] = url          # scheda del Dizionario Biografico dei Friulani
    for eid, vid, sede, aid, ini, fin in con.execute(
            "SELECT entita, voce, sede, annotazione, inizio, fine FROM menzioni WHERE entita IS NOT NULL"):
        if sede == "annotazione":
            if aid not in ann_pos:
                continue
            sede = "a%d" % ann_pos[aid][1]
        entita[stato_id[eid]]["m"].append([pos[vid], sede, ini, fin])
    for e in entita:
        e["v"] = sorted(x for x in e["v"] if x)
    # parole che nel testo sono soprattutto nomi di luogo (Udine, Venezia, Cividale; non Savorgnan,
    # Colloredo, Manzano, che sono soprattutto cognomi): se la domanda è fatta solo di parole così,
    # non si riconosce una persona per forma («Udine» non trova «Vincenzo Giusti da Udine»)
    occ = defaultdict(lambda: defaultdict(int))
    for forma, parte, n in con.execute("SELECT forma, parte, occorrenze FROM lessico"):
        for w in chiave(forma):
            occ[w][parte] += n or 0
    luoghi = {w for w, o in occ.items()
              if o.get("luogo", 0) > o.get("cognome", 0) + o.get("nome_di_battesimo", 0)}
    con.close()
    return {"voci": voci, "espansioni": {k: sorted(v) for k, v in esp.items()}, "entita": entita,
            "vuote": sorted(VUOTE), "luoghi": sorted(luoghi)}


# ---------------------------------------------------------------------------
# Ricerca
# ---------------------------------------------------------------------------

def espandi(t, indice):
    return {t} | set(indice["espansioni"].get(t, []))


def distanza_uno(a, b):
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def testi_voce(v):
    yield "t", v["t"]
    if v["c"]:
        yield "c", v["c"]
    for k, a in enumerate(v["a"]):
        yield "a%d" % k, a


def segmento(v, sede, ini):
    if sede != "t":
        return {"c": "coda", "a": "annotazione"}.get(sede[0], "")
    return next((s[0] for s in v["s"] if s[1] <= ini < s[2]), "")


def cerca(domanda, indice, finestra=None, approssimata=True):
    q = chiave(domanda)
    if not q:
        return []
    insiemi = [espandi(t, indice) for t in q]
    finestra = finestra or max(len(q) + 2, 4)
    risultati = defaultdict(list)           # voce → [(livello, sede, inizio, fine, entità)]

    # 1. entità (una domanda fatta solo di nomi di luogo non riconosce persone)
    solo_luoghi = all(t in set(indice.get("luoghi", ())) for t in q)
    for e in indice["entita"]:
        for var in e["v"]:
            vw = set(var.split())
            if all(s & vw for s in insiemi) and (e["t"] != "persona" or not solo_luoghi):
                for vi, sede, ini, fin in e["m"]:
                    s = {"testo": "t", "coda": "c"}.get(sede, sede)
                    risultati[vi].append((1, s, ini, fin, e))
                break

    # 2. testo: tutte le parole entro la finestra
    def nel_testo(insiemi_):
        trovati = defaultdict(list)
        for vi, v in enumerate(indice["voci"]):
            for sede, testo in testi_voce(v):
                pw = parole(testo)
                if not all(any(p[0] in s for p in pw) for s in insiemi_):
                    continue
                tutte = set().union(*insiemi_)
                for i, (w, ini, fin, bl) in enumerate(pw):
                    if w not in tutte:
                        continue
                    tratto = [p for p in pw[i:i + finestra] if p[3] == bl]     # stesso blocco
                    if all(any(p[0] in s for p in tratto) for s in insiemi_):
                        fine = max(p[2] for p in tratto if p[0] in tutte)
                        trovati[vi].append((sede, ini, fine))
                        break
        return trovati

    for vi, hits in nel_testo(insiemi).items():
        for sede, ini, fin in hits:
            risultati[vi].append((2, sede, ini, fin, None))

    # 3. approssimata
    if approssimata and not risultati:
        vocabolario = set()
        for v in indice["voci"]:
            for _, testo in testi_voce(v):
                vocabolario.update(p[0] for p in parole(testo))
        larghi = []
        for s in insiemi:
            simili = set(s)
            for t in s:
                if len(t) >= 5:
                    simili |= {w for w in vocabolario if distanza_uno(t, w)}
            larghi.append(simili)
        for vi, hits in nel_testo(larghi).items():
            for sede, ini, fin in hits:
                risultati[vi].append((3, sede, ini, fin, None))

    uscita = []
    for vi, hits in risultati.items():
        v = indice["voci"][vi]
        hits.sort(key=lambda h: (h[0], h[1] != "t", h[2]))
        uscita.append({"voce": v["n"], "indice": vi, "livello": hits[0][0],
                       "punti": [{"livello": l, "sede": s, "segmento": segmento(v, s, i), "inizio": i, "fine": f,
                                  "entita": (e["f"], e["t"], e["st"], e["q"]) if e else None}
                                 for l, s, i, f, e in hits]})
    uscita.sort(key=lambda r: (r["livello"], r["indice"]))
    return uscita


def frammento(indice, vi, sede, ini, fin, contesto=60):
    v = indice["voci"][vi]
    testo = dict(testi_voce(v))[sede]
    a, b = max(0, ini - contesto), min(len(testo), fin + contesto)
    return (("…" if a else "") + testo[a:ini] + "[" + testo[ini:fin] + "]" + testo[fin:b]
            + ("…" if b < len(testo) else "")).replace("\n", " / ")
