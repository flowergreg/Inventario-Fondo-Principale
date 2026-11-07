#!/usr/bin/env python3
"""Fase 5, ricadute sul lessico e sulle varianti dei collegamenti ad affidabilità alta.

1. Varianti di ricerca dalle fonti: l'etichetta italiana e gli alias (it, la, fur) di
   Wikidata dei luoghi e delle persone collegati diventano varianti con origine
   `fonte_esterna` (riferimento «Wikidata Qxxx»): chi cerca «Utinum», «Hieronymus»,
   «Dolfin» trova anche le forme del testo.
2. Nomi ambigui: un'entità di persona con un nome «Giacomo o Jacopo» prende il nome
   della persona collegata («Pirona, Jacopo»).
3. Lessico: i cognomi «da verificare» che compaiono come cognome di persone collegate
   diventano «normali» (origine: Wikidata); se Wikidata li scrive in altro modo
   (Delfino → Dolfin) la grafia di Wikidata è registrata come proposta per il
   curatore: la forma del testo non cambia, e la persona collegata è comunque
   trovabile con la grafia di Wikidata, che è tra le sue varianti.

Va eseguito dopo lessico.py, entita.py, collega_luoghi.py e collega_persone.py.
Scrive report/fase_5_lessico.md.

Uso: python3 script/arricchisci.py
"""

import csv
import difflib
import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalizza import normalizza  # noqa: E402
from collega_luoghi import sparql, valore  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
DB = RADICE / "dati" / "inventario.sqlite"
CACHE = RADICE / "dati" / "esterni" / "wikidata_alias.json"
OUT = RADICE / "report" / "fase_5_lessico.md"
PARTICELLE = {"di", "de", "da", "del", "della", "dei", "degli", "d", "von", "van", "le", "la"}


def alias(qids, cache):
    mancanti = [q for q in qids if q not in cache]
    for i in range(0, len(mancanti), 100):
        blocco = mancanti[i:i + 100]
        q = f"""SELECT ?p ?lab ?a WHERE {{
  VALUES ?p {{ {" ".join("wd:" + x for x in blocco)} }}
  OPTIONAL {{ ?p rdfs:label ?lab FILTER(lang(?lab) = "it") }}
  OPTIONAL {{ ?p skos:altLabel ?a FILTER(lang(?a) IN ("it", "la", "fur")) }}
}}"""
        for x in blocco:
            cache[x] = {"etichetta": None, "alias": []}
        for b in sparql(q):
            d = cache[valore(b, "p").rsplit("/", 1)[1]]
            d["etichetta"] = d["etichetta"] or valore(b, "lab")
            if "a" in b:
                v = [b["a"]["value"], b["a"].get("xml:lang")]
                if v not in d["alias"]:
                    d["alias"].append(v)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        print(f"  alias: {min(i + 100, len(mancanti))}/{len(mancanti)}", file=sys.stderr)
        time.sleep(1)


def main():
    con = sqlite3.connect(DB)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    collegati = con.execute(
        "SELECT e.id, e.tipo, e.forma_intestazione, e.chiave, i.codice FROM entita e "
        "JOIN identificatori i ON i.entita=e.id WHERE i.fonte='Wikidata' AND i.affidabilita='alta' "
        "AND e.tipo IN ('luogo', 'persona')").fetchall()
    alias(sorted({r[4] for r in collegati}), cache)
    con.execute("DELETE FROM varianti WHERE origine='fonte_esterna' AND riferimento LIKE 'Wikidata Q%'")

    # 1. varianti dalle fonti
    nuove = defaultdict(int)
    for eid, tipo, intest, chiave, qid in collegati:
        d = cache.get(qid, {})
        esistenti = {normalizza(f) for (f,) in con.execute("SELECT forma FROM varianti WHERE entita=?", (eid,))}
        forme = ([(d["etichetta"], "it")] if d.get("etichetta") else []) + [tuple(a) for a in d.get("alias", [])]
        for forma, lingua in forme:
            n = normalizza(forma)
            if not n or n in esistenti or len(n.replace(" ", "")) < 3 or re.fullmatch(r"[A-Z]{1,3}", forma):
                continue                          # sigle («RM») e forme troppo brevi
            esistenti.add(n)
            con.execute("INSERT INTO varianti (entita, forma, forma_normalizzata, origine, riferimento) "
                        "VALUES (?,?,?,?,?)", (eid, forma, n, "fonte_esterna", f"Wikidata {qid} ({lingua})"))
            nuove[tipo] += 1

    # 2. nomi ambigui sciolti dalla persona collegata
    sciolti = []
    for eid, tipo, intest, chiave, qid in collegati:
        if tipo != "persona" or " o " not in intest:
            continue
        etichetta = cache.get(qid, {}).get("etichetta") or ""
        cognome, nomi = intest.split(", ", 1)
        scelto = next((n for n in nomi.split(" o ") if re.search(rf"\b{re.escape(n.strip())}\b", etichetta)), None)
        if scelto:
            nuova = f"{cognome}, {scelto.strip()}"
            con.execute("UPDATE entita SET forma_intestazione=?, nota=coalesce(nota || '; ', '') || ? WHERE id=?",
                        (nuova, f"nome sciolto con Wikidata ({etichetta})", eid))
            sciolti.append((intest, nuova, etichetta))

    # 3. cognomi del lessico confermati dalle persone collegate
    da_verificare = {f: (s, n) for f, s, n in con.execute(
        "SELECT forma, stato, forma_normalizzata FROM lessico WHERE parte='cognome'")}
    confermati, grafie = {}, {}
    luoghi = {n for (n,) in con.execute("SELECT forma_intestazione FROM entita WHERE tipo='luogo'")}
    for eid, tipo, intest, chiave, qid in collegati:
        if tipo != "persona" or ", " not in intest:
            continue
        etichetta = cache.get(qid, {}).get("etichetta") or ""
        nomi_n = set(chiave.split(" / ")[0].replace("|", " ").split())
        wd_cogn = [w for w in re.findall(r"[^\W\d_][\w'’]*", etichetta)
                   if normalizza(w) not in nomi_n and w.lower() not in PARTICELLE and not re.fullmatch(r"[IVXL]+", w)]
        testo_cogn = [w for w in re.findall(r"[^\W\d_][\w'’]*", intest.split(", ")[0]) if w.lower() not in PARTICELLE]
        # forme del cognome nel testo: tutte le varianti di testo che hanno lo stesso cognome normalizzato
        forme_testo = set(testo_cogn)
        for (f,) in con.execute("SELECT forma FROM varianti WHERE entita=? AND origine='testo'", (eid,)):
            for w in re.findall(r"[^\W\d_][\w'’]*", f):
                if normalizza(w) in {normalizza(x) for x in testo_cogn}:
                    forme_testo.add(w)
        if len(wd_cogn) != len(testo_cogn) or not wd_cogn:
            continue
        for t, wd in zip(testo_cogn, wd_cogn):
            for forma in forme_testo:
                if normalizza(forma) != normalizza(t) or forma not in da_verificare:
                    continue
                if normalizza(wd) == normalizza(forma):
                    confermati[forma] = (None, qid, etichetta)
                elif len(wd) > 2 and wd not in luoghi and \
                        difflib.SequenceMatcher(None, normalizza(wd), normalizza(forma)).ratio() >= 0.7:
                    # solo varianti grafiche (Delfino/Dolfin, Bellone/Belloni), non cognomi diversi
                    # (Braschi/Falconieri) né predicati di luogo (Mattiussi/da Pordenone, Paolo Veneto/da Venezia)
                    grafie[forma] = (wd, qid, etichetta)
    for forma, (wd, qid, etichetta) in confermati.items():
        con.execute("UPDATE lessico SET stato='normale', origine=? WHERE forma=? AND parte='cognome' "
                    "AND stato IN ('da_verificare', 'da_normalizzare', 'doppia_lettura') AND forma_normalizzata IS NULL",
                    (f"Wikidata: {etichetta} ({qid})", forma))
    for forma, (wd, qid, etichetta) in grafie.items():
        if forma in confermati:
            continue
        # proposta, non sostituzione: il lessico vale per tutte le menzioni della parola, e una sola
        # persona collegata non basta a cambiare la forma di riferimento di una famiglia
        con.execute("UPDATE lessico SET origine=? WHERE forma=? AND parte='cognome' AND forma_normalizzata IS NULL",
                    (f"proposta: Wikidata scrive «{wd}» ({etichetta}, {qid})", forma))
    fonti_curatore(con)
    con.commit()
    report(con, nuove, sciolti, confermati, grafie)
    con.close()


def report(con, nuove, sciolti, confermati, grafie):
    r = []
    w = r.append
    w("# Fase 5 — Ricadute sul lessico e sulle varianti\n")
    w("Solo i collegamenti ad affidabilità **alta** (luoghi confermati dal curatore, persone riviste nel contesto).\n")
    w("## 1. Varianti di ricerca dalle fonti\n")
    w(f"Etichette e alias di Wikidata (it, la, fur) aggiunti come varianti `fonte_esterna`: "
      f"{nuove.get('luogo', 0)} per i luoghi, {nuove.get('persona', 0)} per le persone. Esempi:\n")
    for tipo in ("luogo", "persona"):
        righe = con.execute(
            "SELECT e.forma_intestazione, group_concat(v.forma, '; ') FROM varianti v JOIN entita e ON e.id=v.entita "
            "WHERE v.origine='fonte_esterna' AND v.riferimento LIKE 'Wikidata Q%' AND e.tipo=? "
            "GROUP BY e.id ORDER BY count(*) DESC LIMIT 25", (tipo,)).fetchall()
        for intest, forme in righe:
            w(f"- **{intest}**: {forme[:300]}")
        w("")
    w("## 2. Nomi ambigui sciolti con la persona collegata\n")
    for a, b, et in sciolti:
        w(f"- {a} → **{b}** (Wikidata: {et})")
    if not sciolti:
        w("_Nessuno._")
    w("\n## 3. Cognomi con una grafia diversa in Wikidata (proposte)\n")
    w("Proposte per il curatore: la forma del testo resta quella di riferimento nel lessico; la grafia di Wikidata "
      "è già una variante della persona collegata. Se la grafia vale per tutta la famiglia, va aggiunta a "
      "normalizzazioni_curatore.tsv.\n")
    for forma, (wd, qid, et) in sorted(grafie.items()):
        if forma not in confermati:
            w(f"- {forma} → **{wd}** ({et}, [{qid}](https://www.wikidata.org/wiki/{qid}))")
    w(f"\n## 4. Cognomi confermati da Wikidata\n\n{len(confermati)} cognomi passano da «da verificare» a «normale»: "
      + ", ".join(sorted(confermati)) + "\n")
    OUT.write_text("\n".join(r) + "\n", encoding="utf-8")
    print(f"Report scritto in {OUT} ({OUT.stat().st_size // 1024} KB)")


def fonti_curatore(con):
    """Fonti indicate dal curatore per le forme di riferimento (dati/liste/fonti_curatore.tsv): una scheda
    del Dizionario Biografico dei Friulani spiega perché alla forma del testo corrisponde una forma
    diversa (Geronimiani → Agostino de Gerolami), anche dove Wikidata non c'è. Si conservano solo
    fonte, URL e la forma della scheda, mai il testo della biografia."""
    def chiave_i(x):
        return frozenset(w for w in normalizza(x.replace(",", " ")).split()
                         if w not in {"di", "de", "da", "d", "del", "della", "dei", "von", "van"})
    indice = {}
    for eid, tipo, intest, alias in con.execute("SELECT id, tipo, forma_intestazione, alias FROM entita"):
        for v in [intest] + [a for a in (alias or "").split(" | ") if a]:
            indice.setdefault((tipo, chiave_i(v)), eid)
    con.execute("DELETE FROM identificatori WHERE fonte IN ('DBF', 'curatore')")
    mancanti = []
    righe = list(csv.DictReader(open(RADICE / "dati" / "liste" / "fonti_curatore.tsv", encoding="utf-8"), delimiter="\t"))
    # collegamenti al Dizionario decisi nella revisione (fase 6): più schede per una forma quando
    # l'identità è incerta (omonimi): il lettore sceglie da sé
    dbf = RADICE / "dati" / "liste" / "dbf_collegamenti.tsv"
    if dbf.exists():
        righe += [dict(tipo="persona", fonte="Dizionario Biografico dei Friulani", url=r["url"],
                       nota=f"{r['scheda']} ({r['date']})" if r["date"] else r["scheda"], intestazione=r["intestazione"],
                       origine=r["nota"])
                  for r in csv.DictReader(open(dbf, encoding="utf-8"), delimiter="\t")]
    # forma e date della scheda dall'indice del Dizionario (dati/esterni/dbf_indice.json): si mostrano sempre
    idx_dbf = RADICE / "dati" / "esterni" / "dbf_indice.json"
    schede = {d["url"].rstrip("/"): d for d in json.loads(idx_dbf.read_text(encoding="utf-8"))} if idx_dbf.exists() else {}
    visti = set()
    for r in righe:
        d = schede.get(r["url"].rstrip("/"))
        if d:
            r["nota"] = f"{d['cognome']} {d['nome']}".strip() + (f" ({d['date']})" if d["date"] else "")
        eid = indice.get((r["tipo"], chiave_i(r["intestazione"])))
        if not eid:
            mancanti.append(r["intestazione"])
            continue
        if (eid, r["url"].rstrip("/")) in visti:
            continue
        visti.add((eid, r["url"].rstrip("/")))
        # fonte «DBF» per il Dizionario; «curatore» per altre pagine indicate dal curatore (nome nella nota)
        fonte = "DBF" if r["fonte"].startswith("Dizionario Biografico") else "curatore"
        con.execute("INSERT INTO identificatori (entita, fonte, codice, url, forma_autorizzata, data_verifica, stato, "
                    "affidabilita, nota) VALUES (?,?,?,?,?,date('now'),'validato','alta',?)",
                    (eid, fonte, r["url"].rstrip("/").rsplit("/", 1)[1], r["url"], r["nota"] or None,
                     r["fonte"] if fonte == "curatore" else f"{r['fonte']} ({r.get('origine') or 'curatore'})"))
    if mancanti:
        print(f"  fonti del curatore non applicate (intestazione non trovata): {'; '.join(mancanti)}", file=sys.stderr)
    # «Altri nomi» delle schede collegate (dati/esterni/dbf_altri_nomi.json): varianti di ricerca della forma
    # di riferimento, come le etichette di Wikidata (Geronimiano, Germiniano per Agostino de Gerolami)
    altri = RADICE / "dati" / "esterni" / "dbf_altri_nomi.json"
    altri = json.loads(altri.read_text(encoding="utf-8")) if altri.exists() else {}
    con.execute("DELETE FROM varianti WHERE origine='fonte_esterna' AND riferimento LIKE 'Dizionario Biografico%'")
    # forme diverse collegate alla stessa scheda (Haedus, Petrus / Edo, Pietro): ognuna è variante di
    # ricerca dell'altra; solo per le forme con una sola scheda (non per gli omonimi incerti)
    uniche = {eid for eid, k in con.execute("SELECT entita, COUNT(*) FROM identificatori WHERE fonte='DBF' "
                                             "GROUP BY entita") if k == 1}
    per_url = defaultdict(set)
    for eid, url in con.execute("SELECT entita, url FROM identificatori WHERE fonte='DBF'"):
        if eid in uniche:
            per_url[url.rstrip("/")].add(eid)
    for url, eids in per_url.items():
        if len(eids) < 2:
            continue
        forme = {eid: {f for (f,) in con.execute("SELECT forma FROM varianti WHERE entita=? AND origine='testo'", (eid,))}
                 for eid in eids}
        for eid in eids:
            esistenti = {normalizza(f) for (f,) in con.execute("SELECT forma FROM varianti WHERE entita=?", (eid,))}
            for altro in eids - {eid}:
                for forma in sorted(forme[altro]):
                    if normalizza(forma) not in esistenti:
                        esistenti.add(normalizza(forma))
                        con.execute("INSERT INTO varianti (entita, forma, forma_normalizzata, origine, riferimento) "
                                    "VALUES (?,?,?,?,?)", (eid, forma, normalizza(forma), "fonte_esterna",
                                                           "Dizionario Biografico dei Friulani, stessa scheda"))
    # la forma della scheda è variante di ricerca («Altan Enrico» per «Altani, Enrico»), senza date ed epiteti
    for eid, forma in con.execute("SELECT entita, forma_autorizzata FROM identificatori WHERE fonte='DBF'").fetchall():
        forma = re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", " ", forma or "")).strip()
        esistenti = {normalizza(f) for (f,) in con.execute("SELECT forma FROM varianti WHERE entita=?", (eid,))}
        if len(forma) >= 3 and normalizza(forma) not in esistenti:
            con.execute("INSERT INTO varianti (entita, forma, forma_normalizzata, origine, riferimento) "
                        "VALUES (?,?,?,?,?)", (eid, forma, normalizza(forma), "fonte_esterna",
                                               "Dizionario Biografico dei Friulani, scheda"))
    n = 0
    for eid, url in con.execute("SELECT entita, url FROM identificatori WHERE fonte='DBF'").fetchall():
        esistenti = {normalizza(f) for (f,) in con.execute("SELECT forma FROM varianti WHERE entita=?", (eid,))}
        for forma in re.split(r"\s*[,;/]\s*", altri.get(url.rstrip("/"), "") or altri.get(url, "")):
            forma = forma.strip(" .")
            if len(forma.replace(" ", "")) < 3 or normalizza(forma) in esistenti:
                continue
            esistenti.add(normalizza(forma))
            con.execute("INSERT INTO varianti (entita, forma, forma_normalizzata, origine, riferimento) "
                        "VALUES (?,?,?,?,?)", (eid, forma, normalizza(forma), "fonte_esterna",
                                               "Dizionario Biografico dei Friulani, altri nomi"))
            n += 1
    print(f"  altri nomi dal Dizionario Biografico dei Friulani: {n} varianti", file=sys.stderr)


if __name__ == "__main__":
    main()
