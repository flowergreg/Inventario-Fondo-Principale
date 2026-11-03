#!/usr/bin/env python3
"""Report di controllo della fase 3 (estrazione delle menzioni).

Scrive:
- report/report_fase_3.md: numeri, metodi, correzioni del curatore, santi,
  forme più frequenti, non classificati;
- report/fase_3_voci_annotate.md: ogni voce estratta con le menzioni segnate
  nel testo: [Nome|P] persona, [Nome|L] luogo, [Nome|S] santo, con l'eventuale
  correzione («→ Morlupino») e l'affidabilità bassa segnata con «?».

Uso: python3 script/report_fase3.py
"""

import sqlite3
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
DB = RADICE / "dati" / "inventario.sqlite"
OUT = RADICE / "report" / "report_fase_3.md"
OUT_VOCI = RADICE / "report" / "fase_3_voci_annotate.md"
SIGLA = {"persona": "P", "luogo": "L", "santo": "S", "opera": "O"}


def annota(testo, menzioni):
    out, p = [], 0
    for a, b, tipo, corr, aff in menzioni:
        out.append(testo[p:a])
        segno = SIGLA[tipo] + ("?" if aff == "bassa" else "")
        out.append(f"**[{testo[a:b]}|{segno}{' → ' + corr if corr else ''}]**")
        p = b
    out.append(testo[p:])
    return "".join(out)


def main():
    con = sqlite3.connect(DB)
    r = []
    w = r.append
    q = lambda s, *a: con.execute(s, a).fetchall()  # noqa: E731
    n_voci = q("SELECT count(DISTINCT voce) FROM menzioni")[0][0]
    w("# Report fase 3 — Estrazione di persone, luoghi e santi\n")
    w(f"Voci elaborate: **{q('SELECT count(*) FROM voci WHERE id IN (SELECT voce FROM menzioni UNION SELECT voce FROM non_classificati)')[0][0]}** "
      f"(con almeno una menzione: {n_voci}). Le voci annotate sono in `fase_3_voci_annotate.md`.\n")
    w("## 1. Menzioni\n")
    w("| Tipo | alta | media | bassa | Totale |\n|---|---|---|---|---|")
    for tipo in ("persona", "luogo", "santo", "opera"):
        conti = {a: n for a, n in q("SELECT affidabilita, count(*) FROM menzioni WHERE tipo=? GROUP BY 1", tipo)}
        w(f"| {tipo} | {conti.get('alta', 0)} | {conti.get('media', 0)} | {conti.get('bassa', 0)} | {sum(conti.values())} |")
    w("")
    w("Per sede: " + ", ".join(f"{s} {n}" for s, n in q("SELECT sede, count(*) FROM menzioni GROUP BY 1")) + "\n")
    w("### Metodi\n")
    w("| Tipo | Metodo | Affidabilità | Numero |\n|---|---|---|---|")
    for row in q("SELECT tipo, metodo, affidabilita, count(*) FROM menzioni GROUP BY 1,2,3 ORDER BY 1, 4 DESC"):
        w("| " + " | ".join(map(str, row)) + " |")
    w("")
    w("## 2. Correzioni del curatore (diventeranno varianti con origine `correzione_curatore`)\n")
    for v, t, c in q("SELECT v.numero, m.testo_esatto, m.correzione FROM menzioni m JOIN voci v ON v.id=m.voce "
                     "WHERE m.correzione IS NOT NULL ORDER BY v.id"):
        w(f"- {v}: {t} → **{c}**")
    w("")
    w("## 3. Santi (da dirimere: persona, chiesa o luogo)\n")
    for t, n in q("SELECT testo_esatto, count(*) FROM menzioni WHERE tipo='santo' GROUP BY 1 ORDER BY 2 DESC, 1"):
        w(f"- {t} ({n})")
    w("")
    for tipo, titolo in (("persona", "Persone"), ("luogo", "Luoghi")):
        w(f"## 4. {titolo}: forme più frequenti\n")
        righe = q("SELECT testo_esatto, count(*) FROM menzioni WHERE tipo=? GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 80", tipo)
        w(", ".join(f"{t} ({n})" for t, n in righe) + "\n")
        w(f"### {titolo} ad affidabilità bassa (da controllare)\n")
        righe = q("SELECT testo_esatto, metodo, count(*) FROM menzioni WHERE tipo=? AND affidabilita='bassa' "
                  "GROUP BY 1, 2 ORDER BY 3 DESC, 1", tipo)
        w(", ".join(f"{t} [{m}] ({n})" for t, m, n in righe) + "\n")
    w("## 5. Non classificati (parole maiuscole né persona né luogo), per frequenza\n")
    righe = q("SELECT testo_esatto, count(*) FROM non_classificati GROUP BY 1 ORDER BY 2 DESC, 1")
    w(", ".join(f"{t} ({n})" for t, n in righe) + "\n")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(r) + "\n", encoding="utf-8")

    # voci annotate
    v_out = ["# Fase 3 — voci con le menzioni segnate\n",
             "Legenda: **[Nome|P]** persona, **[Nome|L]** luogo, **[Nome|S]** santo, **[Titolo|O]** opera; «?» = affidabilità bassa; "
             "«→» = correzione del curatore. Sotto il testo: coda, annotazioni e parole non classificate.\n"]
    for vid, numero, testo, coda in q("SELECT id, numero, testo, coda FROM voci WHERE id IN "
                                      "(SELECT voce FROM menzioni UNION SELECT voce FROM non_classificati) ORDER BY id"):
        v_out.append(f"### {numero}\n")
        mz = q("SELECT inizio, fine, tipo, correzione, affidabilita FROM menzioni WHERE voce=? AND sede='testo' "
               "ORDER BY inizio", vid)
        v_out.append(annota(testo, mz).replace("\n", "  \n") + "\n")
        if coda:
            mz = q("SELECT inizio, fine, tipo, correzione, affidabilita FROM menzioni WHERE voce=? AND sede='coda' "
                   "ORDER BY inizio", vid)
            v_out.append("*Coda*: " + annota(coda, mz) + "\n")
        for aid, at in q("SELECT id, testo FROM annotazioni WHERE voce=?", vid):
            mz = q("SELECT inizio, fine, tipo, correzione, affidabilita FROM menzioni WHERE annotazione=? "
                   "ORDER BY inizio", aid)
            v_out.append("*Annotazione*: " + annota(at, mz) + "\n")
        nc = [t for (t,) in q("SELECT testo_esatto FROM non_classificati WHERE voce=? ORDER BY sede, inizio", vid)]
        if nc:
            v_out.append("*Non classificati*: " + ", ".join(nc) + "\n")
    OUT_VOCI.write_text("\n".join(v_out) + "\n", encoding="utf-8")
    print(f"Report scritti: {OUT}, {OUT_VOCI}")


if __name__ == "__main__":
    main()
