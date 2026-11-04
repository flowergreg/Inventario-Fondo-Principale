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

Uso: python3 script/revisione.py 1
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


if __name__ == "__main__":
    {"1": blocco1}[sys.argv[1] if len(sys.argv) > 1 else "1"](sqlite3.connect(DB))
