#!/usr/bin/env python3
"""Fase 6 — tabelle di revisione per il curatore (CSV con «;», leggibili da Excel).

Blocco 1, unioni da decidere (`revisione/fase6_1_unioni.csv`):
- coppie di persone con lo stesso nome di battesimo (a meno delle varianti equivalenti,
  già unificate nella chiave: Ludovico = Lodovico) e cognomi che differiscono di una
  lettera (Teck/Tech, Caetani/Gaetani) o dove un cognome contiene l'altro
  (Teck / «Teck Pagine»: di solito un errore di scomposizione);
- coppie di luoghi le cui intestazioni differiscono di una lettera;
- le proposte grafiche di arricchisci.py (cognomi che Wikidata scrive diversamente).

Colonne: n; proposta (sì / no / ?); motivazione; decisione (vuota = vale la proposta); nota curatore;
  tipo; forma A; voci A;
forma B; voci B; motivo; contesto A; contesto B. Il curatore cambia solo la colonna «decisione»
(vuota = accetta la proposta) e, se vuole, scrive nella colonna «nota curatore». Le proposte e
le motivazioni le compila il revisore dopo la generazione (non si rigenera un file già annotato).

Uso: python3 script/revisione.py 1 | dbf
"""

import csv
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ricerca import chiave, distanza_uno  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
DB = RADICE / "dati" / "inventario.sqlite"
DIR = RADICE / "revisione"
CONTESTO = 70


def contesti(con):
    """entità → (voci ordinate, primo frammento con la menzione tra «»)."""
    voci = {vid: (num, testo) for vid, num, testo in con.execute("SELECT id, numero, testo FROM voci")}
    per = defaultdict(list)
    for eid, vid, sede, ini, fin in con.execute(
            "SELECT entita, voce, sede, inizio, fine FROM menzioni WHERE entita IS NOT NULL ORDER BY voce, inizio"):
        per[eid].append((vid, sede, ini, fin))
    uscita = {}
    for eid, ms in per.items():
        numeri = list(dict.fromkeys(voci[m[0]][0] for m in ms))
        fr = ""
        for vid, sede, ini, fin in ms:
            if sede == "testo":
                t = voci[vid][1]
                a, b = max(0, ini - CONTESTO), min(len(t), fin + CONTESTO)
                fr = (f"{voci[vid][0]}: " + ("…" if a else "") + t[a:ini] + "«" + t[ini:fin] + "»" + t[fin:b]
                      + ("…" if b < len(t) else "")).replace("\n", " / ")
                break
        uscita[eid] = (numeri, fr)
    return uscita


def blocco1(con):
    ctx = contesti(con)
    righe = []
    # persone: stessa parte «nomi» della chiave, cognomi vicini
    per_nome = defaultdict(list)
    for eid, intest, ch in con.execute("SELECT id, forma_intestazione, chiave FROM entita WHERE tipo='persona'"):
        if not ch or " / " not in ch:
            continue
        nomi, cogn = ch.split(" / ", 1)
        if nomi and cogn:
            per_nome[nomi].append((eid, intest, cogn))
    for nomi, l in per_nome.items():
        for i in range(len(l)):
            for j in range(i + 1, len(l)):
                (ea, fa, ca), (eb, fb, cb) = l[i], l[j]
                if ca == cb:
                    continue
                wa, wb = set(ca.split()), set(cb.split())
                if distanza_uno(ca, cb):
                    motivo = "cognomi a una lettera di distanza"
                elif wa < wb or wb < wa:
                    motivo = "un cognome contiene l'altro"
                else:
                    continue
                righe.append(("persona", motivo, ea, fa, eb, fb))
    # luoghi a una lettera di distanza (almeno 5 lettere)
    luoghi = [(eid, f, " ".join(chiave(f))) for eid, f in
              con.execute("SELECT id, forma_intestazione FROM entita WHERE tipo='luogo'")]
    for i in range(len(luoghi)):
        for j in range(i + 1, len(luoghi)):
            (ea, fa, ka), (eb, fb, kb) = luoghi[i], luoghi[j]
            if ka != kb and min(len(ka), len(kb)) >= 5 and distanza_uno(ka, kb):
                righe.append(("luogo", "luoghi a una lettera di distanza", ea, fa, eb, fb))
    # proposte grafiche da Wikidata
    proposte = []
    for forma, origine in con.execute("SELECT forma, origine FROM lessico WHERE origine LIKE 'proposta: Wikidata%'"):
        m = re.search(r"«(.+?)» \((.+)\)", origine)
        proposte.append((forma, m.group(1) if m else "", m.group(2) if m else origine))

    righe.sort(key=lambda r: (r[0] != "persona", r[1], r[3].lower()))
    DIR.mkdir(exist_ok=True)
    out = DIR / "fase6_1_unioni.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["n", "proposta", "motivazione", "decisione", "nota curatore", "tipo", "forma A", "voci A",
                    "forma B", "voci B", "motivo", "contesto A", "contesto B"])
        n = 0
        for tipo, motivo, ea, fa, eb, fb in righe:
            n += 1
            va, xa = ctx.get(ea, ([], ""))
            vb, xb = ctx.get(eb, ([], ""))
            w.writerow([n, "", "", "", "", tipo, fa, ", ".join(va[:8]), fb, ", ".join(vb[:8]), motivo, xa, xb])
        for forma, wd, rif in proposte:
            n += 1
            w.writerow([n, "", "", "", "", "cognome", forma, "", wd, "", f"grafia di Wikidata ({rif})", "", ""])
    print(f"{n} righe in {out}")


def blocco_dbf(con):
    """Corrispondenze tra le forme di riferimento di persona e le schede del Dizionario Biografico dei
    Friulani (indice e «Altri nomi» in dati/esterni/). Una scheda è candidata se il cognome della forma
    coincide con il cognome della scheda o con uno dei suoi altri nomi (anche come radice: Geronimiani ~
    Geronimiano) e il nome di battesimo è compatibile (varianti equivalenti comprese). Proposta «sì» se gli
    anni scritti vicino alle menzioni cadono per almeno metà nella vita della persona."""
    import json
    import entita as ent_mod
    from normalizza import normalizza
    esterni = RADICE / "dati" / "esterni"
    idx = json.load(open(esterni / "dbf_indice.json", encoding="utf-8"))
    altri = json.load(open(esterni / "dbf_altri_nomi.json", encoding="utf-8")) if (esterni / "dbf_altri_nomi.json").exists() else {}
    part = {"di", "de", "da", "del", "della", "dei", "degli", "d", "von", "van", "dal", "dalla", "le", "la", "delli"}

    def parole(x):
        return [w for w in normalizza(re.sub(r"\(.*?\)", " ", x).replace("'", " ")).split() if w not in part]

    def nomi_k(x):
        out = []
        for w in normalizza(x).split():
            w = ent_mod.EQUIVALENTI.get(w, w)
            out.extend(ent_mod.FUSI.get(w, [w]))
        return out

    def radice(w):
        return re.sub(r"(ius|ium|ii|ij|us|um|is|ae|am|i|o|e|a)$", "", w) if len(w) > 5 else w

    schede = []
    per_cognome = defaultdict(list)
    for d in idx:
        alt = [a.strip(" .") for a in re.split(r"\s*[,;/]\s*", altri.get(d["url"], "") or "") if a.strip(" .")]
        cogn = {" ".join(parole(d["cognome"]))}
        nomi = [nomi_k(d["nome"])]
        for a in alt:
            ws = parole(a)
            if len(ws) == 1:
                cogn.add(ws[0])
            elif ws:
                for w in ws:          # «Graziani Publio Augusto»: ogni parola può essere il cognome
                    cogn.add(w)
                nomi.append(nomi_k(" ".join(ws)))
        d = dict(d, altri=alt, nomi=nomi)
        schede.append(d)
        for cg in cogn:
            per_cognome[cg].append(d)
            per_cognome[radice(cg)].append(d)

    rx_anno = re.compile(r"\b(1[0-9]{3})\b")
    anni = defaultdict(set)
    for eid, t, i, f in con.execute("SELECT m.entita, v.testo, m.inizio, m.fine FROM menzioni m JOIN voci v "
                                    "ON v.id=m.voce WHERE m.sede='testo' AND m.entita IS NOT NULL"):
        anni[eid] |= {int(a) for a in rx_anno.findall((t or "")[max(0, i - 200):f + 200])}
    gia = {eid for (eid,) in con.execute("SELECT entita FROM identificatori WHERE fonte='DBF'")}
    miste = set()
    for r in csv.DictReader(open(RADICE / "dati" / "liste" / "persone_collegamenti.tsv", encoding="utf-8"), delimiter="\t"):
        if not r["qid"] and re.search(r"raccoglie|più persone|omonim", r["nota"] or ""):
            miste.add(r["intestazione"])

    def vita(d):
        m = re.findall(r"(\d{3,4})", d["date"])
        if not m:
            return None
        n0 = int(m[0]); n1 = int(m[-1]) if len(m) > 1 else n0 + 90
        return n0, n1

    righe = []
    for eid, h in con.execute("SELECT id, forma_intestazione FROM entita WHERE tipo='persona' AND forma_intestazione LIKE '%, %'"):
        if eid in gia:
            continue
        cogn, nomi = h.split(", ", 1)
        if re.search(r"\b[A-Z]\.", nomi) or not nomi.strip():
            continue
        ck = " ".join(parole(cogn))
        nk = nomi_k(nomi)
        cand = {d["url"]: d for k in {ck, radice(ck)} for d in per_cognome.get(k, [])}
        def nomi_ok(n):
            # stesso primo nome; se entrambe le forme hanno due nomi, anche il secondo deve combaciare
            if not n or not nk or n[0] != nk[0]:
                return False
            return len(n) < 2 or len(nk) < 2 or n[1] == nk[1]
        cand = [d for d in cand.values() if any(nomi_ok(n) for n in d["nomi"])]
        if not cand:
            continue
        ys = anni.get(eid, set())

        def quota(d):
            v = vita(d)
            if not v or not ys:
                return None
            return sum(1 for y in ys if v[0] - 5 <= y <= v[1] + 60) / len(ys)
        ok = [d for d in cand if quota(d) is None or quota(d) > 0]
        voci = [v for (v,) in con.execute("SELECT DISTINCT v.numero FROM menzioni m JOIN voci v ON v.id=m.voce WHERE m.entita=?", (eid,))]
        wd = con.execute("SELECT codice FROM identificatori WHERE entita=? AND fonte='Wikidata' AND affidabilita='alta'", (eid,)).fetchone()
        via_altri = lambda d: not {" ".join(parole(d["cognome"])), radice(" ".join(parole(d["cognome"])))} & {ck, radice(ck)}
        if len(ok) == 1:
            d = ok[0]; q = quota(d)
            if h in miste:
                p, mot = "?", "la forma raccoglie più omonimi (collegamento Wikidata tolto nel blocco 4)"
            elif q is None:
                p, mot = "?", "stesso nome; nessun anno vicino alle menzioni per verificare"
            elif q >= 0.5:
                p, mot = "sì", "nome compatibile e anni della voce nella vita della persona"
            else:
                p, mot = "?", "solo una parte degli anni della voce cade nella vita della persona"
            if via_altri(d):
                mot += f"; trovata attraverso gli altri nomi ({', '.join(d['altri'])})"
        elif len(ok) > 1:
            d = None; p = "?"
            mot = "più schede compatibili: " + "; ".join(f"{x['cognome']} {x['nome']} ({x['date']}) {x['url']}" for x in ok)
        else:
            d = cand[0]; p = "no"; mot = f"stesso nome ma un'altra epoca ({d['date']})"
        righe.append([p, mot, h, ", ".join(voci[:6]), ", ".join(str(y) for y in sorted(ys)[:6]),
                      f"{d['cognome']} {d['nome']}" if d else "", d["date"] if d else "",
                      ", ".join(d["altri"]) if d else "", d["url"] if d else "", wd[0] if wd else ""])
    righe.sort(key=lambda x: ({"sì": 0, "?": 1, "no": 2}[x[0]], x[2]))
    out = DIR / "fase6_6_dbf.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["n", "proposta", "motivazione", "decisione", "nota curatore", "forma", "voci", "anni nella voce",
                    "scheda DBF", "date DBF", "altri nomi DBF", "url", "Wikidata già presente"])
        for i, x in enumerate(righe, 1):
            w.writerow([i, x[0], x[1], "", ""] + x[2:])
    from collections import Counter
    print(f"{len(righe)} righe in {out}: {dict(Counter(x[0] for x in righe))}")


if __name__ == "__main__":
    {"1": blocco1, "dbf": blocco_dbf}[sys.argv[1] if len(sys.argv) > 1 else "1"](sqlite3.connect(DB))
