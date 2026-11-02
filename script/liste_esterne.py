#!/usr/bin/env python3
"""Liste di riferimento per l'estrazione (fase 3), da dati aperti.

Scarica (se mancano) in dati/esterni/ — file non versionati — e produce:
- dati/liste/luoghi.tsv: forma, forma_normalizzata, peso, fonte, codice, url
  peso: forte (Friuli, Veneto, capoluoghi, grandi città), medio (altri comuni
  italiani, città estere minori), debole (altre località italiane: valgono
  solo con un contesto che indichi un luogo, es. «in», «da»).
- dati/liste/nomi.tsv: forma, forma_normalizzata, lingua, fonte, codice, url
  (nomi di battesimo da Wikidata: italiano, latino, friulano).

Fonti: ISTAT (elenco comuni), GeoNames (IT.zip, cities5000.zip), Wikidata
(SPARQL). Si conservano forma, identificativo e URL (CLAUDE.md, regola 7).

Uso: python3 script/liste_esterne.py
"""

import csv
import io
import re
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalizza import normalizza  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
ESTERNI = RADICE / "dati" / "esterni"
LISTE = RADICE / "dati" / "liste"
UA = "InventarioJoppi/0.1 (ricerca storica sul Fondo Principale della Biblioteca Joppi)"

FONTI = {
    "comuni_istat.csv": "https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.csv",
    "IT.zip": "https://download.geonames.org/export/dump/IT.zip",
    "cities5000.zip": "https://download.geonames.org/export/dump/cities5000.zip",
}
FRIULI, VENETO = "06", "20"   # codici admin1 GeoNames


def scarica():
    ESTERNI.mkdir(parents=True, exist_ok=True)
    for nome, url in FONTI.items():
        if not (ESTERNI / nome).exists():
            subprocess.run(["curl", "-s", "--max-time", "300", "-A", UA, "-o", str(ESTERNI / nome), url], check=True)
    if not (ESTERNI / "nomi_wikidata.csv").exists():
        righe = []
        for tipo in ("Q12308941", "Q11879590", "Q3409032"):   # nome maschile, femminile, unisex
            for lingua in ("it", "la", "fur"):
                q = (f"SELECT ?n ?lab WHERE {{ ?n wdt:P31 wd:{tipo} . ?n rdfs:label ?lab . "
                     f"FILTER(LANG(?lab)=\"{lingua}\") }}")
                out = subprocess.run(["curl", "-s", "--max-time", "280", "-G", "https://query.wikidata.org/sparql",
                                      "--data-urlencode", f"query={q}", "-H", "Accept: text/csv", "-A", UA],
                                     capture_output=True, text=True, check=True).stdout
                for r in list(csv.reader(io.StringIO(out)))[1:]:
                    if len(r) == 2:
                        righe.append(r + [tipo, lingua])
        with open(ESTERNI / "nomi_wikidata.csv", "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(righe)


def forma_valida(f):
    """Scarta codici, sigle, forme non latine e denominazioni amministrative."""
    if len(f) < 3 or re.search(r"\d", f) or not re.fullmatch(r"[A-Za-zÀ-ÿ' ’\-\.]+", f):
        return False
    if f.isupper() or re.match(r"(?i)(comune|provincia|province|ente|regione|citt[aà] metropolitana)\b", f):
        return False
    return True


def luoghi():
    voci = {}   # (forma) -> (peso, fonte, codice, url)
    ordine = {"forte": 0, "medio": 1, "debole": 2}

    citta = set()

    def aggiungi(forma, peso, fonte, codice, url, e_citta=False):
        forma = forma.strip()
        if not forma_valida(forma):
            return
        if e_citta:
            citta.add(forma)
        attuale = voci.get(forma)
        if attuale is None or ordine[peso] < ordine[attuale[0]]:
            voci[forma] = (peso, fonte, codice, url)

    # ISTAT: comuni
    testo = (ESTERNI / "comuni_istat.csv").read_bytes().decode("latin-1")
    righe = list(csv.reader(io.StringIO(testo), delimiter=";"))
    intest = righe[0]
    i_den = intest.index("Denominazione in italiano")
    i_alt = intest.index("Denominazione altra lingua")
    i_reg = intest.index("Denominazione Regione")
    i_cod = intest.index("Codice Comune formato alfanumerico")
    i_cap = next(k for k, h in enumerate(intest) if h.startswith("Flag Comune capoluogo"))
    for r in righe[1:]:
        if len(r) <= i_reg:
            continue
        forte = r[i_reg] in ("Friuli-Venezia Giulia", "Veneto") or r[i_cap] == "1"
        url = "https://www.istat.it/classificazione/codici-dei-comuni-delle-province-e-delle-regioni/"
        for f in [r[i_den]] + [x for x in r[i_alt].split("/") if x]:
            aggiungi(f, "forte" if forte else "medio", "ISTAT", r[i_cod], url, r[i_cap] == "1")

    # GeoNames Italia
    with zipfile.ZipFile(ESTERNI / "IT.zip") as z, z.open("IT.txt") as fh:
        for r in csv.reader(io.TextIOWrapper(fh, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
            classe, codice_f, adm1 = r[6], r[7], r[10]
            pop = int(r[14] or 0)
            regione = adm1 in (FRIULI, VENETO)
            if classe == "P":
                peso = "forte" if (adm1 == FRIULI or codice_f.startswith("PPLA") or pop >= 20000) else (
                    "medio" if regione else "debole")
            elif classe == "A" and codice_f in ("ADM1", "ADM2", "ADM3"):
                peso = "forte" if (regione or codice_f != "ADM3") else "medio"
            elif classe in ("L", "T") and adm1 == FRIULI:
                peso = "medio"               # regioni storiche, monti, valli del Friuli («Carnia»)
            else:
                continue
            url = f"https://www.geonames.org/{r[0]}"
            for f in [r[1]] + r[3].split(","):
                aggiungi(f, peso, "GeoNames", r[0], url, classe == "P" and pop >= 15000)

    # GeoNames: città del mondo con almeno 5000 abitanti (nomi italiani e latini compresi)
    with zipfile.ZipFile(ESTERNI / "cities5000.zip") as z, z.open("cities5000.txt") as fh:
        for r in csv.reader(io.TextIOWrapper(fh, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
            if r[8] == "IT":
                continue
            pop = int(r[14] or 0)
            # all'estero valgono solo le città note anche in italiano (Vienna, Parigi…)
            peso = "forte" if pop >= 500000 else "medio" if pop >= 100000 else "debole"
            url = f"https://www.geonames.org/{r[0]}"
            for f in [r[1]] + r[3].split(","):
                aggiungi(f, peso, "GeoNames", r[0], url, pop >= 500000)
    for v in voci:
        voci[v] = voci[v] + ("1" if v in citta else "0",)
    return voci


def nomi():
    voci = {}
    testo = (ESTERNI / "nomi_wikidata.csv").read_bytes().decode("utf-8").replace("\r", "")
    for riga in csv.reader(io.StringIO(testo)):
        if len(riga) != 4:
            continue
        qid, forma, tipo, lingua = riga
        forma = forma.strip()
        if not re.fullmatch(r"[A-Za-zÀ-ÿ'’\-]{2,}", forma):
            continue
        codice = qid.rsplit("/", 1)[-1]
        voci.setdefault((forma, lingua), (codice, qid))
    return voci


def main():
    scarica()
    LISTE.mkdir(parents=True, exist_ok=True)
    l = luoghi()
    with open(LISTE / "luoghi.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["forma", "forma_normalizzata", "peso", "fonte", "codice", "url", "citta"])
        for forma in sorted(l):
            w.writerow([forma, normalizza(forma)] + list(l[forma]))
    n = nomi()
    with open(LISTE / "nomi.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["forma", "forma_normalizzata", "lingua", "fonte", "codice", "url"])
        for (forma, lingua) in sorted(n):
            codice, url = n[(forma, lingua)]
            w.writerow([forma, normalizza(forma), lingua, "Wikidata", codice, url])
    print(f"luoghi: {len(l)} forme; nomi: {len(n)} forme")


if __name__ == "__main__":
    main()
