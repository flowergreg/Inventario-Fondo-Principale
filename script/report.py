#!/usr/bin/env python3
"""Report di verifica delle fasi 1 (parsing) e 2 (segmentazione).

Legge dati/inventario.sqlite e i file di diagnostica prodotti da parser.py e
segmenta.py; scrive report/report_fasi_1_2.md.

Uso: python3 script/report.py [seme_campione]
"""

import collections
import json
import random
import sqlite3
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
DB = RADICE / "dati" / "inventario.sqlite"
DIAG_PARSER = RADICE / "dati" / "diagnostica_parser.json"
DIAG_SEGMENTA = RADICE / "dati" / "diagnostica_segmenta.json"
USCITA = RADICE / "report" / "report_fasi_1_2.md"
ULTIMO_NUMERO = 4519


def intervalli(numeri):
    """[1,2,3,7,8] → «1–3, 7–8»."""
    numeri = sorted(numeri)
    pezzi, inizio, prec = [], None, None
    for n in numeri:
        if inizio is None:
            inizio = prec = n
        elif n == prec + 1:
            prec = n
        else:
            pezzi.append(f"{inizio}–{prec}" if prec > inizio else str(inizio))
            inizio = prec = n
    if inizio is not None:
        pezzi.append(f"{inizio}–{prec}" if prec > inizio else str(inizio))
    return ", ".join(pezzi)


def tronca(testo, n):
    testo = testo or ""
    return testo if len(testo) <= n else testo[:n] + f" […+{len(testo) - n} caratteri]"


def main():
    seme = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    dp = json.loads(DIAG_PARSER.read_text(encoding="utf-8"))
    ds = json.loads(DIAG_SEGMENTA.read_text(encoding="utf-8"))
    voci = con.execute("SELECT * FROM voci ORDER BY id").fetchall()
    r = []
    w = r.append

    w("# Report fasi 1 e 2 — Inventario del Fondo Principale\n")
    w("Generato da `script/report.py` su `dati/inventario.sqlite`. "
      "Sorgente: `sorgenti/Inventario_Fondo_Principale.docx` (non modificata).\n")

    # --- Riepilogo -----------------------------------------------------------
    w("## 1. Riepilogo\n")
    n_ann = con.execute("SELECT count(*) FROM annotazioni").fetchone()[0]
    n_seg = con.execute("SELECT count(*) FROM segmenti").fetchone()[0]
    n_vseg = con.execute("SELECT count(DISTINCT voce) FROM segmenti WHERE tipo != 'voce_intera'").fetchone()[0]
    senza_coda = [v for v in voci if v["coda"] is None]
    w("| Dato | Valore |\n|---|---|")
    w(f"| Paragrafi del documento | {dp['paragrafi_totali']} |")
    w(f"| Paragrafi preliminari saltati (prima della voce 1) | {len(dp['preliminari'])} |")
    w(f"| **Voci** | **{len(voci)}** |")
    w(f"| Intestazioni di sezione | {len(dp['intestazioni'])} |")
    w(f"| Annotazioni | {n_ann} |")
    w(f"| Voci con coda / senza coda | {len(voci) - len(senza_coda)} / {len(senza_coda)} |")
    w(f"| Voci con residuo | {sum(1 for v in voci if v['residuo'])} |")
    w(f"| **Voci segmentate** (con almeno un riferimento) | **{n_vseg}** |")
    w(f"| **Segmenti** (comprese le voci intere) | **{n_seg}** |")
    w("")

    w("### Paragrafi preliminari saltati\n")
    for i, t in dp["preliminari"]:
        w(f"- par. {i}: {tronca(t, 90)}")
    w("")

    w("### Intestazioni di sezione\n")
    w("| Par. | Intestazione | Dopo la voce |\n|---|---|---|")
    for i, t, dopo in dp["intestazioni"]:
        w(f"| {i} | {t} | {dopo} |")
    w("")
    w("Sezioni con ambito (aperte e chiuse da una riga «Fine …»); le intestazioni senza "
      "chiusura (es. «Letteratura storica Friulana») non si propagano alle voci.\n")
    w("| Sezione | Voci | Da | A |\n|---|---|---|---|")
    for sez, n, da, a in con.execute(
            "SELECT sezione, count(*), min(numero_base), max(numero_base) FROM voci "
            "WHERE sezione IS NOT NULL GROUP BY 1 ORDER BY 3"):
        w(f"| {sez} | {n} | {da} | {a} |")
    w("")

    # --- Numeri ---------------------------------------------------------------
    w("## 2. Numeri di voce\n")
    w("### Numeri anomali\n")
    per_tipo = collections.defaultdict(list)
    for v in voci:
        if v["tipo_numero"] != "semplice":
            per_tipo[v["tipo_numero"]].append(v["numero_originale"])
    for tipo, lista in sorted(per_tipo.items()):
        w(f"- **{tipo}** ({len(lista)}): " + ", ".join(f"`{x}`" for x in lista))
    w("")

    coperti = set()
    for v in voci:
        coperti.add(v["numero_base"])
        if v["numeri_compresi"]:
            coperti.update(int(x) for x in v["numeri_compresi"].split(","))
    mancanti = [n for n in range(1, ULTIMO_NUMERO + 1) if n not in coperti]
    w("### Numeri mancanti\n")
    w(f"Numeri da 1 a {ULTIMO_NUMERO} senza voce (le voci fuse coprono entrambi i numeri): "
      f"**{len(mancanti)}** — {intervalli(mancanti) or 'nessuno'}\n")
    for n in mancanti:
        prec = [v for v in voci if v["numero_base"] < n][-1:]
        if prec:
            nota = con.execute(
                "SELECT testo FROM annotazioni WHERE voce=?", (prec[0]["id"],)).fetchall()
            if nota:
                w(f"- {n}: annotazioni della voce precedente ({prec[0]['numero_originale']}): "
                  + "; ".join(x[0] for x in nota))
    w("")

    w("### Numeri fuori sequenza\n")
    w("Voci il cui numero base è minore del precedente, o lo supera di più di uno.\n")
    w("| Voce precedente | Voce | Problema |\n|---|---|---|")
    prec = None
    for v in voci:
        if prec is not None:
            b, pb = v["numero_base"], prec["numero_base"]
            if prec["numeri_compresi"]:
                pb = max(int(x) for x in prec["numeri_compresi"].split(","))
            if b < pb:
                w(f"| {prec['numero_originale']} | {v['numero_originale']} | indietro |")
            elif b > pb + 1:
                w(f"| {prec['numero_originale']} | {v['numero_originale']} | salto di {b - pb - 1} |")
        prec = v
    w("")

    # --- Coda -------------------------------------------------------------------
    w("## 3. Riga di coda\n")
    w(f"Voci senza coda: **{len(senza_coda)}**. Numeri base (intervalli): "
      + intervalli({v["numero_base"] for v in senza_coda}) + "\n")
    forme = collections.Counter()
    for v in voci:
        if v["coda"]:
            for riga in v["coda"].split("\n"):
                forme["«Provenienza: …»" if riga.startswith("Provenienza") else
                      "«… · …»" if "·" in riga else "supporto solo"] += 1
    w("Forme di coda: " + ", ".join(f"{k} {n}" for k, n in forme.items()) + "\n")
    w("Campi della coda valorizzati: "
      + ", ".join(f"{c} {sum(1 for v in voci if v[c])}" for c in ("supporto", "volumi", "stato", "provenienza"))
      + "\n")
    w("### Code intermedie e multiple\n")
    w("La coda riguarda il testo che la precede; il testo che la segue resta testo della voce.\n")
    for num, avvisi in dp["avvisi"].items():
        w(f"- **{num}**: " + " / ".join(avvisi))
    w("")

    # --- Residui ----------------------------------------------------------------
    w("## 4. Residui\n")
    res = [v for v in voci if v["residuo"]]
    if not res:
        w("Nessun residuo.\n")
    for v in res:
        w(f"- **{v['numero_originale']}**: {v['residuo']}")
    w("")

    # --- Annotazioni -------------------------------------------------------------
    w("## 5. Annotazioni\n")
    w("| Sede | Tipo | Numero |\n|---|---|---|")
    for sede, tipo, n in con.execute(
            "SELECT sede, tipo, count(*) FROM annotazioni GROUP BY 1,2 ORDER BY 1,3 DESC"):
        w(f"| {sede} | {tipo} | {n} |")
    w("")
    w("### Annotazioni relative all'indice (non alle voci)\n")
    for par, etichetta, testo, dopo in dp["annotazioni_indice"]:
        w(f"- par. {par} (dopo la voce {dopo}): [{etichetta}: {testo}]")
    w("")
    w("### Da controllare\n")
    for num, par, et in dp["annotazioni_senza_grassetto"]:
        w(f"- {num} (par. {par}): etichetta «{et}» non in grassetto")
    for num, testo, sede in con.execute(
            "SELECT v.numero_originale, a.testo, a.sede FROM annotazioni a JOIN voci v ON v.id=a.voce "
            "WHERE a.testo NOT LIKE '«%'"):
        w(f"- {num} (sede {sede}): contenuto senza virgolette «»: {tronca(testo, 100)}")
    for num, in con.execute(
            "SELECT DISTINCT v.numero_originale FROM annotazioni a JOIN voci v ON v.id=a.voce "
            "WHERE a.testo_originale NOT LIKE '[%'"):
        w(f"- {num}: annotazione con etichetta fuori dalle quadre («Nota a margine: [«…»]»)")
    w("")

    # --- Segmentazione ------------------------------------------------------------
    w("## 6. Segmentazione\n")
    w("| Tipo di segmento | Numero |\n|---|---|")
    for tipo, n in con.execute("SELECT tipo, count(*) FROM segmenti GROUP BY 1 ORDER BY 2 DESC"):
        w(f"| {tipo} | {n} |")
    w("")
    w("Voci con più segmenti:\n")
    for num, n in con.execute(
            "SELECT v.numero_originale, count(*) FROM segmenti s JOIN voci v ON v.id=s.voce "
            "GROUP BY s.voce ORDER BY 2 DESC LIMIT 10"):
        w(f"- {num}: {n} segmenti")
    w("")
    w("### Segmentazioni dubbie\n")
    w("Criteri: segmento quasi vuoto (solo l'etichetta), preambolo lungo prima del primo "
      "riferimento (>600 caratteri), famiglie di riferimenti diverse nella stessa voce.\n")
    for num, dubbi in ds["dubbie"].items():
        w(f"- **{num}**: " + "; ".join(dubbi))
    w("")
    man = json.loads((RADICE / "dati" / "segmentazioni_manuali.json").read_text(encoding="utf-8"))
    w("### Segmentazioni manuali (dati/segmentazioni_manuali.json)\n")
    w(", ".join(k for k in man if not k.startswith("_")) + "\n")
    w("### Riferimenti candidati scartati\n")
    motivi = collections.Counter(m for lista in ds["scartati"].values() for _, m in lista)
    w("Riepilogo: " + ", ".join(f"{m} {n}" for m, n in motivi.most_common()) + "\n")
    for num, lista in ds["scartati"].items():
        w(f"- {num}: " + "; ".join(f"«{e}» ({m})" for e, m in lista))
    w("")

    # --- Campione -----------------------------------------------------------------
    def mostra(v):
        w(f"### {v['numero_originale']}\n")
        w(f"**Testo**\n\n> " + tronca(v["testo"], 1500).replace("\n", "\n>\n> ") + "\n")
        if v["coda"]:
            w(f"**Coda**: `{v['coda']}` → supporto: {v['supporto'] or '—'}; volumi: {v['volumi'] or '—'}; "
              f"stato: {v['stato'] or '—'}; provenienza: {v['provenienza'] or '—'}\n")
        else:
            w("**Coda**: —\n")
        ann = con.execute("SELECT tipo, testo FROM annotazioni WHERE voce=?", (v["id"],)).fetchall()
        if ann:
            w("**Annotazioni**: " + "; ".join(f"[{a['tipo']}] {a['testo']}" for a in ann) + "\n")
        w("**Segmenti**\n")
        for s in con.execute("SELECT * FROM segmenti WHERE voce=? ORDER BY ordine", (v["id"],)):
            etichetta = f"«{s['etichetta']}»" if s["etichetta"] else "(senza etichetta)"
            w(f"- {s['tipo']} {etichetta} [{s['inizio']}–{s['fine']}]: {tronca(s['testo'], 160)}")
        w("")

    w(f"## 7. Venti voci estratte a caso (seme {seme})\n")
    rnd = random.Random(seme)
    for v in sorted(rnd.sample(list(voci), 20), key=lambda x: x["id"]):
        mostra(v)
    segmentate = [v for v in voci if con.execute(
        "SELECT 1 FROM segmenti WHERE voce=? AND tipo='riferimento'", (v["id"],)).fetchone()]
    w(f"## 8. Venti voci segmentate estratte a caso (seme {seme + 1})\n")
    rnd = random.Random(seme + 1)
    for v in sorted(rnd.sample(segmentate, 20), key=lambda x: x["id"]):
        mostra(v)

    USCITA.parent.mkdir(parents=True, exist_ok=True)
    USCITA.write_text("\n".join(r) + "\n", encoding="utf-8")
    print(f"Report scritto in {USCITA}")


if __name__ == "__main__":
    main()
