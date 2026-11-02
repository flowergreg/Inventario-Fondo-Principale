#!/usr/bin/env python3
"""Fase 1 — Parsing dell'inventario del Fondo Principale.

Legge sorgenti/Inventario_Fondo_Principale.docx (in sola lettura) e popola
le tabelle `voci` e `annotazioni` di dati/inventario.sqlite.

Principi (vedi CLAUDE.md):
- il testo dell'inventario non si altera: `testo_integrale` conserva tutto,
  `testo` è la sola descrizione senza coda e annotazioni, e la posizione di
  ogni annotazione permette di ricostruire l'originale;
- ciò che non si sa classificare va in `residuo` e nel report.

Uso: python3 script/parser.py [percorso_docx] [percorso_sqlite]
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

import docx

RADICE = Path(__file__).resolve().parent.parent
DOCX_PREDEFINITO = RADICE / "sorgenti" / "Inventario_Fondo_Principale.docx"
DB_PREDEFINITO = RADICE / "dati" / "inventario.sqlite"
SCHEMA = RADICE / "script" / "schema.sql"
DIAGNOSTICA = RADICE / "dati" / "diagnostica_parser.json"

# ---------------------------------------------------------------------------
# Numeri di voce
# ---------------------------------------------------------------------------

# Prefisso prima della tabulazione: «542 a.», «2528 bis.», «2630/1.», «1596-bis», «4288»
RX_NUMERO_TAB = re.compile(
    r"^(?P<num>(?P<base>\d+)"
    r"(?P<suf>\s?(?:bis|ter|[a-zA-Z])\.?|-(?:bis|b)|/\d+-\d+|/\d+(?:\s?bis)?|/bis|/[a-zA-Z]|(?:-\d{3,})+)?"
    r"\.?)\t"
)
# Forma con spazio al posto della tabulazione: ammessa solo con suffisso o
# parentesi («2635/16 bis.», «3523-bis.», «3074 (con 3079).») e solo se
# coerente con la sequenza (vedi riconosci_inizio).
RX_NUMERO_SPAZIO = re.compile(
    r"^(?P<num>(?P<base>\d+)"
    r"(?P<suf>/\d+-\d+|/\d+\s?bis|/bis|-bis|\s?bis|/\d+|(?:-\d{3,})+)?"
    r"(?P<par>\s\([^)]{1,40}\))?"
    r"\.)\s"
)


# Numero omesso dichiarato nel testo: «Omissione del n.° 3078: numero omesso.»
# Il paragrafo diventa la voce di quel numero; il testo resta intatto.
RX_OMISSIONE = re.compile(r"^Omissione del n\.°\s?(?P<base>\d+)\b")


def riconosci_inizio(testo, base_corrente):
    """Restituisce (numero_originale, base, lunghezza_prefisso) se il paragrafo
    apre una voce, altrimenti None. Per i numeri omessi il prefisso è 0 (tutto
    il paragrafo è testo) e il numero originale è ricavato dal testo."""
    m = RX_OMISSIONE.match(testo)
    if m:
        return m.group("base"), int(m.group("base")), 0
    m = RX_NUMERO_TAB.match(testo)
    if m:
        return m.group("num"), int(m.group("base")), m.end()
    m = RX_NUMERO_SPAZIO.match(testo)
    if m and (m.group("suf") or m.group("par")):
        base = int(m.group("base"))
        if base_corrente <= base <= base_corrente + 2:
            return m.group("num"), base, m.end()
    return None


def analizza_numero(numero_originale, base):
    """Calcola numero ripulito, tipo, chiave di ordinamento, numeri compresi."""
    numero = numero_originale.strip()
    if numero.endswith("."):
        numero = numero[:-1].rstrip()
    resto = numero[len(str(base)):]
    sotto, variante, tipo, compresi = 0, 0, "semplice", None
    par = re.search(r"\s\(([^)]*)\)$", resto)
    if par:
        tipo = "annotato"
        resto = resto[: par.start()]
    if re.search(r"bis$", resto):
        variante = 1
        resto = re.sub(r"[\s/-]*bis$", "", resto)
        if tipo == "semplice":
            tipo = "bis"
    m_fusi = re.fullmatch(r"(?:-\d{3,})+", resto)
    m_int = re.fullmatch(r"/(\d+)-(\d+)", resto)
    m = re.fullmatch(r"/(\d+)", resto)
    if m_fusi:
        # «3202-3203-3204»: più numeri riuniti in una voce
        tipo = "fusa"
        compresi = ",".join([str(base)] + re.findall(r"\d+", resto))
    elif m_int:
        # «4107/1-5», «2639/14-22»: intervallo di sottonumeri
        sotto = int(m_int.group(1))
        tipo = "sottonumero_intervallo"
    elif m:
        s = m.group(1)
        if len(s) >= 2 and int(s) == (base + 1) % (10 ** len(s)):
            tipo = "fusa"
            compresi = f"{base},{base + 1}"
        else:
            sotto = int(s)
            tipo = "sottonumero" if variante == 0 else "sottonumero_bis"
    else:
        m = re.fullmatch(r"[\s/-]*([a-zA-Z])", resto)
        if m:
            sotto = ord(m.group(1).lower()) - ord("a") + 1
            tipo = "lettera"
        elif resto.strip():
            tipo = "anomalo"
    chiave = f"{base:05d}.{sotto:03d}.{variante}"
    return numero, tipo, chiave, compresi


# ---------------------------------------------------------------------------
# Annotazioni
# ---------------------------------------------------------------------------

ETICHETTE = r"(?:Da qui mano diversa\.\s*)?(?:Note?|Commento|A margine|Aggiunta)[^:\[\]«»]{0,40}"
RX_ANNOT_DENTRO = re.compile(r"\[(?P<etichetta>" + ETICHETTE + r"):")
# Variante con etichetta fuori dalle quadre: «Nota a margine: [«Manca…»]»
RX_ANNOT_FUORI = re.compile(r"(?P<etichetta>Note? a margine):\s*\[(?=«)")


def normalizza_tipo(etichetta):
    e = etichetta.lower()
    e = re.sub(r"^da qui mano diversa\.\s*", "", e)
    e = re.sub(r"^note\b", "nota", e)
    return re.sub(r"\W+", "_", e).strip("_")


def chiudi_quadra(testo, i):
    """Data la posizione di una «[», restituisce l'indice dopo la «]»
    corrispondente (con annidamento), o None se non è chiusa."""
    profondita = 0
    for j in range(i, len(testo)):
        if testo[j] == "[":
            profondita += 1
        elif testo[j] == "]":
            profondita -= 1
            if profondita == 0:
                return j + 1
    return None


def trova_annotazioni(testo):
    """Restituisce le annotazioni del paragrafo come lista di dizionari con
    inizio/fine nel paragrafo; segnala quelle non chiuse."""
    trovate = []
    for m in RX_ANNOT_DENTRO.finditer(testo):
        if any(a["inizio"] <= m.start() < a["fine"] for a in trovate):
            continue
        fine = chiudi_quadra(testo, m.start())
        chiusa = fine is not None
        if not chiusa:
            fine = len(testo)
        trovate.append({
            "inizio": m.start(), "fine": fine,
            "etichetta": m.group("etichetta").strip(),
            "contenuto": testo[m.end():fine - (1 if chiusa else 0)].strip(),
            "chiusa": chiusa,
        })
    for m in RX_ANNOT_FUORI.finditer(testo):
        if any(a["inizio"] <= m.start() < a["fine"] for a in trovate):
            continue
        q = m.end() - 1
        fine = chiudi_quadra(testo, q)
        chiusa = fine is not None
        if not chiusa:
            fine = len(testo)
        inizio = m.start()
        # include lo spazio che precede l'etichetta, come per le altre forme
        trovate.append({
            "inizio": inizio, "fine": fine,
            "etichetta": m.group("etichetta"),
            "contenuto": testo[q + 1:fine - (1 if chiusa else 0)].strip(),
            "chiusa": chiusa,
        })
    trovate.sort(key=lambda a: a["inizio"])
    return trovate


def togli_annotazioni(testo, annotazioni):
    """Restituisce il testo senza annotazioni e, per ciascuna, l'offset nel
    testo ripulito dove si trovava. Nessun altro carattere viene toccato."""
    pezzi, posizioni, cursore, lung = [], [], 0, 0
    for a in annotazioni:
        pezzo = testo[cursore:a["inizio"]]
        pezzi.append(pezzo)
        lung += len(pezzo)
        posizioni.append(lung)
        cursore = a["fine"]
    pezzi.append(testo[cursore:])
    return "".join(pezzi), posizioni


def annotazione_di_indice(a):
    """Annotazioni che riguardano l'indice in generale, non la voce
    (cambio di mano, catalogatori)."""
    return (a["etichetta"].lower().startswith("da qui mano diversa")
            or "catalogatore" in a["contenuto"].lower())


def etichetta_in_grassetto(paragrafo, inizio):
    """Verifica se il carattere `inizio` del paragrafo è in grassetto."""
    pos = 0
    for r in paragrafo.runs:
        if pos <= inizio < pos + len(r.text):
            return bool(r.bold)
        pos += len(r.text)
    return False


# ---------------------------------------------------------------------------
# Riga di coda
# ---------------------------------------------------------------------------

RX_SUPPORTO = re.compile(r"^(Cart|Perg|Membr|Seta|Volum|Rotol)", re.I)
RX_SUPPORTO_SOLO = re.compile(r"^(Cartaceo|Membranaceo|Pergamenaceo)\.?$")
RX_STATO = re.compile(r"^stato\s*:\s*", re.I)
RX_VOLUMI = re.compile(r"^\d|\bvol|\bfasc|\bnum\b", re.I)


def e_coda(testo_pulito):
    t = testo_pulito.strip()
    if not t:
        return False
    if re.match(r"^Provenienza\s*:", t):
        return True
    if RX_SUPPORTO_SOLO.match(t):
        return True
    if "·" in t:
        campi = [c.strip() for c in t.split("·")]
        if len(campi[0]) < 45 and (RX_SUPPORTO.match(campi[0])
                                   or any(RX_STATO.match(c) for c in campi)):
            return True
    return False


def scomponi_coda(testo_pulito):
    """Scompone una riga di coda. Restituisce (campi, residuo)."""
    t = testo_pulito.strip()
    campi = {"supporto": None, "volumi": None, "stato": None, "provenienza": []}
    residuo = []
    m = re.match(r"^Provenienza\s*:\s*(.*)$", t, re.S)
    if m:
        campi["provenienza"].append(m.group(1).strip())
        return campi, residuo
    if "·" not in t:
        campi["supporto"] = t
        return campi, residuo
    parti = [c.strip() for c in t.split("·")]
    visto_stato = False
    for i, c in enumerate(parti):
        if RX_STATO.match(c):
            campi["stato"] = RX_STATO.sub("", c)
            visto_stato = True
        elif i == 0:
            campi["supporto"] = c
        elif not visto_stato and campi["volumi"] is None and RX_VOLUMI.search(c) and len(c) < 40:
            campi["volumi"] = c
        elif not visto_stato and c.lower().startswith("in-"):
            residuo.append(c)
        elif visto_stato or i >= 1:
            campi["provenienza"].append(c)
        else:
            residuo.append(c)
    return campi, residuo


# ---------------------------------------------------------------------------
# Intestazioni di sezione
# ---------------------------------------------------------------------------

def e_intestazione(paragrafo, testo_pulito, apre_voce_dopo):
    t = testo_pulito.strip()
    if paragrafo.style.name.lower().startswith("heading"):
        return True
    # righe di chiusura: «Fine Archivio Braida», «Fine sezione «Archivio della Porta»»
    if re.match(r"^Fine\s", t) and len(t) < 70:
        return True
    if not t or not apre_voce_dopo or len(t) >= 70:
        return False
    if e_coda(t) or re.match(r"^[\d(\[-]", t):
        return False
    return not re.search(r"[.;:»\]]$", t)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def leggi(percorso_docx):
    documento = docx.Document(str(percorso_docx))
    paragrafi = documento.paragraphs
    testi = [p.text for p in paragrafi]

    # inizio: primo paragrafo «1.<tab>»
    primo = next(i for i, t in enumerate(testi) if t.startswith("1.\t"))
    preliminari = [(i, testi[i]) for i in range(primo) if testi[i].strip()]

    # 1) individua gli inizi di voce
    inizi = {}
    base = 0
    for i in range(primo, len(testi)):
        r = riconosci_inizio(testi[i], base)
        if r:
            inizi[i] = r
            base = r[1]

    def prossimo_non_vuoto(i):
        j = i + 1
        while j < len(testi) and not testi[j].strip():
            j += 1
        return j

    voci, annot_indice, intestazioni, vuoti = [], [], [], 0
    corrente = None
    for i in range(primo, len(testi)):
        t = testi[i]
        if i in inizi:
            num, b, lp = inizi[i]
            corrente = {"numero_originale": num, "base": b, "prefisso": lp,
                        "paragrafi": [i], "omesso": lp == 0}
            voci.append(corrente)
            continue
        if not t.strip():
            vuoti += 1
            continue
        ann = trova_annotazioni(t)
        pulito, _ = togli_annotazioni(t, ann)
        # numero omesso segnalato da una nota («[Nota a margine: «Omissione di un
        # numero»]» dopo la 2725): il paragrafo diventa la voce del numero saltato
        if (corrente and ann and not pulito.strip() and len(ann) == 1
                and "omissione di un numero" in ann[0]["contenuto"].lower()
                and inizi.get(prossimo_non_vuoto(i), (None, None))[1] == corrente["base"] + 2):
            b = corrente["base"] + 1
            corrente = {"numero_originale": str(b), "base": b, "prefisso": 0,
                        "paragrafi": [i], "omesso": True}
            voci.append(corrente)
            continue
        # paragrafo fatto solo di annotazioni di indice
        if ann and not pulito.strip() and all(annotazione_di_indice(a) for a in ann):
            for a in ann:
                annot_indice.append((i, a, etichetta_in_grassetto(paragrafi[i], a["inizio"]),
                                     corrente["numero_originale"] if corrente else None))
            continue
        if e_intestazione(paragrafi[i], pulito, prossimo_non_vuoto(i) in inizi):
            intestazioni.append((i, t.strip(),
                                 corrente["numero_originale"] if corrente else None))
            continue
        corrente["paragrafi"].append(i)

    # 2) ambito delle sezioni: un'intestazione vale come sezione solo se la
    # chiude una riga «Fine …» prima della successiva intestazione di apertura
    # (es. «Letteratura storica Friulana» non ha fine: non si propaga)
    ambiti = []
    for k, (i, t, _) in enumerate(intestazioni):
        if t.lower().startswith("fine"):
            continue
        succ = intestazioni[k + 1] if k + 1 < len(intestazioni) else None
        if succ and succ[1].lower().startswith("fine"):
            ambiti.append((i, succ[0], t))
    for v in voci:
        v["sezione"] = next((t for a, b, t in ambiti if a < v["paragrafi"][0] < b), None)
    return paragrafi, testi, preliminari, voci, annot_indice, intestazioni, vuoti


def costruisci_voce(v, paragrafi, testi):
    """Divide i paragrafi della voce in testo, coda e annotazioni."""
    righe_testo, code, annotazioni, residui, avvisi = [], [], [], [], []
    lung_testo = 0
    coda_vista = False
    for k, i in enumerate(v["paragrafi"]):
        t = testi[i]
        corpo = t[v["prefisso"]:] if k == 0 else t
        scarto = v["prefisso"] if k == 0 else 0
        ann = trova_annotazioni(corpo)
        pulito, posizioni = togli_annotazioni(corpo, ann)
        if k > 0 and e_coda(pulito):
            # coda: annotazioni eventuali con sede «coda»
            pos_coda = sum(len(c) + 1 for c in code)
            for a, p in zip(ann, posizioni):
                annotazioni.append(("coda", a, pos_coda + p, i,
                                    etichetta_in_grassetto(paragrafi[i], a["inizio"] + scarto)))
            code.append(pulito.strip())
            coda_vista = True
            continue
        if coda_vista and pulito.strip():
            avvisi.append(f"testo dopo la coda (par. {i}): {pulito.strip()[:80]}")
        separatore = 1 if righe_testo else 0
        if not pulito.strip() and ann:
            # paragrafo di sole annotazioni: non aggiunge righe al testo
            for a in ann:
                annotazioni.append(("testo", a, lung_testo, i,
                                    etichetta_in_grassetto(paragrafi[i], a["inizio"] + scarto)))
            continue
        base = lung_testo + separatore
        for a, p in zip(ann, posizioni):
            annotazioni.append(("testo", a, base + p, i,
                                etichetta_in_grassetto(paragrafi[i], a["inizio"] + scarto)))
        righe_testo.append(pulito)
        lung_testo = base + len(pulito)
    for _, a, _, i, _ in annotazioni:
        if not a["chiusa"]:
            residui.append(f"annotazione non chiusa (par. {i}): {a['etichetta']}")

    campi = {"supporto": [], "volumi": [], "stato": [], "provenienza": []}
    for c in code:
        f, res = scomponi_coda(c)
        for chiave in ("supporto", "volumi", "stato"):
            if f[chiave]:
                campi[chiave].append(f[chiave])
        campi["provenienza"].extend(f["provenienza"])
        residui.extend(res)
    if len(code) > 1:
        avvisi.append(f"{len(code)} righe di coda")

    def unisci(lista, sep):
        return sep.join(lista) if lista else None

    return {
        "testo_integrale": "\n".join(testi[i] for i in v["paragrafi"]),
        "testo": "\n".join(righe_testo),
        "coda": unisci(code, "\n"),
        "supporto": unisci(campi["supporto"], " | "),
        "volumi": unisci(campi["volumi"], " | "),
        "stato": unisci(campi["stato"], " | "),
        "provenienza": unisci(campi["provenienza"], " · "),
        "residuo": unisci(residui, "\n"),
        "annotazioni": annotazioni,
        "avvisi": avvisi,
    }


def main():
    percorso_docx = Path(sys.argv[1]) if len(sys.argv) > 1 else DOCX_PREDEFINITO
    percorso_db = Path(sys.argv[2]) if len(sys.argv) > 2 else DB_PREDEFINITO
    percorso_db.parent.mkdir(parents=True, exist_ok=True)
    if percorso_db.exists():
        percorso_db.unlink()

    paragrafi, testi, preliminari, voci, annot_indice, intestazioni, vuoti = leggi(percorso_docx)

    con = sqlite3.connect(percorso_db)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    avvisi_totali, annot_senza_grassetto = {}, []
    for idx, v in enumerate(voci, start=1):
        numero, tipo, chiave, compresi = analizza_numero(v["numero_originale"], v["base"])
        if v["omesso"]:
            tipo = "omesso"
        d = costruisci_voce(v, paragrafi, testi)
        con.execute(
            "INSERT INTO voci (id, numero_originale, numero, numero_base, chiave_ordinamento,"
            " tipo_numero, numeri_compresi, sezione, testo_integrale, testo, coda, supporto,"
            " volumi, stato, provenienza, paragrafo_inizio, paragrafo_fine, residuo)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (idx, v["numero_originale"], numero, v["base"], chiave, tipo, compresi,
             v["sezione"], d["testo_integrale"], d["testo"], d["coda"], d["supporto"],
             d["volumi"], d["stato"], d["provenienza"], v["paragrafi"][0],
             v["paragrafi"][-1], d["residuo"]))
        for sede, a, pos, par, grassetto in d["annotazioni"]:
            con.execute(
                "INSERT INTO annotazioni (voce, sede, tipo, etichetta_originale, testo,"
                " testo_originale, posizione, paragrafo, etichetta_grassetto)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (idx, sede, normalizza_tipo(a["etichetta"]), a["etichetta"], a["contenuto"],
                 testi[par][a["inizio"] + (v["prefisso"] if par == v["paragrafi"][0] else 0):
                            a["fine"] + (v["prefisso"] if par == v["paragrafi"][0] else 0)],
                 pos, par, int(grassetto)))
            if not grassetto:
                annot_senza_grassetto.append((v["numero_originale"], par, a["etichetta"]))
        if d["avvisi"]:
            avvisi_totali[v["numero_originale"]] = d["avvisi"]
    for par, a, grassetto, dopo in annot_indice:
        con.execute(
            "INSERT INTO annotazioni (voce, sede, tipo, etichetta_originale, testo,"
            " testo_originale, posizione, paragrafo, etichetta_grassetto)"
            " VALUES (NULL,'indice',?,?,?,?,NULL,?,?)",
            (normalizza_tipo(a["etichetta"]), a["etichetta"], a["contenuto"],
             testi[par][a["inizio"]:a["fine"]], par, int(grassetto)))
    con.commit()
    con.close()

    # diagnostica per il report
    DIAGNOSTICA.write_text(json.dumps({
        "paragrafi_totali": len(testi),
        "paragrafi_vuoti_saltati": vuoti,
        "preliminari": preliminari,
        "intestazioni": intestazioni,
        "annotazioni_indice": [(p, a["etichetta"], a["contenuto"], dopo)
                               for p, a, _, dopo in annot_indice],
        "avvisi": avvisi_totali,
        "annotazioni_senza_grassetto": annot_senza_grassetto,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Voci: {len(voci)} — database: {percorso_db}")


if __name__ == "__main__":
    main()
