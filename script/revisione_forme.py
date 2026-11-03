#!/usr/bin/env python3
"""Report di revisione della fase 3 per forme (tutto l'inventario).

Ogni forma compare una volta, con il numero di occorrenze, le voci e un
esempio di contesto, ordinata per frequenza. Sezioni:
1. persone ad affidabilità bassa;
2. luoghi ad affidabilità media o bassa;
3. forme classificate in modo diverso in voci diverse;
4. non classificati;
5. santi (da dirimere).

Le decisioni del curatore si registrano in dati/liste/decisioni_forme.tsv
(forma, tipo: persona | luogo | santo | opera | nessuno, forma_riferimento, nota)
e valgono in tutte le voci; le eccezioni per singola voce in
dati/liste/classificazioni_manuali.tsv.

Uso: python3 script/revisione_forme.py
"""

import sqlite3
from collections import defaultdict
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
DB = RADICE / "dati" / "inventario.sqlite"
OUT = RADICE / "report" / "fase_3_revisione_forme.md"


def main():
    con = sqlite3.connect(DB)
    testi = {}

    def contesto(voce, sede, annotazione, a, b, largo=70):
        chiave = (voce, sede, annotazione)
        if chiave not in testi:
            if sede == "annotazione":
                testi[chiave] = con.execute("SELECT testo FROM annotazioni WHERE id=?", (annotazione,)).fetchone()[0]
            else:
                testi[chiave] = con.execute(f"SELECT coalesce({sede}, '') FROM voci WHERE id=?", (voce,)).fetchone()[0]
        t = testi[chiave]
        return (("…" if a > largo else "") + t[max(0, a - largo):a] + "**" + t[a:b] + "**" + t[b:b + largo]
                + ("…" if b + largo < len(t) else "")).replace("\n", " ").replace("|", "/")

    numeri = dict(con.execute("SELECT id, numero FROM voci"))

    def tabella(righe, titolo, nota):
        out = [f"## {titolo}\n", nota + "\n"]
        multiple = [r for r in righe if r[1] > 1]
        singole = [r for r in righe if r[1] == 1]
        out.append(f"Forme: {len(righe)} (di cui {len(singole)} con una sola occorrenza).\n")
        if multiple:
            out.append("| Forma | Occ. | Classificazione | Voci | Esempio |\n|---|---|---|---|---|")
            for forma, n, info, voci, es in multiple:
                vv = ", ".join(voci[:6]) + (" …" if len(voci) > 6 else "")
                out.append(f"| {forma} | {n} | {info} | {vv} | {es} |")
            out.append("")
        if singole:
            out.append("**Una sola occorrenza** (forma — voce: contesto)\n")
            for forma, n, info, voci, es in singole:
                out.append(f"- {forma} — {voci[0]} ({info}): {es}")
            out.append("")
        return out

    def raccogli(sql, *par):
        gruppi = defaultdict(list)
        for row in con.execute(sql, par):
            gruppi[row[0]].append(row)
        righe = []
        for forma, rr in gruppi.items():
            voci = sorted({numeri[r[1]] for r in rr}, key=lambda x: (len(x), x))
            info = ", ".join(sorted({r[6] for r in rr}))
            r0 = rr[0]
            righe.append((forma, len(rr), info, voci, contesto(r0[1], r0[2], r0[3], r0[4], r0[5])))
        righe.sort(key=lambda x: (-x[1], x[0]))
        return righe

    r = ["# Fase 3 — revisione per forme (tutto l'inventario)\n"]
    tot = con.execute("SELECT tipo, count(*) FROM menzioni GROUP BY 1").fetchall()
    nc = con.execute("SELECT count(*) FROM non_classificati").fetchone()[0]
    r.append("Menzioni: " + ", ".join(f"{t} {n}" for t, n in tot) + f"; non classificati: {nc}.\n")
    r.append("Per correggere: indica la forma e il tipo giusto (persona, luogo, santo, opera, nessuno). "
             "Le decisioni vanno in `dati/liste/decisioni_forme.tsv` e valgono in tutte le voci; "
             "le eccezioni per singola voce in `dati/liste/classificazioni_manuali.tsv`. "
             "La colonna «Classificazione» riporta la regola che ha prodotto la forma.\n")
    r.append("Indice: [1. Persone ad affidabilità bassa](#1-persone-ad-affidabilità-bassa) · "
             "[2. Luoghi incerti](#2-luoghi-incerti) · [3. Forme con classificazioni diverse](#3-forme-con-classificazioni-diverse) · "
             "[4. Non classificati](#4-non-classificati) · [5. Santi](#5-santi)\n")

    r += tabella(raccogli("SELECT testo_esatto, voce, sede, annotazione, inizio, fine, metodo FROM menzioni "
                          "WHERE tipo='persona' AND affidabilita='bassa'"),
                 "1. Persone ad affidabilità bassa",
                 "Forme classificate come persona con indizi deboli (autore in testa alla voce, destinatario, gruppo…).")
    r += tabella(raccogli("SELECT testo_esatto, voce, sede, annotazione, inizio, fine, metodo FROM menzioni "
                          "WHERE tipo='luogo' AND affidabilita IN ('media','bassa')"),
                 "2. Luoghi incerti", "Forme classificate come luogo per contesto o da liste a peso medio o debole.")

    # forme con più tipi
    tipi = defaultdict(lambda: defaultdict(list))
    for forma, tipo, voce, sede, ann, a, b in con.execute(
            "SELECT testo_esatto, tipo, voce, sede, annotazione, inizio, fine FROM menzioni"):
        tipi[forma][tipo].append((voce, sede, ann, a, b))
    ambigue = [(f, d) for f, d in tipi.items() if len(d) > 1]
    ambigue.sort(key=lambda x: (-sum(len(v) for v in x[1].values()), x[0]))
    r.append("## 3. Forme con classificazioni diverse\n")
    r.append("La stessa forma è persona in alcune voci e luogo (o santo, opera) in altre. "
             "Può essere giusto (Udine città, «del Monti» persona) o un errore da correggere.\n")
    r.append(f"Forme: {len(ambigue)}.\n")
    r.append("| Forma | Per tipo | Esempi |\n|---|---|---|")
    for forma, d in ambigue:
        per_tipo = ", ".join(f"{t} {len(v)}" for t, v in sorted(d.items(), key=lambda x: -len(x[1])))
        esempi = " · ".join(f"*{t}* ({numeri[v[0][0]]}): {contesto(v[0][0], v[0][1], v[0][2], v[0][3], v[0][4], 45)}"
                            for t, v in d.items())
        r.append(f"| {forma} | {per_tipo} | {esempi} |")
    r.append("")

    r += tabella(raccogli("SELECT testo_esatto, voce, sede, annotazione, inizio, fine, sede FROM non_classificati"),
                 "4. Non classificati",
                 "Parole con iniziale maiuscola che le regole non hanno classificato: per lo più parole comuni, "
                 "ma anche nomi da recuperare.")
    r += tabella(raccogli("SELECT testo_esatto, voce, sede, annotazione, inizio, fine, metodo FROM menzioni "
                          "WHERE tipo='santo'"),
                 "5. Santi", "Da dirimere: persona, chiesa o luogo.")

    OUT.write_text("\n".join(r) + "\n", encoding="utf-8")
    print(f"Report scritto in {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
