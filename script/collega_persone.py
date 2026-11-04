#!/usr/bin/env python3
"""Fase 5, persone: collegamento delle entità di persona a Wikidata (e, tramite
Wikidata, a VIAF, SBN e Dizionario Biografico degli Italiani).

Per ogni entità di persona con almeno un nome per intero (le sole iniziali non
sono confrontabili):

1. forme di ricerca: «Nome Cognome» e, per i cognomi di famiglia nobile o di
   luogo, «Nome di Cognome», «Nome da Cognome»; per papi e sovrani «papa X»;
2. su Wikidata: esseri umani (Q5) con quell'etichetta o quell'alias italiano,
   interrogati a blocchi via SPARQL; si leggono anni di nascita e di morte,
   luoghi di nascita e di morte, descrizione breve, numero di voci di Wikipedia
   e gli identificativi VIAF (P214), SBN (P396), DBI (P1986);
3. punteggio di ogni candidato:
   +2 se è nato o morto in Friuli o in Veneto;
   +1 se gli anni citati nelle voci della persona cadono nella sua vita;
   −3 se è nato dopo l'ultimo anno citato nelle sue voci;
   a parità, conta il numero di voci di Wikipedia;
4. scelta: un solo candidato plausibile → alta (o media se nulla lo lega al
   Friuli o alle date); più candidati → media con alternative.

Le date e i luoghi servono solo a scegliere: non si salvano (regola: niente
biografie). Si salvano identificativo, URL, forma autorizzata e data.

Scrive in `identificatori` (fonti Wikidata, VIAF, SBN, DBI) per le persone e il
report report/fase_5_persone.md.

Uso: python3 script/collega_persone.py
"""

import csv
import io
import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalizza import normalizza  # noqa: E402
from collega_luoghi import sparql, valore  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
DB = RADICE / "dati" / "inventario.sqlite"
ESTERNI = RADICE / "dati" / "esterni"
CACHE = ESTERNI / "wikidata_persone.json"
OUT = RADICE / "report" / "fase_5_persone.md"
OGGI = date.today().isoformat()
RX_ANNO = re.compile(r"\b(1[0-9]{3})\b")
URL = {"Wikidata": "https://www.wikidata.org/wiki/{}", "VIAF": "https://viaf.org/viaf/{}",
       "SBN": "https://opac.sbn.it/nome/{}", "DBI": "https://www.treccani.it/enciclopedia/{}_(Dizionario-Biografico)"}


def salva(cache):
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def luoghi_regionali():
    """Nomi dei comuni del Friuli-Venezia Giulia e del Veneto (ISTAT) e delle entità di luogo regionali."""
    testo = (ESTERNI / "comuni_istat.csv").read_bytes().decode("latin-1")
    righe = list(csv.reader(io.StringIO(testo), delimiter=";"))
    h = righe[0]
    i_den, i_reg = h.index("Denominazione in italiano"), h.index("Denominazione Regione")
    return {r[i_den] for r in righe[1:] if len(r) > i_reg and r[i_reg] in ("Friuli-Venezia Giulia", "Veneto")}


def forme_di_ricerca(intestazione):
    """«Florio, Daniele» → ["Daniele Florio", "Daniele di Florio", …]."""
    if ", " not in intestazione:
        forme = [intestazione]
        if re.search(r"\b[IVXL]+$", intestazione):
            forme.append("papa " + intestazione)
        return forme
    cognome, nomi = intestazione.split(", ", 1)
    if all(re.fullmatch(r"\S\.?", x) or x.endswith(".") for x in nomi.split()):
        return []                                    # sole iniziali
    alternative = [nomi]
    if " o " in nomi:                                # «Giacomo o Jacopo»
        alternative = [n.strip() for n in nomi.split(" o ")]
    forme = []
    for n in alternative:
        forme.append(f"{n} {cognome}")
        m = re.match(r"(?:di|de|da|d')\s*(.+)", cognome)
        if m:
            forme.append(f"{n} {m.group(1)}")
        elif not cognome[:1].islower():
            forme += [f"{n} di {cognome}", f"{n} da {cognome}"]
    return forme


def cerca(forme, cache):
    mancanti = sorted({f for f in forme if f not in cache["forme"]})
    for i in range(0, len(mancanti), 40):
        blocco = mancanti[i:i + 40]
        valori = " ".join(json.dumps(f, ensure_ascii=False) + "@it" for f in blocco)
        q = f"""SELECT ?l ?p ?sl ?nasc ?morte ?desc ?viaf ?sbn ?dbi ?lnasc ?lmorte ?lab WHERE {{
  VALUES ?l {{ {valori} }}
  {{ ?p rdfs:label ?l }} UNION {{ ?p skos:altLabel ?l }}
  ?p wdt:P31 wd:Q5 ; wikibase:sitelinks ?sl .
  OPTIONAL {{ ?p rdfs:label ?lab FILTER(lang(?lab) = "it") }}
  OPTIONAL {{ ?p wdt:P569 ?n }} BIND(YEAR(?n) AS ?nasc)
  OPTIONAL {{ ?p wdt:P570 ?m }} BIND(YEAR(?m) AS ?morte)
  OPTIONAL {{ ?p schema:description ?desc FILTER(lang(?desc) = "it") }}
  OPTIONAL {{ ?p wdt:P214 ?viaf }}
  OPTIONAL {{ ?p wdt:P396 ?sbn }}
  OPTIONAL {{ ?p wdt:P1986 ?dbi }}
  OPTIONAL {{ ?p wdt:P19 ?ln . ?ln rdfs:label ?lnasc FILTER(lang(?lnasc) = "it") }}
  OPTIONAL {{ ?p wdt:P20 ?lm . ?lm rdfs:label ?lmorte FILTER(lang(?lmorte) = "it") }}
}}"""
        for f in blocco:
            cache["forme"][f] = []
        for b in sparql(q):
            f = valore(b, "l")
            qid = valore(b, "p").rsplit("/", 1)[1]
            c = next((x for x in cache["forme"][f] if x["qid"] == qid), None)
            if c is None:
                c = {"qid": qid, "sl": int(valore(b, "sl") or 0), "etichetta": valore(b, "lab"),
                     "nasc": valore(b, "nasc"), "morte": valore(b, "morte"), "desc": valore(b, "desc"),
                     "viaf": valore(b, "viaf"), "sbn": valore(b, "sbn"), "dbi": valore(b, "dbi"), "luoghi": []}
                cache["forme"][f].append(c)
            for k in ("lnasc", "lmorte"):
                if valore(b, k) and valore(b, k) not in c["luoghi"]:
                    c["luoghi"].append(valore(b, k))
        salva(cache)
        print(f"  {min(i + 40, len(mancanti))}/{len(mancanti)}", file=sys.stderr)
        time.sleep(1)


def anno(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def punteggio(c, anni, regionali):
    p, motivi = 0, []
    if any(l in regionali for l in c["luoghi"]):
        p += 2
        motivi.append("nato o morto in Friuli/Veneto")
    n, m = anno(c["nasc"]), anno(c["morte"])
    if anni and n:
        if n > max(anni) + 5:
            p -= 3
            motivi.append(f"nato dopo le date delle voci ({max(anni)})")
        elif any(n + 10 <= a <= (m or n + 90) + 5 for a in anni):
            p += 1
            motivi.append("date compatibili")
    return p, motivi


def main():
    con = sqlite3.connect(DB)
    for c_, t in {"stato": "TEXT", "affidabilita": "TEXT", "nota": "TEXT"}.items():
        if c_ not in {r[1] for r in con.execute("PRAGMA table_info(identificatori)")}:
            con.execute(f"ALTER TABLE identificatori ADD COLUMN {c_} {t}")
    con.execute("DELETE FROM identificatori WHERE entita IN (SELECT id FROM entita WHERE tipo='persona')")
    regionali = luoghi_regionali() | {n for (n,) in con.execute(
        "SELECT e.forma_intestazione FROM entita e JOIN identificatori i ON i.entita=e.id "
        "WHERE e.tipo='luogo' AND i.forma_autorizzata IS NOT NULL")}
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {"forme": {}}
    entita = con.execute("SELECT id, forma_intestazione, nota FROM entita WHERE tipo='persona'").fetchall()
    # anni citati nelle voci in cui compare ogni entità
    anni = defaultdict(set)
    for eid, testo in con.execute("SELECT DISTINCT m.entita, v.testo FROM menzioni m JOIN voci v ON v.id=m.voce "
                                  "WHERE m.entita IN (SELECT id FROM entita WHERE tipo='persona')"):
        anni[eid] |= {int(a) for a in RX_ANNO.findall(testo or "") if 1000 <= int(a) <= 1999}
    forme = {eid: forme_di_ricerca(intest) for eid, intest, _ in entita}
    print(f"Ricerca su Wikidata di {sum(len(f) for f in forme.values())} forme…", file=sys.stderr)
    cerca([f for ff in forme.values() for f in ff], cache)

    risultati = {}
    for eid, intest, nota_e in entita:
        cand = {}
        for f in forme[eid]:
            for c in cache["forme"].get(f, []):
                cand[c["qid"]] = c
        if not cand:
            risultati[eid] = (intest, None, None, [], [])
            continue
        valutati = sorted(((*punteggio(c, anni[eid], regionali), c) for c in cand.values()),
                          key=lambda x: (x[0], x[2]["sl"]), reverse=True)
        plausibili = [v for v in valutati if v[0] >= 0]
        if not plausibili:
            risultati[eid] = (intest, None, "bassa", valutati, [])
            continue
        top = plausibili[0]
        if len(plausibili) == 1 or top[0] >= plausibili[1][0] + 2:
            aff = "alta" if (top[0] > 0 or top[2]["sl"] >= 10) else "media"
        else:
            aff = "media"
        if nota_e and "omonimi" in nota_e and aff == "alta":
            aff = "media"
        risultati[eid] = (intest, top, aff, valutati, top[1])

    for eid, (intest, top, aff, valutati, motivi) in risultati.items():
        if not top:
            continue
        c = top[2]
        nota = "; ".join(motivi) or None
        forma = c["etichetta"] or intest
        righe = [("Wikidata", c["qid"])] + [(f, c[k]) for f, k in (("VIAF", "viaf"), ("SBN", "sbn"), ("DBI", "dbi"))
                                             if c.get(k)]
        for fonte, codice in righe:
            con.execute("INSERT INTO identificatori (entita, fonte, codice, url, forma_autorizzata, data_verifica, "
                        "stato, affidabilita, nota) VALUES (?,?,?,?,?,?,?,?,?)",
                        (eid, fonte, codice, URL[fonte].format(codice), forma, OGGI, "proposto", aff, nota))
    con.commit()
    report(con, risultati, anni)
    con.close()


def report(con, risultati, anni):
    voci = defaultdict(list)
    for eid, num in con.execute("SELECT DISTINCT m.entita, v.numero FROM menzioni m JOIN voci v ON v.id=m.voce "
                                "WHERE m.entita IN (SELECT id FROM entita WHERE tipo='persona') ORDER BY v.id"):
        if len(voci[eid]) < 4:
            voci[eid].append(num)
    per = defaultdict(list)
    for eid, x in risultati.items():
        per[x[2] or ("nessuna" if not x[3] else "bassa")].append((eid,) + x)
    r = []
    w = r.append
    w("# Fase 5 — Persone: collegamento a Wikidata (VIAF, SBN, DBI)\n")
    w(f"Verifica del {OGGI}. Collegamenti **proposti**. Date, luoghi e descrizioni di Wikidata compaiono solo qui, "
      "per scegliere; nel database restano identificativo, URL e forma autorizzata.\n")
    w("| Affidabilità | Persone |\n|---|---|")
    for k in ("alta", "media", "bassa", "nessuna"):
        w(f"| {k} | {len(per[k])} |")
    w("")

    def descr(c):
        vita = f"{c['nasc'] or '?'}–{c['morte'] or '?'}"
        return (f"[{c['qid']}](https://www.wikidata.org/wiki/{c['qid']}) {c['etichetta'] or ''} ({vita})"
                + (f": _{c['desc']}_" if c.get("desc") else "")
                + (f" — {', '.join(c['luoghi'][:2])}" if c["luoghi"] else ""))

    def riga(x, alternative=True):
        eid, intest, top, aff, valutati, motivi = x
        anni_v = sorted(anni[eid])
        s = f"- **{intest}** (voci {', '.join(voci[eid])}; anni {anni_v[0] if anni_v else '?'}–{anni_v[-1] if anni_v else '?'})"
        if top:
            s += " → " + descr(top[2]) + (f" — {'; '.join(motivi)}" if motivi else "")
        if alternative:
            altri = [v for v in valutati if not top or v[2]["qid"] != top[2]["qid"]][:4]
            if altri:
                s += "\n  - altri: " + "; ".join(descr(v[2]) + f" [{v[0]}]" for v in altri)
        return s

    w("## 1. Affidabilità media: da verificare\n")
    for x in sorted(per["media"], key=lambda x: x[1]):
        w(riga(x))
    w("\n## 2. Candidati scartati (date incompatibili)\n")
    for x in sorted(per["bassa"], key=lambda x: x[1]):
        w(riga(x))
    w("\n## 3. Affidabilità alta\n")
    for x in sorted(per["alta"], key=lambda x: x[1]):
        w(riga(x, alternative=False))
    w(f"\n## 4. Nessun candidato su Wikidata: {len(per['nessuna'])} persone\n")
    w("Elenco completo nella tabella `entita` (persone senza righe in `identificatori`).\n")
    OUT.write_text("\n".join(r) + "\n", encoding="utf-8")
    print(f"Report scritto in {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
