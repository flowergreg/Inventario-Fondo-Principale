#!/usr/bin/env python3
"""Fase 5, luoghi: collegamento delle entità di luogo a GeoNames e Wikidata.

Per ogni entità di luogo (tabella `entita`, tipo «luogo»):

1. candidati locali da GeoNames (dati aperti già scaricati in dati/esterni/):
   IT.txt per l'Italia, cities5000.txt per l'estero; a parità di nome si
   preferiscono Friuli e Veneto, poi il resto d'Italia, poi l'estero, e i
   centri abitati rispetto alle altre località;
2. candidati da Wikidata: elementi con quell'etichetta italiana e con un
   identificativo GeoNames (P1566), interrogati a blocchi via SPARQL;
3. scelta e affidabilità:
   alta  — un solo candidato friulano o veneto, oppure un solo elemento
           Wikidata, oppure uno nettamente più noto degli altri;
   media — più candidati plausibili: si propone il migliore e si elencano
           gli altri nel report;
   bassa — corrispondenza solo in GeoNames fuori regione o lontana.

Si conservano soltanto forma autorizzata (italiana), identificativo, URL e
data di verifica (regola 7). Gli alias di Wikidata (it, la, fur) si salvano a
parte in `alias_esterni` e diventano varianti solo dopo la conferma del curatore.

Scrive le righe di `identificatori` per i luoghi (stato «proposto»), la tabella
`alias_esterni` e il report report/fase_5_luoghi.md.

Uso: python3 script/collega_luoghi.py
"""

import csv
import io
import json
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalizza import altre_intestazioni, normalizza, nota_senza_unioni  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
DB = RADICE / "dati" / "inventario.sqlite"
ESTERNI = RADICE / "dati" / "esterni"
CACHE = ESTERNI / "wikidata_luoghi.json"
OUT = RADICE / "report" / "fase_5_luoghi.md"
SPARQL = "https://query.wikidata.org/sparql"
AGENTE = "InventarioJoppi/0.1 (ricerca storica)"
OGGI = date.today().isoformat()
REGIONI = {"06": "Friuli-Venezia Giulia", "20": "Veneto"}

# priorità dei tipi di località GeoNames (codice di caratteristica)
PESO_TIPO = {"PPLC": 9, "PPLA": 8, "PPLA2": 7, "PPLA3": 6, "PPL": 5, "PPLA4": 5, "ADM1": 6, "ADM2": 5,
             "RGN": 5, "PCLI": 9, "ADM3": 3, "PPLL": 2, "PPLX": 2, "PPLF": 2, "PPLQ": 1}

SCHEMA = """
CREATE TABLE IF NOT EXISTS identificatori (
    entita INTEGER NOT NULL, fonte TEXT NOT NULL, codice TEXT NOT NULL, url TEXT,
    forma_autorizzata TEXT, data_verifica TEXT
);
DROP TABLE IF EXISTS alias_esterni;
CREATE TABLE alias_esterni (
    entita  INTEGER NOT NULL,
    fonte   TEXT NOT NULL,      -- Wikidata
    codice  TEXT NOT NULL,      -- QID
    lingua  TEXT NOT NULL,      -- it | la | fur
    forma   TEXT NOT NULL
);
"""
COLONNE = {"stato": "TEXT", "affidabilita": "TEXT", "nota": "TEXT"}


def sparql(query, tentativi=4):
    url = SPARQL + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    for t in range(tentativi):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)["results"]["bindings"]
        except Exception as e:                     # limiti di frequenza o tempo: si riprova con calma
            print(f"  SPARQL: {e}; nuovo tentativo", file=sys.stderr)
            time.sleep(10 * (t + 1))
    raise RuntimeError("Wikidata non risponde")


def valore(b, k):
    return b[k]["value"] if k in b else None


# ---------------------------------------------------------------------------
# GeoNames locale
# ---------------------------------------------------------------------------

def indice_geonames(nomi):
    """forma normalizzata → candidati [(punteggio, gid, nome, tipo, regione, provincia, paese, popolazione)]."""
    cercati = {normalizza(n) for n in nomi}
    cand = defaultdict(dict)

    def aggiungi(r, italia):
        forme = {r[1], r[2]} | set(x for x in r[3].split(",") if x)
        for f in forme:
            k = normalizza(f)
            if k not in cercati:
                continue
            tipo, adm1, pop = r[7], r[10], int(r[14] or 0)
            principale = normalizza(r[1]) == k
            p = PESO_TIPO.get(tipo, 0) + (2 if principale else 0)
            if italia:
                p += 7 if adm1 == "06" else 6 if adm1 in REGIONI else 2   # il Friuli prima del Veneto
            else:
                p += min(4, len(str(pop)) - 3) if pop else 0
            if p > cand[k].get(r[0], (-1,))[0]:
                cand[k][r[0]] = (p, r[0], r[1], tipo, adm1, r[11], r[8], pop)

    with zipfile.ZipFile(ESTERNI / "IT.zip") as z, z.open("IT.txt") as fh:
        for r in csv.reader(io.TextIOWrapper(fh, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
            if r[6] in ("P", "A", "L", "T", "H"):
                aggiungi(r, True)
    with zipfile.ZipFile(ESTERNI / "cities5000.zip") as z, z.open("cities5000.txt") as fh:
        for r in csv.reader(io.TextIOWrapper(fh, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
            if r[8] != "IT":
                aggiungi(r, False)
    return {k: sorted(v.values(), reverse=True) for k, v in cand.items()}


# ---------------------------------------------------------------------------
# Wikidata
# ---------------------------------------------------------------------------

def wikidata_per_etichetta(nomi, cache):
    """etichetta italiana → [(qid, gid, descrizione, sitelinks, paese)], solo elementi con P1566."""
    mancanti = [n for n in nomi if n not in cache["etichette"]]
    for i in range(0, len(mancanti), 40):
        blocco = mancanti[i:i + 40]
        valori = " ".join(json.dumps(n, ensure_ascii=False) + "@it" for n in blocco)
        q = f"""SELECT ?l ?item ?g ?desc ?sl ?paese WHERE {{
  VALUES ?l {{ {valori} }}
  ?item rdfs:label ?l ; wdt:P1566 ?g ; wikibase:sitelinks ?sl .
  OPTIONAL {{ ?item schema:description ?desc FILTER(lang(?desc) = "it") }}
  OPTIONAL {{ ?item wdt:P17 ?paese }}
}}"""
        for n in blocco:
            cache["etichette"][n] = []
        for b in sparql(q):
            n = valore(b, "l")
            qid = valore(b, "item").rsplit("/", 1)[1]
            riga = [qid, valore(b, "g"), valore(b, "desc"), int(valore(b, "sl") or 0),
                    (valore(b, "paese") or "").rsplit("/", 1)[-1]]
            if riga not in cache["etichette"][n]:
                cache["etichette"][n].append(riga)
        salva(cache)
        print(f"  etichette: {min(i + 40, len(mancanti))}/{len(mancanti)}", file=sys.stderr)
        time.sleep(1)


def wikidata_noti_per_etichetta(nomi, cache):
    """Elementi con coordinate o collocazione amministrativa e almeno 10 voci di Wikipedia, anche senza P1566 (la Carnia regione
    storica non ha un identificativo GeoNames): etichetta → [(qid, gid|None, descrizione, sitelinks, paese)]."""
    cache.setdefault("noti", {})
    mancanti = [n for n in nomi if n not in cache["noti"]]
    for i in range(0, len(mancanti), 40):
        blocco = mancanti[i:i + 40]
        valori = " ".join(json.dumps(n, ensure_ascii=False) + "@it" for n in blocco)
        q = f"""SELECT ?l ?item ?g ?desc ?sl ?paese WHERE {{
  VALUES ?l {{ {valori} }}
  ?item rdfs:label ?l ; wikibase:sitelinks ?sl .
  FILTER(?sl >= 10)
  FILTER EXISTS {{ {{ ?item wdt:P625 [] }} UNION {{ ?item wdt:P131 [] }} }}
  OPTIONAL {{ ?item wdt:P1566 ?g }}
  OPTIONAL {{ ?item schema:description ?desc FILTER(lang(?desc) = "it") }}
  OPTIONAL {{ ?item wdt:P17 ?paese }}
}}"""
        for n in blocco:
            cache["noti"][n] = []
        for b in sparql(q):
            n = valore(b, "l")
            riga = [valore(b, "item").rsplit("/", 1)[1], valore(b, "g"), valore(b, "desc"),
                    int(valore(b, "sl") or 0), (valore(b, "paese") or "").rsplit("/", 1)[-1]]
            if not any(x[0] == riga[0] for x in cache["noti"][n]):
                cache["noti"][n].append(riga)
        salva(cache)
        print(f"  noti: {min(i + 40, len(mancanti))}/{len(mancanti)}", file=sys.stderr)
        time.sleep(1)


def wikidata_per_geonames(gids, cache):
    """geonameid → qid (P1566)."""
    mancanti = [g for g in gids if g not in cache["gid"]]
    for i in range(0, len(mancanti), 150):
        blocco = mancanti[i:i + 150]
        valori = " ".join(json.dumps(g) for g in blocco)
        for g in blocco:
            cache["gid"][g] = None
        for b in sparql(f"SELECT ?g ?item WHERE {{ VALUES ?g {{ {valori} }} ?item wdt:P1566 ?g . }}"):
            cache["gid"][valore(b, "g")] = valore(b, "item").rsplit("/", 1)[1]
        salva(cache)
        time.sleep(1)


def wikidata_dettagli(qids, cache):
    """qid → {etichetta it, descrizione it, alias {lingua: [forme]}}."""
    mancanti = [q for q in qids if q not in cache["dettagli"]]
    for i in range(0, len(mancanti), 100):
        blocco = mancanti[i:i + 100]
        valori = " ".join("wd:" + q for q in blocco)
        q = f"""SELECT ?item ?lab ?desc ?alias WHERE {{
  VALUES ?item {{ {valori} }}
  OPTIONAL {{ ?item rdfs:label ?lab FILTER(lang(?lab) = "it") }}
  OPTIONAL {{ ?item wdt:P1566 ?g }}
  OPTIONAL {{ ?item schema:description ?desc FILTER(lang(?desc) = "it") }}
  OPTIONAL {{ ?item skos:altLabel ?alias FILTER(lang(?alias) IN ("it", "la", "fur")) }}
}}"""
        for qid in blocco:
            cache["dettagli"][qid] = {"etichetta": None, "descrizione": None, "alias": {}}
        for b in sparql(q):
            d = cache["dettagli"][valore(b, "item").rsplit("/", 1)[1]]
            d["etichetta"] = d["etichetta"] or valore(b, "lab")
            d["descrizione"] = d["descrizione"] or valore(b, "desc")
            d["gid"] = d.get("gid") or valore(b, "g")
            if "alias" in b:
                lingua = b["alias"].get("xml:lang")
                d["alias"].setdefault(lingua, [])
                if b["alias"]["value"] not in d["alias"][lingua]:
                    d["alias"][lingua].append(b["alias"]["value"])
        salva(cache)
        time.sleep(1)


def comuni_istat():
    """nome ufficiale → codice ISTAT (P635 su Wikidata)."""
    testo = (ESTERNI / "comuni_istat.csv").read_bytes().decode("latin-1")
    righe = list(csv.reader(io.StringIO(testo), delimiter=";"))
    h = righe[0]
    i_den, i_cod = h.index("Denominazione in italiano"), h.index("Codice Comune formato alfanumerico")
    i_reg = h.index("Denominazione Regione")
    return {r[i_den]: (r[i_cod], r[i_reg]) for r in righe[1:] if len(r) > max(i_cod, i_reg)}


def wikidata_per_istat(codici, cache):
    """codice ISTAT → qid del comune."""
    cache.setdefault("istat", {})
    mancanti = [c for c in codici if c not in cache["istat"]]
    for i in range(0, len(mancanti), 150):
        blocco = mancanti[i:i + 150]
        valori = " ".join(json.dumps(c) for c in blocco)
        for c in blocco:
            cache["istat"][c] = None
        migliore = {}
        # più elementi possono portare lo stesso codice ISTAT (il comune e la frazione capoluogo, Raspano
        # per Cassacco): vince quello con più voci di Wikipedia, cioè il comune
        for b in sparql(f"SELECT ?c ?item ?sl WHERE {{ VALUES ?c {{ {valori} }} ?item wdt:P635 ?c ; "
                        f"wikibase:sitelinks ?sl . }}"):
            cod, sl = valore(b, "c"), int(valore(b, "sl") or 0)
            if sl > migliore.get(cod, -1):
                migliore[cod] = sl
                cache["istat"][cod] = valore(b, "item").rsplit("/", 1)[1]
        salva(cache)
        time.sleep(1)


def salva(cache):
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------

def scegli(nome, locali, wd, qid_di):
    """Restituisce (gid, qid, affidabilita, nota, alternative)."""
    regionali = [c for c in locali if c[6] == "IT" and c[4] in REGIONI and c[3].startswith(("PPL", "ADM"))]
    regionali_p = [c for c in regionali if c[3].startswith("PPL")]
    wd_gid = {w[1]: w for w in wd}
    if regionali:
        scelto = regionali[0]
        altri = [c for c in (regionali_p or regionali)[1:] if c[2] == scelto[2] and c[3].startswith("PPL")
                 and c[1] != scelto[1]]
        if scelto[3].startswith(("PPLA", "ADM")):
            altri = []                            # capoluogo di comune o ente: prevale sulle frazioni omonime
        aff = "alta" if not altri else "media"
        nota = "più località omonime in regione" if altri else None
        return scelto[1], wd_gid.get(scelto[1], [None])[0] or qid_di.get(scelto[1]), aff, nota, altri[:4]
    if wd:
        wd_s = sorted(wd, key=lambda w: (w[4] == "Q38", w[3]), reverse=True)
        top = wd_s[0]
        unico = len(wd_s) == 1 or (wd_s[0][3] >= 3 * max(1, wd_s[1][3])) or \
            (wd_s[0][3] >= 30 and wd_s[0][3] >= 2 * wd_s[1][3])
        return top[1], top[0], "alta" if unico else "media", None if unico else "più elementi Wikidata omonimi", \
            [(None, w[1], w[0], w[2]) for w in wd_s[1:4]]
    if locali:
        top = locali[0]
        return top[1], qid_di.get(top[1]), "bassa", "solo GeoNames, fuori regione", locali[1:4]
    return None, None, None, None, []


def main():
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    esistenti = {r[1] for r in con.execute("PRAGMA table_info(identificatori)")}
    for c, t in COLONNE.items():
        if c not in esistenti:
            con.execute(f"ALTER TABLE identificatori ADD COLUMN {c} {t}")
    con.execute("DELETE FROM identificatori WHERE entita IN (SELECT id FROM entita WHERE tipo='luogo')")
    entita = con.execute("SELECT id, forma_intestazione, nota FROM entita WHERE tipo='luogo'").fetchall()
    nomi = sorted({e[1] for e in entita})
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else \
        {"etichette": {}, "gid": {}, "dettagli": {}}

    print("GeoNames locale…", file=sys.stderr)
    locali = indice_geonames(nomi)
    print("Wikidata per etichetta…", file=sys.stderr)
    wikidata_per_etichetta(nomi, cache)
    wikidata_noti_per_etichetta(nomi, cache)

    scelte = {}
    for eid, nome, nota_e in entita:
        loc = locali.get(normalizza(nome), [])
        wd = cache["etichette"].get(nome, [])
        scelte[eid] = (nome, loc, wd, nota_e)
    manuali = {r["forma"]: r for r in csv.DictReader(
        open(RADICE / "dati" / "liste" / "luoghi_collegamenti.tsv", encoding="utf-8"), delimiter="\t")}
    gids = {c[1] for _, loc, _, _ in scelte.values() for c in loc[:3]} | \
        {m["geonameid"] for m in manuali.values() if m["geonameid"]}
    print("Wikidata per GeoNames…", file=sys.stderr)
    wikidata_per_geonames(sorted(gids), cache)

    # comuni italiani: l'elemento Wikidata del comune (P635), non quello del «capoluogo dell'omonimo comune»
    istat = comuni_istat()
    print("Wikidata per codice ISTAT…", file=sys.stderr)
    wikidata_per_istat(sorted({istat[n][0] for n in nomi if n in istat} |
                              {cod for n, (cod, reg) in istat.items() if reg == "Friuli-Venezia Giulia"}), cache)
    confermati = {x.strip() for x in (RADICE / "dati" / "liste" / "luoghi_confermati.txt").read_text(
        encoding="utf-8").splitlines() if x.strip() and not x.startswith("#")}
    cognomi = {f for (f,) in con.execute("SELECT forma FROM lessico WHERE parte='cognome'")}
    doppie = {f for (f,) in con.execute("SELECT forma FROM lessico WHERE stato='doppia_lettura'")}

    risultati = {}
    for eid, (nome, loc, wd, nota_e) in scelte.items():
        gid, qid, aff, nota, alt = scegli(nome, loc, wd, cache["gid"])
        c = next((c for c in loc if c[1] == gid), None)
        comune = nome in istat
        if comune:
            cod, regione = istat[nome]
            stesso = [x for x in loc if x[6] == "IT" and x[2] == nome and x[3].startswith(("PPLA", "PPL", "ADM3"))]
            if c and c[2] != nome and stesso:     # «Cassacco», non la frazione Raspano trovata tra gli alias
                c = stesso[0]
                gid = c[1]
            if regione not in REGIONI.values():
                # comune fuori regione: il centro principale, non una frazione friulana o veneta omonima
                italiani = [x for x in loc if x[6] == "IT" and x[4] not in REGIONI]
                if italiani:
                    c = max(italiani, key=lambda x: (PESO_TIPO.get(x[3], 0), x[7]))
                    gid = c[1]
            if cache["istat"].get(cod):
                qid = cache["istat"][cod]
            if aff in ("media", "bassa") and nota in ("più località omonime in regione", "solo GeoNames, fuori regione"):
                aff, nota = "alta", None            # il comune prevale sulle frazioni omonime
        if wd or cache["noti"].get(nome):
            # un elemento Wikidata molto più noto della località scelta: regione storica, fiume, stato,
            # città (Roma) invece dell'ente comunale o di una frazione omonima («Carnia», «Tagliamento»)
            tutti = wd + [x for x in cache["noti"].get(nome, []) if not any(y[0] == x[0] for y in wd)]
            regionale = c and c[6] == "IT" and c[4] in REGIONI
            forte = regionale and (c[3].startswith(("PPLA", "ADM")) or c[4] == "06")
            if tutti:
                noto = max(tutti, key=lambda x: x[3])
                sl_scelto = next((x[3] for x in tutti if x[0] == qid), 0)
                soglia = (50, 10) if forte else (10, 1.5)    # Parigi, Romania, Riga, Colonia: non le frazioni
                if noto[0] != qid and noto[3] >= soglia[0] and noto[3] > soglia[1] * max(1, sl_scelto) \
                        and not (comune and regionale):
                    gid, qid, aff, nota = noto[1] or (gid if comune else None), noto[0], "alta", None
                    c = next((c for c in loc if c[1] == gid), None)
        sl = next((x[3] for x in wd if x[0] == qid), 0)
        if not comune and c and c[6] == "IT" and c[4] == "20" and c[3] in ("PPL", "PPLL", "PPLX") and aff == "alta" \
                and sl < 20:                          # Mestre è nota, Sasso e Zucca no
            aff, nota = "media", "frazione veneta omonima: verificare"   # Sasso, Zucca, Alpe
        if c and c[6] == "IT" and not comune and nome in doppie and aff == "alta" and not c[3].startswith("ADM"):
            aff, nota = "media", "anche cognome nel testo"
        # forma breve di un comune friulano: «Colloredo» = Colloredo di Monte Albano, «Gradisca» = Gradisca
        # d'Isonzo, «San Daniele» = San Daniele del Friuli (se non è già un comune o un capoluogo)
        lunghi = [n for n, (cod, reg) in istat.items() if reg == "Friuli-Venezia Giulia"
                  and (n.startswith(nome + " ") or n.startswith(nome + "-"))]
        if len(lunghi) == 1 and not comune and not (c and c[6] == "IT" and c[4] == "06" and c[3].startswith("PPLA")) \
                and cache["istat"].get(istat[lunghi[0]][0]):
            qid, gid, aff, nota = cache["istat"][istat[lunghi[0]][0]], None, "alta", f"forma breve di {lunghi[0]}"
            c = None
        # parola che nel testo è un cognome e che corrisponde solo a una frazione fuori Friuli
        if c and c[6] == "IT" and c[4] != "06" and c[3] in ("PPL", "PPLL", "PPLX") and nome in cognomi \
                and not comune:
            aff, nota = "bassa", "probabilmente cognome, non luogo"
        # decisioni del curatore o dal contesto, anche se prese per una forma poi unita (fase 6)
        chiave_m = next((x for x in [nome] + altre_intestazioni(None, nota_e) if x in manuali), None)
        if chiave_m:
            m = manuali[chiave_m]
            gid, qid, nota = m["geonameid"] or None, m["qid"] or cache["gid"].get(m["geonameid"]), m["nota"]
            aff = "alta" if (gid or qid) else None   # vuoto: non è un luogo
        if any(x in confermati for x in [nome] + altre_intestazioni(None, nota_e)) and aff == "media":
            aff, nota = "alta", "grafia confermata dal curatore" + (f"; {nota}" if nota else "")
        if nota_senza_unioni(nota_e) and aff == "alta":
            aff = "media"                          # forma già segnalata come incerta nel lessico
        risultati[eid] = (nome, gid, qid, aff, nota, alt, loc)
    qids = sorted({r[2] for r in risultati.values() if r[2]})
    print("Wikidata dettagli…", file=sys.stderr)
    wikidata_dettagli(qids, cache)

    nome_gn = {c[1]: c[2] for loc in locali.values() for c in loc}
    for eid, (nome, gid, qid, aff, nota, alt, loc) in risultati.items():
        if not gid and not qid:
            continue
        d = cache["dettagli"].get(qid, {}) if qid else {}
        gid = gid or d.get("gid")                  # identificativo GeoNames dell'elemento Wikidata scelto
        forma = d.get("etichetta") or nome_gn.get(gid) or nome
        if gid:
            con.execute("INSERT INTO identificatori (entita, fonte, codice, url, forma_autorizzata, data_verifica, "
                        "stato, affidabilita, nota) VALUES (?,?,?,?,?,?,?,?,?)",
                        (eid, "GeoNames", gid, f"https://www.geonames.org/{gid}", forma, OGGI, "proposto", aff, nota))
        if qid:
            con.execute("INSERT INTO identificatori (entita, fonte, codice, url, forma_autorizzata, data_verifica, "
                        "stato, affidabilita, nota) VALUES (?,?,?,?,?,?,?,?,?)",
                        (eid, "Wikidata", qid, f"https://www.wikidata.org/wiki/{qid}", forma, OGGI, "proposto",
                         aff, nota))
            for lingua, forme in d.get("alias", {}).items():
                for f in forme:
                    con.execute("INSERT INTO alias_esterni VALUES (?,?,?,?,?)", (eid, "Wikidata", qid, lingua, f))
    con.commit()
    report(con, risultati, cache)
    con.close()


def report(con, risultati, cache):
    r = []
    w = r.append
    q = lambda s, *a: con.execute(s, a).fetchall()  # noqa: E731
    menz = dict(q("SELECT entita, count(*) FROM menzioni WHERE entita IS NOT NULL GROUP BY 1"))
    voci = defaultdict(list)
    for eid, num in q("SELECT DISTINCT m.entita, v.numero FROM menzioni m JOIN voci v ON v.id=m.voce "
                      "WHERE m.entita IN (SELECT id FROM entita WHERE tipo='luogo') ORDER BY v.id"):
        if len(voci[eid]) < 4:
            voci[eid].append(num)
    per = defaultdict(list)
    for eid, x in risultati.items():
        per[x[3] or "nessuna"].append((eid,) + x)
    w("# Fase 5 — Luoghi: collegamento a GeoNames e Wikidata\n")
    w(f"Verifica del {OGGI}. Tutti i collegamenti sono **proposti**. Per ogni luogo: forma del curatore → forma "
      "autorizzata italiana, identificativi e (per Wikidata) la descrizione breve, mostrata solo qui per scegliere "
      "e non salvata. Gli alias di Wikidata (it, la, fur) sono in `alias_esterni` e diventeranno varianti di ricerca "
      "dopo la conferma.\n")
    w("| Affidabilità | Luoghi |\n|---|---|")
    for k in ("alta", "media", "bassa", "nessuna"):
        w(f"| {k} | {len(per[k])} |")
    w("")

    def riga(x, alternative=True):
        eid, nome, gid, qid, aff, nota, alt, loc = x
        d = cache["dettagli"].get(qid, {}) if qid else {}
        gid = gid or d.get("gid")
        forma = d.get("etichetta") or (loc[0][2] if loc else "")
        luogo = ""
        c = next((c for c in loc if c[1] == gid), None)
        if c:
            luogo = f"{c[3]}, " + (REGIONI.get(c[4], f"reg. {c[4]}") if c[6] == "IT" else c[6]) + \
                (f" ({c[5]})" if c[6] == "IT" and c[5] else "")
        s = (f"- **{nome}** ({menz.get(eid, 0)} menz.; voci {', '.join(voci[eid])}) → {forma}"
             + (f" — GeoNames [{gid}](https://www.geonames.org/{gid})" if gid else "")
             + (f" {luogo}" if luogo else "")
             + (f" — Wikidata [{qid}](https://www.wikidata.org/wiki/{qid})" if qid else "")
             + (f": _{d['descrizione']}_" if d.get("descrizione") else "")
             + (f" — {nota}" if nota else ""))
        if alternative and alt:
            alts = []
            for a in alt:
                if a[0] is None:                    # alternativa Wikidata
                    alts.append(f"[{a[2]}](https://www.wikidata.org/wiki/{a[2]}) {a[3] or ''}")
                else:
                    alts.append(f"[{a[1]}](https://www.geonames.org/{a[1]}) {a[2]} {a[3]} "
                                + (REGIONI.get(a[4], a[4]) if a[6] == "IT" else a[6]) + (f" {a[5]}" if a[5] else ""))
            s += "\n  - altri: " + "; ".join(alts)
        return s

    w("## 1. Affidabilità media: più candidati, da scegliere\n")
    for x in sorted(per["media"], key=lambda x: x[1]):
        w(riga(x))
    w("\n## 2. Affidabilità bassa: solo GeoNames fuori regione\n")
    for x in sorted(per["bassa"], key=lambda x: x[1]):
        w(riga(x))
    w("\n## 3. Nessuna corrispondenza\n")
    w("Forme che non sono luoghi (cognomi, parole) o luoghi minori assenti da GeoNames e Wikidata.\n")
    w(", ".join(f"{x[1]} ({', '.join(voci[x[0]])})" for x in sorted(per["nessuna"], key=lambda x: x[1])) + "\n")
    w("## 4. Affidabilità alta\n")
    for x in sorted(per["alta"], key=lambda x: x[1]):
        w(riga(x, alternative=False))
    OUT.write_text("\n".join(r) + "\n", encoding="utf-8")
    print(f"Report scritto in {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
