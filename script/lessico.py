#!/usr/bin/env python3
"""Lessico delle parole dei nomi e scrematura delle forme già normalizzate.

Lo scopo della ricerca è che chi cerca «Giovanni da Udine» trovi «Zuan de
Udene»: si normalizzano le parti del nome (Giovanni ↔ Zuane, Udine ↔ Udene),
non le menzioni intere. Per questo il lessico registra ogni parola distinta
delle menzioni di persona (e ogni forma intera di luogo e di santo), con:

- parte: nome_di_battesimo | cognome | luogo | santo | opera | particella |
  titolo | iniziale | numerale
- stato: normale | da_normalizzare | doppia_lettura | da_verificare
    normale          già nella forma di riferimento (nome italiano corrente,
                     nome ufficiale ISTAT/GeoNames…)
    da_normalizzare  variante con forma normalizzata proposta o da trovare
                     (abbreviazioni, latino, forme venete, nomi storici di luogo)
    doppia_lettura   nome ufficiale di un luogo che compare anche come cognome o
                     famiglia («Savorgnano», «Belgrado»): normale come luogo, ma
                     da non unire d'ufficio alla famiglia
    da_verificare    cognomi: la forma di riferimento verrà dalle fonti (fase 5)
- forma_normalizzata, origine (lista, fonte o regola), riferimento (QID, geonameid,
  codice ISTAT), occorrenze, voci.

Scrive la tabella `lessico` e il report report/fase_3_lessico.md.

Uso: python3 script/lessico.py
"""

import csv
import difflib
import io
import re
import sqlite3
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalizza import normalizza  # noqa: E402
import estrai  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
DB = RADICE / "dati" / "inventario.sqlite"
LISTE = RADICE / "dati" / "liste"
ESTERNI = RADICE / "dati" / "esterni"
OUT = RADICE / "report" / "fase_3_lessico.md"

SCHEMA = """
DROP TABLE IF EXISTS lessico;
CREATE TABLE lessico (
    id                 INTEGER PRIMARY KEY,
    forma              TEXT NOT NULL,      -- parola (o forma intera di luogo/santo) come nel testo
    parte              TEXT NOT NULL,      -- nome_di_battesimo | cognome | luogo | santo | opera | particella | titolo | iniziale | numerale
    stato              TEXT NOT NULL,      -- normale | da_normalizzare | doppia_lettura | da_verificare
    forma_normalizzata TEXT,               -- forma di riferimento proposta
    origine            TEXT,               -- da dove viene la forma normalizzata
    riferimento        TEXT,               -- QID Wikidata, geonameid, codice ISTAT…
    gruppo_grafico     TEXT,               -- forma normalizzata secondo CLAUDE.md (unisce le varianti minime)
    occorrenze         INTEGER NOT NULL,
    voci               TEXT                -- prime voci in cui compare
);
CREATE INDEX ix_lessico_forma ON lessico(forma);
CREATE INDEX ix_lessico_gruppo ON lessico(gruppo_grafico);
"""

REGIONALI = set()          # nomi ufficiali di luoghi del Friuli e del Veneto
RX_PAROLA = re.compile(r"[^\W\d_][^\W\d_'’]*(?:['’][^\W\d_]+)*(?:-[^\W\d_]+)*(?:\.(?:co|meo|eo|zo|mo|ro|na|ne|ni|lo|to|so|r|ra|te|ssa|ta)\b|\.°|°|\.)?")


# ---------------------------------------------------------------------------
# Fonti di riferimento
# ---------------------------------------------------------------------------

def nomi_ufficiali_luoghi():
    """forma → (nome ufficiale, codice, fonte) e insieme dei nomi ufficiali italiani."""
    ufficiali = {}                     # nome ufficiale → (codice, fonte)
    alternativi = {}                   # forma alternativa → (nome ufficiale, codice, fonte)
    testo = (ESTERNI / "comuni_istat.csv").read_bytes().decode("latin-1")
    righe = list(csv.reader(io.StringIO(testo), delimiter=";"))
    h = righe[0]
    i_den, i_cod = h.index("Denominazione in italiano"), h.index("Codice Comune formato alfanumerico")
    i_alt = h.index("Denominazione altra lingua")
    i_reg = h.index("Denominazione Regione")
    for r in righe[1:]:
        if len(r) > i_reg and r[i_reg] in ("Friuli-Venezia Giulia", "Veneto"):
            REGIONALI.add(r[i_den])
        if len(r) > i_alt:
            ufficiali.setdefault(r[i_den], (r[i_cod], "ISTAT"))
            for a in r[i_alt].split("/"):
                if a:
                    alternativi.setdefault(a, (r[i_den], r[i_cod], "ISTAT"))
    istat = set(ufficiali)
    with zipfile.ZipFile(ESTERNI / "IT.zip") as z, z.open("IT.txt") as fh:
        for r in csv.reader(io.TextIOWrapper(fh, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
            if r[6] not in ("P", "A", "L", "T"):
                continue
            nome = re.sub(r"^Comune di ", "", r[1])
            if nome not in istat:     # GeoNames dà il nome inglese delle città maggiori: «Padua», «Venice»
                nome = next((a for a in r[3].split(",") if a in istat), nome)
            ufficiali.setdefault(nome, (r[0], "GeoNames"))
            if r[10] in ("06", "20") and r[6] in ("P", "A"):
                REGIONALI.add(nome)
            for a in r[3].split(","):
                if a and a != nome:
                    alternativi.setdefault(a, (nome, r[0], "GeoNames"))
    esteri, popolazione = {}, {}
    with zipfile.ZipFile(ESTERNI / "cities5000.zip") as z, z.open("cities5000.txt") as fh:
        for r in csv.reader(io.TextIOWrapper(fh, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
            if r[8] != "IT":
                # a parità di forma vince la città più popolosa, mai un quartiere (PPLX):
                # «Graz» è la città, non «Innere Stadt»; «Londra» è Londra, non la City
                pop = -1 if r[7] == "PPLX" else int(r[14] or 0)
                for a in [r[1]] + r[3].split(","):
                    if a and pop > popolazione.get(a, -2):
                        popolazione[a] = pop
                        esteri[a] = (r[1], r[0], "GeoNames")
    manuali = {}
    for r in csv.DictReader(open(LISTE / "luoghi_manuali.tsv", encoding="utf-8"), delimiter="\t"):
        manuali[r["forma"]] = r.get("riferimento") or ""
    return ufficiali, alternativi, esteri, manuali


def nomi_di_battesimo():
    """forma → (lingua, QID); QID → forma italiana."""
    forme = defaultdict(set)
    italiano = {}
    for r in csv.DictReader(open(LISTE / "nomi.tsv", encoding="utf-8"), delimiter="\t"):
        forme[r["forma"]].add((r["lingua"], r["codice"]))
        if r["lingua"] == "it" and r["codice"] not in italiano:
            italiano[r["codice"]] = r["forma"]
    return forme, italiano


IRREGOLARI = {"petr": "Pietro", "thom": "Tommaso", "ioann": "Giovanni", "iohann": "Giovanni", "johann": "Giovanni",
              "georg": "Giorgio", "hieronym": "Girolamo", "aloys": "Luigi", "ludovic": "Lodovico", "francisc": "Francesco",
              "iacob": "Giacomo o Jacopo", "jacob": "Giacomo o Jacopo", "baptist": "Battista", "christian": "Cristiano"}


def latino_italiano(forma, nomi_it):
    """Forma italiana di un nome latino, anche declinato: «Julii» → «Giulio», «Thomae» → «Tommaso»,
    «Fabricii» → «Fabrizio», «Mariae» → «Maria», «Platonis» → «Platone». Restituisce None se la
    forma ottenuta non è un nome italiano noto (salvo gli irregolari)."""
    f = forma.rstrip(".").lower().replace("j", "i")
    radice, fin = f, ""
    for d, nuova in (("orum", "o"), ("onis", "one"), ("onem", "one"), ("ii", "io"), ("ij", "io"), ("ium", "io"),
                     ("ius", "io"), ("ae", "a"), ("am", "a"), ("um", "o"), ("us", "o"), ("is", "e"), ("i", "o"),
                     ("o", "o"), ("a", "a"), ("es", "e"), ("em", "e")):
        if f.endswith(d) and len(f) - len(d) >= 2:
            radice, fin = f[:-len(d)], nuova
            break
    for k, v in IRREGOLARI.items():
        if radice.startswith(k) or f.startswith(k):
            return v
    r = radice
    if r[:1] == "i" and r[1:2] in "aeou":
        r = "gi" + r[1:]                          # Iulius → Giulio, Iustinianus → Giustiniano, Ieremias → Geremia
    r = r.replace("ph", "f").replace("th", "t").replace("ae", "e").replace("oe", "e").replace("y", "i")
    if r.startswith("h"):
        r = r[1:]
    # -tius → -zio (Horatius → Orazio); -cius → -zio solo dopo -ri-/-a- (Fabricius → Fabrizio,
    # Bonifacius → Bonifazio), non in Lucius → Lucio
    cand_z = [re.sub(r"(t|(?<=ri)c|(?<=a)c)$", "z", r) + fin] if fin == "io" else []
    for cand in cand_z + [r + fin, (r + fin).replace("gie", "ge"), r + "o", r + "a", r + "e"]:
        c2 = cand[:1].upper() + cand[1:]
        if c2 in nomi_it:
            return c2
    return None


def leggi_tsv(nome, chiave="forma", valore="nome"):
    return {r[chiave]: r[valore] for r in csv.DictReader(open(LISTE / nome, encoding="utf-8"), delimiter="\t")}


# ---------------------------------------------------------------------------

def main():
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    ufficiali, alternativi, esteri, manuali = nomi_ufficiali_luoghi()
    # luoghi «forti» (Friuli, Veneto, capoluoghi, città): solo questi danno doppia lettura con i cognomi
    forti = {r["forma"] for r in csv.DictReader(open(LISTE / "luoghi.tsv", encoding="utf-8"), delimiter="\t")
             if r["peso"] == "forte"}
    # nomi ufficiali per forma normalizzata: «Osopo» → «Osoppo», «Ajello» → «Aiello del Friuli»
    nome_it = {r["geonameid"]: r["nome_italiano"] for r in csv.DictReader(
        open(LISTE / "geonames_it.tsv", encoding="utf-8"), delimiter="\t")} if (LISTE / "geonames_it.tsv").exists() else {}
    capoluoghi = set((LISTE / "capoluoghi.txt").read_text(encoding="utf-8").splitlines())
    per_normalizzata = {}
    for u in ufficiali:
        if u not in REGIONALI and u not in capoluoghi:
            continue                          # «Ceresetto» non deve diventare «Cereseto» (Piemonte)
        per_normalizzata.setdefault(normalizza(u), u)
        per_normalizzata.setdefault(normalizza(re.sub(r" (?:del Friuli|al Tagliamento|di Udine)$", "", u)), u)
    forme_nomi, qid_it = nomi_di_battesimo()
    nomi_it = {f for f, ll in forme_nomi.items() if any(l == "it" for l, _ in ll)}
    varianti = leggi_tsv("nomi_varianti.tsv")
    abbreviazioni = {}
    for riga in (LISTE / "abbreviazioni_nomi.txt").read_text(encoding="utf-8").splitlines():
        if riga and not riga.startswith("#") and "\t" in riga:
            f, n = riga.split("\t", 1)
            abbreviazioni[f] = n
    titoli = {t.lower() for t in estrai.leggi_parole("titoli.txt")}
    radici = estrai.radici_latine({estrai.chiave_luogo(f) for f in forme_nomi},
                                  frozenset(estrai.chiave_luogo(r["forma"]) for r in csv.DictReader(
                                      open(LISTE / "autori.tsv", encoding="utf-8"), delimiter="\t")))
    autori = leggi_tsv("autori.tsv", valore="nota")
    numeri = dict(con.execute("SELECT id, numero FROM voci"))

    occ = Counter()
    voci = defaultdict(list)
    parte_di = {}
    correzioni = {}
    for testo, tipo, voce, corr in con.execute("SELECT testo_esatto, tipo, voce, correzione FROM menzioni"):
        if tipo in ("luogo", "santo", "opera"):
            unita = [(testo, tipo)]
        else:
            unita = [(m.group(0), "persona") for m in RX_PAROLA.finditer(testo)]
            if corr:
                # correzione del curatore: le parole cambiate diventano varianti («Marlupino» → «Morlupino»)
                p_t, p_c = testo.split(), corr.split()
                if len(p_t) == len(p_c):
                    for a, b in zip(p_t, p_c):
                        a, b = a.strip("[]"), b.strip("[]")
                        if a != b and not a.startswith("["):
                            correzioni[a] = b
        for forma, t in unita:
            occ[(forma, t)] += 1
            if len(voci[(forma, t)]) < 8 and numeri[voce] not in voci[(forma, t)]:
                voci[(forma, t)].append(numeri[voce])

    # doppia lettura: parole dei nomi di persona che sono anche nomi ufficiali di luoghi del Friuli
    # e del Veneto, escluse le città («Savorgnano», «Colloredo», «Toppo», non «Udine»)
    citta = {estrai.chiave_luogo(x) for x in (LISTE / "capoluoghi.txt").read_text(encoding="utf-8").splitlines()}
    citta |= {"cividale", "gemona", "venzone", "palma", "palmanova", "sacile", "tolmezzo", "codroipo", "latisana",
              "portogruaro", "aquileia", "aquileia", "pordenone", "gorizia", "trieste", "spilimbergo", "san daniele"}
    doppie = {f for (f, t) in occ if t == "persona" and f in REGIONALI and estrai.chiave_luogo(f) not in citta
              and f[:1].isupper() and f not in manuali}

    righe = []
    for (forma, t), n in occ.items():
        nf = forma.rstrip(".")
        chiave = estrai.chiave_luogo(nf)
        parte = stato = norm = origine = rif = None
        if t in ("luogo", "santo", "opera"):
            parte = t
            if t == "opera":
                stato, norm, origine = "normale", None, "lista opere"
            elif t == "santo":
                stato, origine = "da_verificare", "santo da dirimere"
            elif forma in manuali:
                norm = manuali[forma] or forma
                stato = "normale" if norm == forma else "da_normalizzare"
                origine = "lista manuale"
            elif forma in ufficiali:
                stato, (rif, origine) = "normale", ufficiali[forma]
            elif any(u.startswith(forma + " ") for u in (forma + " del Friuli", forma + " al Tagliamento")) and \
                    (forma + " del Friuli" in ufficiali or forma + " al Tagliamento" in ufficiali):
                stato, origine = "normale", "forma breve del nome ufficiale"
            elif forma in alternativi:
                norm, rif, origine = alternativi[forma]
                norm = nome_it.get(rif, norm)     # nome italiano (Wikidata), non inglese
                breve = norm.startswith(forma + " ")
                stato = "normale" if breve else "da_normalizzare"
                if not breve and difflib.SequenceMatcher(None, normalizza(forma), normalizza(norm)).ratio() < 0.7:
                    stato, origine = "da_verificare", origine + " (corrispondenza incerta)"
                if breve:
                    origine = f"forma breve di «{norm}» ({origine})"
            elif forma in esteri:
                norm, rif, origine = esteri[forma]
                norm = nome_it.get(rif, norm)     # nome italiano: «Wien» → «Vienna»
                stato = "normale" if norm == forma else "da_normalizzare"
                if stato != "normale" and difflib.SequenceMatcher(None, normalizza(forma), normalizza(norm)).ratio() < 0.7:
                    # «Homo» → «Qom», «Sion» → «Gerusalemme», «Itan» → «Itami»: omonimie casuali da controllare
                    stato, origine = "da_verificare", "GeoNames (corrispondenza incerta)"
            elif chiave in {estrai.chiave_luogo(k) for k in ()}:
                pass
            elif normalizza(forma) in per_normalizzata:
                norm = per_normalizzata[normalizza(forma)]
                stato, origine = "da_normalizzare", "stessa forma normalizzata del nome ufficiale"
                rif = ufficiali[norm][0]
            else:
                stato, origine = "da_normalizzare", "nessuna corrispondenza nelle liste"
            if stato == "normale" and forma in doppie:
                stato = "doppia_lettura"
        else:
            if nf.lower() in estrai.PARTICELLE or forma.lower() in estrai.PARTICELLE or \
                    forma in estrai.PARTICELLE_MAIUSCOLE:
                parte, stato = "particella", "normale"
            elif forma.lower() in titoli or nf.lower() + "." in titoli:
                parte, stato = "titolo", "normale"
            elif re.fullmatch(r"[A-Z]\.", forma):
                parte, stato = "iniziale", "normale"
            elif re.fullmatch(r"[IVXLCDM]+", forma):
                parte, stato = "numerale", "normale"
            elif forma in abbreviazioni and abbreviazioni[forma] not in ("(iniziale)",):
                parte, stato, norm, origine = "nome_di_battesimo", "da_normalizzare", abbreviazioni[forma], \
                    "abbreviazione (lista manuale)"
            elif forma in forme_nomi and any(l == "it" for l, _ in forme_nomi[forma]):
                parte, stato, origine = "nome_di_battesimo", "normale", "Wikidata (it)"
                rif = next(q for l, q in forme_nomi[forma] if l == "it")
            elif forma in varianti:
                parte, stato, norm, origine = "nome_di_battesimo", "da_normalizzare", varianti[forma], \
                    "variante (lista manuale)"
            elif forma in forme_nomi:
                lingua, q = sorted(forme_nomi[forma])[0]
                parte, stato, rif = "nome_di_battesimo", "da_normalizzare", q
                norm = qid_it.get(q) or latino_italiano(forma, nomi_it)
                origine = f"Wikidata ({lingua})" + ("" if qid_it.get(q) else ", forma italiana per regola")
                if lingua == "it-derivato":
                    stato, norm, origine = "normale", None, "forma femminile derivata"
            elif chiave in radici and re.search(r"(?:ii|ij|ae|um|us|onis|onem)$", chiave):   # non «-is»: Valentinis, Portis
                base = radici[chiave]
                parte, stato = "nome_di_battesimo", "da_normalizzare"
                cand = [f for f in forme_nomi if estrai.chiave_luogo(f) == base]
                q = sorted(forme_nomi[cand[0]])[0][1] if cand else None
                norm = qid_it.get(q) if q else None
                if not norm and base in {estrai.chiave_luogo(a) for a in autori}:
                    norm = next(v for k, v in autori.items() if estrai.chiave_luogo(k) == base)
                if not norm or norm.lower() == base:
                    norm = latino_italiano(forma, nomi_it)    # mai una forma latina: «Julii» → «Giulio»
                origine = f"forma latina declinata di «{cand[0] if cand else base}»"
                rif = q
            elif forma.endswith(".") or forma.endswith("°") or len(nf) < 3 or not nf[:1].isupper():
                parte, stato = "abbreviazione", "da_verificare"      # «Acq.», «Bat.», «A.°», «a»
            elif forma in correzioni:
                parte, stato, norm, origine = "cognome", "da_normalizzare", correzioni[forma], "correzione_curatore"
            else:
                parte, stato = "cognome", "da_verificare"
                if forma in doppie:
                    stato, origine = "doppia_lettura", f"anche nome ufficiale di luogo ({ufficiali[forma][1]})"
        righe.append([forma, parte, stato, norm, origine, rif, normalizza(forma), n, ", ".join(voci[(forma, t)])])

    # cognomi: varianti grafiche che la normalizzazione già unisce, e varianti vicine (una lettera di differenza)
    gruppi = defaultdict(list)
    for r in righe:
        if r[1] == "cognome":
            gruppi[r[6]].append(r)
    for g, rr in gruppi.items():
        if len(rr) > 1:
            # le grafie si ritrovano già con la normalizzazione: nessuna forma «normalizzata» imposta
            # (Bosio non diventa Bossio); la forma di riferimento verrà dalle fonti
            altre = sorted({x[0] for x in rr})
            for r in rr:
                if r[2] == "da_verificare":
                    r[2], r[4] = "da_normalizzare", "variante grafica di " + ", ".join(a for a in altre if a != r[0])

    # decisioni del curatore e dal contesto (dati/liste/normalizzazioni_curatore.tsv): prevalgono
    decisioni = {r["forma"]: r for r in csv.DictReader(
        open(LISTE / "normalizzazioni_curatore.tsv", encoding="utf-8"), delimiter="\t")}
    for r in righe:
        d = decisioni.get(r[0])
        if not d:
            continue
        parte = d["parte"]
        if parte == "persona":
            parte = "cognome"
        r[1] = parte
        r[3] = d["forma_normalizzata"] or None
        r[4] = d["origine"] + (": " + d["nota"] if d["nota"] else "")
        r[2] = "normale" if (parte == "parola" or not r[3] or r[3] == r[0]) else "da_normalizzare"
        if parte == "parola":
            r[2] = "parola"

    con.executemany("INSERT INTO lessico (forma, parte, stato, forma_normalizzata, origine, riferimento, "
                    "gruppo_grafico, occorrenze, voci) VALUES (?,?,?,?,?,?,?,?,?)", righe)
    con.commit()
    report(con, gruppi)
    con.close()


def vicini(forme):
    """Coppie di forme normalizzate a una lettera di distanza (cancellazione), lunghe almeno 6."""
    indice = defaultdict(set)
    for f in forme:
        if len(f) >= 6 and " " not in f:
            for i in range(len(f)):
                indice[f[:i] + f[i + 1:]].add(f)
            indice[f].add(f)
    coppie = set()
    for gruppo in indice.values():
        if len(gruppo) > 1:
            g = sorted(gruppo)
            for a in g:
                for b in g:
                    if a < b and distanza_uno(a, b):
                        coppie.add((a, b))
    return coppie


def distanza_uno(a, b):
    """Vero se a e b differiscono per una sola lettera (sostituzione, aggiunta o perdita)."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    corto, lungo = (a, b) if len(a) < len(b) else (b, a)
    return any(lungo[:i] + lungo[i + 1:] == corto for i in range(len(lungo)))


def report(con, gruppi):
    q = lambda s, *a: con.execute(s, a).fetchall()  # noqa: E731
    r = ["# Fase 3 — lessico dei nomi e scrematura\n",
         "Ogni parola dei nomi di persona (e ogni forma intera di luogo e di santo) compare una volta. "
         "Le forme **già normali** non sono elencate: restano qui sotto solo quelle da normalizzare, "
         "a doppia lettura o da verificare. La ricerca userà le parti del nome: chi cerca «Giovanni da Udine» "
         "troverà «Zuan de Udene» se Zuane → Giovanni e Udene → Udine, comunque sia classificata la menzione.\n"]
    r.append("## Riepilogo\n")
    r.append("| Parte | normale | da normalizzare | doppia lettura | da verificare | Totale forme | Occorrenze |")
    r.append("|---|---|---|---|---|---|---|")
    for parte, in q("SELECT DISTINCT parte FROM lessico ORDER BY parte"):
        c = dict(q("SELECT stato, count(*) FROM lessico WHERE parte=? GROUP BY 1", parte))
        tot = sum(c.values())
        n_occ = q("SELECT sum(occorrenze) FROM lessico WHERE parte=?", parte)[0][0]
        r.append(f"| {parte} | {c.get('normale', 0)} | {c.get('da_normalizzare', 0)} | {c.get('doppia_lettura', 0)} | "
                 f"{c.get('da_verificare', 0)} | {tot} | {n_occ} |")
    r.append("")

    def sezione(titolo, nota, sql, *par, limite=None):
        rows = q(sql, *par)
        r.append(f"## {titolo}\n")
        r.append(nota + f" Forme: {len(rows)}.\n")
        r.append("| Forma | Occ. | Forma normalizzata proposta | Origine | Voci |\n|---|---|---|---|---|")
        for forma, n, norm, orig, vv in rows[:limite]:
            r.append(f"| {forma} | {n} | {norm or '—'} | {orig or ''} | {vv} |")
        if limite and len(rows) > limite:
            r.append(f"| … | | | altre {len(rows) - limite} forme nella tabella `lessico` | |")
        r.append("")

    sezione("1. Luoghi da normalizzare",
            "Forme di luogo che non sono il nome ufficiale (ISTAT, GeoNames) né una sua forma breve: "
            "latine, storiche, dialettali, o assenti dalle liste. Le corrispondenze «incerte» (forma lontana dal nome trovato: Homo → Qom) sono da controllare.",
            "SELECT forma, occorrenze, forma_normalizzata, origine, voci FROM lessico "
            "WHERE parte='luogo' AND stato IN ('da_normalizzare', 'da_verificare') ORDER BY stato, occorrenze DESC, forma")
    sezione("2. Doppia lettura: nomi ufficiali di luogo che sono anche cognomi o famiglie",
            "Normali come luogo, ma da non unire d'ufficio alla famiglia (Savorgnano luogo ≠ Savorgnan famiglia).",
            "SELECT forma, occorrenze, forma_normalizzata, origine, voci FROM lessico "
            "WHERE stato='doppia_lettura' ORDER BY occorrenze DESC, forma")
    sezione("3. Nomi di battesimo da normalizzare",
            "Abbreviazioni, forme latine (anche declinate), friulane, venete e antiche. «—» = forma italiana da trovare.",
            "SELECT forma, occorrenze, forma_normalizzata, origine, voci FROM lessico "
            "WHERE parte='nome_di_battesimo' AND stato='da_normalizzare' ORDER BY occorrenze DESC, forma")
    sezione("4. Cognomi: varianti grafiche e correzioni del curatore",
            "Grafie che la normalizzazione già unisce (Aloi/Aloj/Aloy) e correzioni tra quadre: "
            "la forma proposta è la più frequente del gruppo.",
            "SELECT forma, occorrenze, forma_normalizzata, origine, voci FROM lessico "
            "WHERE parte='cognome' AND stato='da_normalizzare' ORDER BY forma_normalizzata, forma")
    # varianti vicine
    forme = [f for (f,) in q("SELECT DISTINCT gruppo_grafico FROM lessico WHERE parte='cognome'")]
    coppie = sorted(vicini(forme))
    esempi = {g: f for g, f in q("SELECT gruppo_grafico, forma FROM lessico WHERE parte='cognome' "
                                 "ORDER BY occorrenze")}
    r.append("## 5. Cognomi simili (una lettera di differenza): candidati per la fase 4\n")
    r.append(f"Non si uniscono senza conferma (omonimi, cognomi diversi). Coppie: {len(coppie)}.\n")
    r.append(", ".join(f"{esempi[a]} ~ {esempi[b]}" for a, b in coppie) + "\n")
    n_ver = q("SELECT count(*), sum(occorrenze) FROM lessico WHERE parte='cognome' AND stato='da_verificare'")[0]
    r.append("## 6. Cognomi da verificare nelle fonti\n")
    r.append(f"{n_ver[0]} forme ({n_ver[1]} occorrenze) senza varianti nel testo: la forma di riferimento verrà "
             "dalle fonti enciclopediche (fase 5). Elenco completo nella tabella `lessico` "
             "(`parte='cognome' AND stato='da_verificare'`).\n")
    sezione("7. Santi (da dirimere)", "Forme intere.",
            "SELECT forma, occorrenze, forma_normalizzata, origine, voci FROM lessico WHERE parte='santo' "
            "ORDER BY occorrenze DESC, forma", limite=60)
    OUT.write_text("\n".join(r) + "\n", encoding="utf-8")
    print(f"Report scritto in {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
