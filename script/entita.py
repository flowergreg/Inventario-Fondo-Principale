#!/usr/bin/env python3
"""Fase 4 — raggruppamento delle menzioni in entità (stato «proposto»).

Parte dalla tabella `lessico` (fase 3) e dalle menzioni:

- luoghi: un'entità per forma di riferimento (nome ufficiale ISTAT/GeoNames,
  forma italiana, decisione del curatore); le corrispondenze incerte
  (stato «da_verificare») non si uniscono ad altre forme;
- santi: un'entità per forma (S. Niccolò → S. Nicola);
- persone: chiave = nomi di battesimo in forma italiana + cognomi in forma
  normalizzata (CLAUDE.md), indipendente dall'ordine (Florio Daniele = Daniele
  Florio), senza titoli né particelle semplici (di, de, da):
  · i cognomi si normalizzano solo graficamente: «Savorgnan» non diventa
    «Savorgnano», «Brazzà» non diventa «Brazzacco»; valgono solo le correzioni
    del curatore sui cognomi (Brunalleschi → Brunelleschi);
  · le menzioni con sole iniziali («G. B. Pirona») si uniscono a un'entità
    completa solo se ce n'è una e una sola compatibile; altrimenti restano a sé;
  · le menzioni di un solo nome o cognome non fanno entità (sono famiglie o
    persone non identificabili): restano senza entità e si contano nel report;
  · gli omonimi noti (Daniele Florio, Antonio Savorgnan, Della Torre) e i gruppi
    presenti in molte voci sono segnalati: un'entità può contenere più persone.

Tutte le entità hanno stato «proposto». Ogni variante registra l'origine
(testo, correzione_curatore, fonte_esterna, manuale) e il riferimento.

Scrive le tabelle `entita`, `varianti`, `identificatori` (vuota: fase 5),
aggiorna `menzioni.entita` e il report report/fase_4_entita.md.

Uso: python3 script/entita.py
"""

import csv
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalizza import normalizza  # noqa: E402
import estrai  # noqa: E402
from lessico import RX_PAROLA  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
DB = RADICE / "dati" / "inventario.sqlite"
LISTE = RADICE / "dati" / "liste"
OUT = RADICE / "report" / "fase_4_entita.md"

SCHEMA = """
DROP TABLE IF EXISTS identificatori;
DROP TABLE IF EXISTS varianti;
DROP TABLE IF EXISTS entita;
CREATE TABLE entita (
    id                 INTEGER PRIMARY KEY,
    tipo               TEXT NOT NULL,      -- persona | luogo | santo
    forma_intestazione TEXT NOT NULL,
    stato              TEXT NOT NULL DEFAULT 'proposto',   -- proposto | validato
    chiave             TEXT NOT NULL,      -- chiave di raggruppamento (per rigenerare e controllare)
    nota               TEXT                -- segnalazioni per la revisione (omonimi, iniziali, grafie diverse)
);
CREATE TABLE varianti (
    id                 INTEGER PRIMARY KEY,
    entita             INTEGER NOT NULL REFERENCES entita(id),
    forma              TEXT NOT NULL,
    forma_normalizzata TEXT NOT NULL,
    origine            TEXT NOT NULL,      -- testo | correzione_curatore | fonte_esterna | manuale
    riferimento        TEXT                -- voci (testo), fonte e codice (fonte_esterna), nota (manuale)
);
CREATE TABLE identificatori (
    entita             INTEGER NOT NULL REFERENCES entita(id),
    fonte              TEXT NOT NULL,
    codice             TEXT NOT NULL,
    url                TEXT,
    forma_autorizzata  TEXT,
    data_verifica      TEXT
);
CREATE INDEX ix_varianti_entita ON varianti(entita);
CREATE INDEX ix_varianti_norm ON varianti(forma_normalizzata);
"""

# particelle che non distinguono (Colloredo (di) Ermes = Ermes di Colloredo); gli articoli restano
# nel cognome (Della Torre ≠ Torre)
PARTICELLE_SEMPLICI = {"di", "de", "da", "d'", "d’", "de'", "de’", "e"}
OMONIMI_NOTI = {("daniele",): "florio", ("antonio",): "savorgnan"}
COGNOMI_OMONIMI = {"dela tore", "tore", "savorgnan", "florio"}
RX_SUFFISSO = re.compile(r" (?:del Friuli|al Tagliamento|di Friuli)$")


def lessico(con):
    """forma → lista di righe (parte, stato, forma_normalizzata, origine, riferimento)."""
    d = defaultdict(list)
    for f, p, s, n, o, r, k in con.execute(
            "SELECT forma, parte, stato, forma_normalizzata, origine, riferimento, occorrenze FROM lessico"):
        d[f].append((p, s, n, o, r))
        if p == "nome_di_battesimo":
            OCC_NOME[f] = OCC_NOME.get(f, 0) + k
    return d


# secondi elementi dei nomi doppi (Anna Maria, Giovanni Battista): mai cognomi dedotti
SECONDI_NOMI = {"Maria", "Battista", "Batta", "Antonio", "Domenico", "Francesco",
                "Gian", "Giovan", "Pier", "Zuan", "Zan"}      # primi elementi dei nomi doppi: mai cognomi
SECONDI_NOMI_N = {normalizza(x) for x in SECONDI_NOMI}
COPPIE_N = {"maria", "batista", "bata"}            # Anna Maria, Maria Teresa: mai spezzare
# primi elementi frequenti dei nomi doppi: «Marco Antonio», «Giorgio Antonio», «Giacomo Francesco»
PRIMI_DOPPI = {"Marco", "Giovanni", "Pietro", "Angelo", "Giorgio", "Ludovico", "Lodovico", "Filippo", "Carlo",
               "Giacomo", "Giuseppe", "Paolo", "Anton", "Luigi", "Girolamo", "Nicolò", "Bartolomeo", "Giambattista"}
ULTIMI_CANDIDATI = [0]     # parole intere che potrebbero essere il cognome, nell'ultima scomposizione
# nomi doppi fusi o abbreviati, per la chiave: Giandomenico = Gian Domenico = Giovanni Domenico
FUSI = {"gian": ["giovani"], "giovan": ["giovani"], "zuan": ["giovani"], "zan": ["giovani"],
        "giandomenico": ["giovani", "domenico"], "giambatista": ["giovani", "batista"],
        "gianbatista": ["giovani", "batista"], "gianfrancesco": ["giovani", "francesco"],
        "gianantonio": ["giovani", "antonio"], "giampietro": ["giovani", "pietro"],
        "gianpietro": ["giovani", "pietro"], "giampaolo": ["giovani", "paolo"], "gianpaolo": ["giovani", "paolo"],
        "giangiacomo": ["giovani", "giacomo"], "giangiuseppe": ["giovani", "giusepe"],
        "gianmaria": ["giovani", "maria"], "giannicolo": ["giovani", "nicolo"]}
COGNOMI_INTESTAZIONI = set()   # cognomi letti nelle intestazioni di voce (Cognome Nome)
NOMI_IN_I = {"Giovanni", "Luigi", "Dionigi", "Gianni", "Vanni", "Ercoli", "Remigi", "Ludovici", "Bernardi"}
DEDOTTI = set()            # cognomi dedotti tra parole che sono anche nomi
OCC_NOME = {}              # occorrenze delle parole classificate come nome di battesimo


def riga_persona(righe):
    """La riga del lessico che vale per una parola dentro un nome di persona."""
    for r in righe:
        if r[0] not in ("luogo", "santo", "opera"):
            return r
    return righe[0] if righe else None


def riga_luogo(righe):
    for r in righe:
        if r[0] == "luogo":
            return r
    return righe[0] if righe else None


def origine_esterna(origine):
    o = origine or ""
    return any(x in o for x in ("ISTAT", "GeoNames", "Wikidata"))


# ---------------------------------------------------------------------------
# Persone
# ---------------------------------------------------------------------------

def scomponi(testo, lex, titoli, inizio_voce=False, dedurre=True, cognomi_voce=frozenset(),
             intestazione=frozenset()):
    """Parole di un nome di persona → (nomi, iniziali, cognomi, vista).

    nomi: tuple di alternative italiane normalizzate per ogni nome di battesimo
    («Giacomo o Jacopo» → ("giacomo", "iacopo")); iniziali: lettere dei nomi
    abbreviati non risolti; cognomi: forme normalizzate (con eventuali articoli);
    vista: (nomi in forma italiana e iniziali, cognome come nel testo) per
    l'intestazione.

    inizio_voce: la menzione apre la voce, dove i compilatori scrivono di regola
    Cognome Nome (all'interno delle voci: Nome Cognome)."""
    nomi, iniziali, cognomi, vis_n, vis_c = [], [], [], [], []
    candidati = []
    numerale = False
    articolo = None
    particella = None
    # «Colloredo (di) Ermes»: la particella tra parentesi appartiene alla parola precedente
    t = re.sub(r"\(\s*(?:di|de|da|d'|d’)\s*\)", " ", testo)
    # «Pace (della) Carlo Maria», «Rò (dei) Bernardino»: l'articolo tra parentesi va col cognome
    t = re.sub(r"([A-ZÀ-Ý][\w'’]+)\s*\(\s*(della|del|dei|degli|delle|dalla|dal|dall'|de')\s*\)", r"\2 \1", t)
    # «N. H.» = Nobil Homo
    t = re.sub(r"\bN\.\s*H\.\s*", " ", t)
    # patronimico: «Alessandro di Nicolò di Manzano», «Francesco q. Taddio»: il nome del padre
    # non entra nella chiave (resta nel testo della variante)
    t = re.sub(r"\b(?:di|q\.|qm\.|quondam|fu)\s+([A-Z][\w'’]+)(?=\s+(?:di|de|da)\s+[A-Z])", " ", t)
    for m in RX_PAROLA.finditer(t.replace("(", " ").replace(")", " ")):
        w = m.group(0)
        wl = w.lower()
        if wl in PARTICELLE_SEMPLICI:
            if wl != "e":
                particella = w                   # «de Zorzi», «De Luca», «da Camino»
            continue
        if wl in estrai.PARTICELLE:              # della, del, dalla, degli…: restano col cognome
            articolo = w
            continue
        if wl in titoli or wl.rstrip(".") + "." in titoli:
            articolo = particella = None          # «del Sr. F. Barnaba»: l'articolo è del titolo
            continue
        if w[:1].islower():                      # «a» (Philippi a Turre), «e», abbreviazioni minuscole
            continue
        r = riga_persona(lex.get(w, []))
        parte = r[0] if r else ("iniziale" if re.fullmatch(r"[A-Z]\.?", w) else "cognome")
        if re.fullmatch(r"[IVXLC]{2,}\.", w):
            parte = "numerale"                  # «Onorio III.»: il punto chiude la frase
            w = w.rstrip(".")
        elif parte == "abbreviazione" and m.end() == len(t.rstrip()) and len(w.rstrip(".")) >= 4 \
                and w.rstrip(".").isalpha():
            # ultima parola con il punto di fine frase, non abbreviazione: «P. Simon Paolo Treo.»
            parte, r = "cognome", None
            w = w.rstrip(".")
        if parte in ("titolo", "parola", "opera"):
            continue
        if parte == "particella":
            articolo = w
            continue
        if parte == "numerale":
            numerale = True                     # Alessandro VIII: papa, non cognome
            nomi.append((w.lower(),))
            vis_n.append(w)
        elif parte == "abbreviazione" and (particella or articolo) and (len(w.rstrip(".")) >= 3 or not w.endswith(".")):
            # «Giacomo de Sit.»: il punto chiude la frase, «Sit» è il cognome
            c = normalizza(w)
            if articolo:
                c = normalizza(articolo) + " " + c
            cognomi.append(c)
            vis_c.append(" ".join(x for x in (particella, articolo, w.rstrip(".")) if x))
            articolo = particella = None
        elif parte in ("iniziale", "abbreviazione"):
            iniziali.append(normalizza(w)[:1])
            vis_n.append(w[:1].upper() + ".")
        elif parte == "nome_di_battesimo":
            n = r[2] or w
            if n.startswith("("):
                iniziali.append(normalizza(w)[:1])
                vis_n.append(normalizza(w)[:1].upper() + ".")
            elif " o " in n:                     # «Giacomo o Jacopo»: un nome, due alternative
                nomi.append(tuple(normalizza(x) for x in n.split(" o ")))
                vis_n.append(n)
            else:                                # «Giovanni Battista» → due nomi
                if r[1] == "normale" and w not in SECONDI_NOMI and nomi[-1:] != [("gian",)]:
                    # parola intera: potrebbe essere un cognome uguale a un nome (Wolf, Venerio, Del Bianco)
                    candidati.append((len(nomi), len(vis_n), w, articolo, particella))
                    articolo = None
                for nome in n.split():
                    for x in FUSI.get(normalizza(nome), [normalizza(nome)]):
                        nomi.append((x,))
                    vis_n.append(nome)
        else:                                   # cognome, nome_abbreviato, luogo dentro un nome, doppia lettura
            forma = w
            if r and r[3] and r[2] and (r[3].startswith("curatore") or r[3] == "correzione_curatore") \
                    and parte in ("cognome", "nome_abbreviato") and " " not in r[2]:
                forma = r[2]                    # Brunalleschi → Brunelleschi, Lir. → Liruti
            c = normalizza(forma)
            if articolo:
                c = normalizza(articolo) + " " + c
                forma = articolo + " " + forma
                articolo = None
            cognomi.append(c)
            vis_c.append(forma)
    if dedurre and not cognomi and len(iniziali) == 1 and nomi and intestazione:
        # «Z. Girolamo» nella voce «Zorzi, Mario»: il compilatore abbrevia il cognome ovvio, cioè
        # quello dell'intestazione (non un cognome qualsiasi della voce: «G. Gius. Bellina»)
        simili = [c for c in intestazione if c[:1] == iniziali[0]]
        if len(simili) == 1:
            i_v = next(k for k, v in enumerate(vis_n) if v.endswith("."))
            del vis_n[i_v]
            iniziali = []
            cognomi.append(simili[0])
            vis_c.append(simili[0].title())
            DEDOTTI.add(simili[0])
    ULTIMI_CANDIDATI[0] = len(candidati)
    if dedurre and not cognomi and candidati and (len(nomi) >= 2 or iniziali) and not numerale \
            and not re.search(r"\bS\.\s", testo) \
            and not (len(nomi) == 2 and not iniziali and not any(normalizza(c[2]) in cognomi_voce for c in candidati)
                     and (any(x[0] in COPPIE_N for x in nomi) or all(c[2] in PRIMI_DOPPI for c in candidati))):
        # le coppie di soli nomi (Marco Antonio, Anna Maria) si spezzano solo se nella voce
        # una delle due parole è cognome di altri (Paulino Francesco)
        # escluse anche le coppie di soli nomi con Maria, Battista… (Anna Maria, Maria Teresa, Ave Maria)
        # nessun cognome riconosciuto: è cognome la parola preceduta da un articolo o da una
        # particella (Del Bianco, de Zorzi); altrimenti la prima parola se la menzione apre la
        # voce (Cognome Nome: «Zeno Apostolo»), l'ultima se è all'interno (Nome Cognome: «Aldo Stella»)
        # prima ancora della posizione: la parola che nella stessa voce è cognome di altri
        # (Paulino Fabio accanto ad Alessandro e Gio. Batta Paulino)
        con_art = [c for c in candidati if c[3] or c[4]]
        in_voce = [c for c in candidati if normalizza(c[2]) in cognomi_voce]
        altrove = [c for c in candidati if normalizza(c[2]) in COGNOMI_INTESTAZIONI]
        if con_art:
            i_n, i_v, w, art, part = con_art[0]
        elif len(in_voce) == 1:
            i_n, i_v, w, art, part = in_voce[0]
        elif len(altrove) == 1:
            # cognome nell'intestazione di un'altra voce («Mariani Andrea»)
            i_n, i_v, w, art, part = altrove[0]
        elif len(in_i := [c for c in candidati if c[2].endswith("i") and c[2] not in NOMI_IN_I]) == 1:
            # i nomi italiani non finiscono in -i (salvo Giovanni, Luigi…): «Rossi Lazzaro»
            i_n, i_v, w, art, part = in_i[0]
        else:
            i_n, i_v, w, art, part = candidati[0] if inizio_voce else candidati[-1]
        del nomi[i_n]
        del vis_n[i_v]
        cognomi.append(normalizza((art + " " if art else "") + w))     # «di/de/da» fuori dalla chiave
        vis_c.append(" ".join(x for x in (part, art, w) if x))
        DEDOTTI.add(cognomi[-1])
    if not cognomi and numerale and nomi:
        cognomi.append("")                      # papi e sovrani: «Benedetto XIII»
    return nomi, iniziali, cognomi, (vis_n, " ".join(vis_c))


def intestazione_interna(testo, inizio, fine):
    """La menzione è un'intestazione interna alla voce: a capo, dopo «; » o dopo un punto
    che chiude una frase (non «prof.», «cav.», «ab.»), e seguita da punteggiatura, da «(»
    o da «a carte» («20. Delfino Daniele. Concessione…», «Cesarino Girolamo (carte…)»)."""
    prima = testo[:inizio].rstrip(" ")
    dopo = testo[fine:fine + 9]
    if prima and prima[-1] == ".":
        ultima = re.search(r"(\S+)\.$", prima)
        if ultima and not re.search(r"\d|°|\w{5,}", ultima.group(1)):
            return False                      # abbreviazione: «prof. Federico Seneca»
    elif prima and prima[-1] not in ";\n":
        return False
    return dopo == "" or dopo[:1] in ".,;:" or re.match(r"\s*\(|\s+a\s+carte", dopo) is not None


def cognome_precedente(testo, inizio, lex, titoli):
    """Cognome scritto subito prima della menzione e separato da virgola o parentesi:
    «Pecile, Gabriele Luigi», «De Rubeis (Gio. Fran.)». Solo parole che il lessico
    non dà per luogo, titolo, parola o nome di battesimo."""
    # con la virgola solo in apertura di frase («…1858). Pecile, Gabriele Luigi»), non negli elenchi
    # («cte de Beauregard, Giulio Ventura»); con la parentesi ovunque
    m = re.search(r"(?:^|[.;)\n]\s*)((?:[Dd]e|[Dd]i|[Dd]el|[Dd]ella|[Dd]a)\s+)?([A-ZÀ-Ý][\w'’]+),\s*$", testo[:inizio]) or \
        re.search(r"(?:^|[\s.;])((?:[Dd]e|[Dd]i|[Dd]el|[Dd]ella|[Dd]a)\s+)?([A-ZÀ-Ý][\w'’]+)\s*\(\s*$", testo[:inizio])
    if not m or m.group(2).lower() in titoli:
        return None
    righe = lex.get(m.group(2), [])
    esclusi = ("luogo", "titolo", "parola", "particella", "opera", "santo")
    if m.start(2) > 0:                        # in apertura di voce («Zorzi, Mario») anche una parola-nome
        esclusi += ("nome_di_battesimo",)
    if any(r[0] in esclusi for r in righe):
        return None
    return (m.group(1) or "") + m.group(2)


def scomponi_manuale(testo, lex, titoli):
    """Persona indicata dal curatore: «Rodolfo / Barnaba» = nomi / cognome esplicito."""
    if "/" not in testo:
        return scomponi(testo, lex, titoli)
    sx, dx = (x.strip() for x in testo.split("/", 1))
    nomi, iniziali, cogn, (vis_n, _) = scomponi(sx, lex, titoli, dedurre=False)
    if cogn and not nomi:                       # il curatore indica come nomi parole non riconosciute
        nomi, vis_n = [(normalizza(x),) for x in sx.split()], sx.split()
    # «Berlingero /»: persona nota solo per nome; la particella non entra nella chiave
    chiave = " ".join(x for x in normalizza(dx).split() if x not in ("di", "de", "da", "d")) if dx else ""
    return nomi, iniziali, [chiave], (vis_n, dx)


def chiave_persona(nomi, cognomi):
    return " ".join(sorted("|".join(n) for n in nomi)) + " / " + " ".join(sorted(cognomi))


def compatibile(entita_nomi, iniziali, nomi):
    """Un'entità completa è compatibile con una menzione a iniziali se ne contiene i nomi
    espliciti e se le iniziali corrispondono ai nomi restanti."""
    resto = list(entita_nomi)
    for n in nomi:
        trovato = next((e for e in resto if set(e) & set(n)), None)
        if trovato is None:
            return False
        resto.remove(trovato)
    if len(iniziali) != len(resto):
        return False
    lettere = list(iniziali)
    for e in resto:                       # ogni nome restante deve avere un'iniziale corrispondente
        x = next((l for l in lettere if any(a[:1] == l for a in e)), None)
        if x is None:
            return False
        lettere.remove(x)
    return True


# ---------------------------------------------------------------------------

def main():
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    con.execute("UPDATE menzioni SET entita = NULL")     # i collegamenti si rifanno da capo
    lex = lessico(con)
    curatore = {}
    for r in csv.DictReader(open(LISTE / "persone_curatore.tsv", encoding="utf-8"), delimiter="\t"):
        curatore[(r["voce"], r["testo"])] = [x.strip() for x in r["persone"].split("|")]
    titoli = {t.lower() for t in estrai.leggi_parole("titoli.txt")}
    numeri = dict(con.execute("SELECT id, numero FROM voci"))
    menzioni = con.execute("SELECT id, voce, testo_esatto, tipo, correzione, forma_riferimento, sede, inizio, fine FROM menzioni "
                           "ORDER BY voce, inizio").fetchall()

    entita = {}                # (tipo, chiave) → dict(intestazione, nota, varianti: {(forma, origine): set(rif)}, menzioni)
    senza = Counter()          # menzioni lasciate senza entità, per motivo
    soli = Counter()           # nomi singoli senza entità

    def ent(tipo, chiave, intestazione):
        k = (tipo, chiave)
        if k not in entita:
            entita[k] = {"intestazione": intestazione, "note": set(), "varianti": defaultdict(set),
                         "menzioni": [], "voci": set()}
        return entita[k]

    persone_iniziali = []
    apre_mid = {}      # menzioni con iniziali, da risolvere dopo le entità complete

    testi = dict(con.execute("SELECT id, testo FROM voci"))
    # cognomi di ogni voce: riconosciuti, o dedotti quando l'unica parola intera è il cognome
    # («Alessandro e Gio. Batta Paulino»)
    cognomi_voce = defaultdict(set)
    ordine_voce = defaultdict(Counter)
    intestazione_voce = defaultdict(set)     # cognomi dell'intestazione di ogni voce       # voce → quante menzioni Cognome Nome / Nome Cognome
    for voce, t, sede_m, ini in con.execute("SELECT voce, testo_esatto, sede, inizio FROM menzioni "
                                            "WHERE tipo='persona'"):
        apre = sede_m == "testo" and ini <= 2
        for x in re.split(r"\s(?:e|ed)\s", t):
            nomi, iniz, cogn, _ = scomponi(x, lex, titoli, dedurre=False)
            if cogn and nomi and not apre:
                prima = next((normalizza(w.group(0)) for w in RX_PAROLA.finditer(x)
                              if w.group(0)[:1].isupper() and w.group(0).lower() not in titoli), "")
                ordine_voce[voce]["cognome_nome" if any(c and (prima == c.split()[-1] or prima == c.split()[0])
                                                        for c in cogn) else "nome_cognome"] += 1
            if not cogn and apre and len(nomi) == 1 and not iniz:
                cogn = [nomi[0][0]]               # «Zorzi, Mario»: la prima parola della voce è il cognome
            if not cogn and apre and len(nomi) >= 2:
                c0 = scomponi(x, lex, titoli, inizio_voce=True)[2]
                COGNOMI_INTESTAZIONI.update(c for c in c0 if c and " " not in c)
            if not cogn:
                # l'intestazione della voce (Cognome Nome) o un'unica parola intera possibile
                cogn = scomponi(x, lex, titoli, inizio_voce=apre)[2] if apre or ULTIMI_CANDIDATI[0] == 1 else []
            cognomi_voce[voce].update(c for c in cogn if c)
            if apre:
                intestazione_voce[voce].update(c for c in cogn if c and " " not in c)
    for mid, voce, testo, tipo, corr, rif_forma, sede, inizio, fine in menzioni:
        # ordine Cognome Nome: all'inizio della voce, e nelle intestazioni ed elenchi interni
        # («20. Delfino Daniele. Concessione…», «…, Zorzi Carlo Maria, De Lepre…»)
        # ordine: inizio della voce → Cognome Nome; poi l'ordine prevalente nella voce;
        # poi le intestazioni interne; altrimenti Nome Cognome
        ov = ordine_voce.get(voce, Counter())
        if sede == "testo" and inizio <= 2:
            inizio_voce = True
        elif abs(ov["cognome_nome"] - ov["nome_cognome"]) >= 2:
            inizio_voce = ov["cognome_nome"] > ov["nome_cognome"]
        else:
            inizio_voce = sede == "testo" and intestazione_interna(testi.get(voce, ""), inizio, fine)
        apre_voce = sede == "testo" and inizio <= 2
        num = numeri[voce]
        tipo_eff = tipo
        if tipo in ("luogo", "santo"):
            r = riga_luogo(lex.get(testo, [])) if tipo == "luogo" else (lex.get(testo) or [None])[0]
            if r and tipo == "luogo" and r[0] != "luogo":
                # il curatore ha riclassificato la forma: «Battistella A.°» è una persona, «Alla» una parola
                if r[0] in ("parola", "abbreviazione", "opera"):
                    senza["parola o abbreviazione, non luogo"] += 1
                    continue
                if r[0] == "santo":
                    tipo_eff = "santo"
                else:
                    tipo_eff = "persona"
                    if r[2] and " " in r[2]:
                        testo_p = r[2]           # «Antonio Battistella»
                    else:
                        testo_p = r[2] or testo
            if tipo_eff == "luogo":
                if r and r[1] == "da_verificare":
                    norm, nota = testo, "corrispondenza con le fonti incerta: non unita"
                else:
                    norm, nota = (r[2] if r and r[2] else testo), None
                # forma breve e nome ufficiale insieme: Cividale = Cividale del Friuli
                e = ent("luogo", normalizza(RX_SUFFISSO.sub("", norm)), norm)
                if len(norm) > len(e["intestazione"]) and RX_SUFFISSO.search(norm):
                    e["intestazione"] = norm
                if nota:
                    e["note"].add(nota)
                e["varianti"][(testo, "testo")].add(num)
                if corr:
                    e["varianti"][(corr.strip("[] "), "correzione_curatore")].add(num)
                if norm != testo and r:
                    o = r[3] or ""
                    if origine_esterna(o):
                        e["varianti"][(norm, "fonte_esterna")].add(f"{o} {r[4] or ''}".strip())
                    else:
                        e["varianti"][(norm, "manuale")].add(o)
                e["menzioni"].append(mid)
                e["voci"].add(num)
                continue
            if tipo_eff == "santo":
                r = (lex.get(testo) or [None])[0]
                norm = r[2] if r and r[2] else testo
                e = ent("santo", normalizza(norm), norm)
                e["varianti"][(testo, "testo")].add(num)
                if norm != testo:
                    e["varianti"][(norm, "manuale")].add(r[3] or "")
                e["menzioni"].append(mid)
                e["voci"].add(num)
                continue
            testo_chiave = testo_p
        elif tipo == "opera":
            senza["opera"] += 1
            continue
        else:
            testo_chiave = corr.strip("[] ") if corr else testo

        manuale = curatore.get((num, testo)) or curatore.get(("", testo))
        if not manuale and tipo == "persona" and re.match(r"Madonna\b", testo):
            manuale = ["santo:" + testo]          # «Madonna del Carmine», «Madonna di Rosa»
        if manuale and manuale[0].startswith("santo:"):
            nome = manuale[0][6:].strip()           # «St. Claude», «San Daniele»: santi, non persone
            e = ent("santo", normalizza(nome), nome)
            e["varianti"][(testo, "testo")].add(num)
            e["menzioni"].append(mid)
            e["voci"].add(num)
            continue
        if manuale:
            # persone indicate dal curatore (dati/liste/persone_curatore.tsv)
            persone = [scomponi_manuale(x, lex, titoli) for x in manuale if x]
            if not persone:                     # non è una persona (Belle Arti, Annalia Civ.)
                senza["esclusa dal curatore"] += 1
                continue
        elif tipo == "persona" and sede == "testo" and not scomponi(testo_chiave, lex, titoli, dedurre=False)[2] \
                and (prec := cognome_precedente(testi.get(voce, ""), inizio, lex, titoli)):
            # «Pecile, Gabriele Luigi»: il cognome sta subito prima, separato da virgola o parentesi
            persone = [scomponi_manuale(f"{testo_chiave} / {prec}", lex, titoli)]
        else:
            # «Gasparo e Carlo Gozzi»: più persone in una menzione, il cognome finale vale per tutte
            parti = [x for x in re.split(r"\s(?:e|ed)\s", testo_chiave) if x.strip()]
            if len(parti) > 1 and not all(re.match(r"[A-Z]", x.strip()) for x in parti):
                parti = [testo_chiave]
            # nelle parti prima dell'ultima non si deduce il cognome: «Gian Mario e Antonio Tommasi»
            persone = [scomponi(x, lex, titoli, inizio_voce and k == 0, cognomi_voce=cognomi_voce.get(voce, frozenset()),
                                 intestazione=intestazione_voce.get(voce, frozenset()),
                                 dedurre=(k == len(parti) - 1 or len(parti) == 1))
                       for k, x in enumerate(parti)]
            if len(persone) > 1 and not persone[-1][2]:
                persone = [scomponi(x, lex, titoli, inizio_voce and k == 0, cognomi_voce=cognomi_voce.get(voce, frozenset()),
                                     intestazione=intestazione_voce.get(voce, frozenset())) for k, x in enumerate(parti)]
            if len(persone) > 1 and persone[-1][2]:
                persone = [(n, i, c or persone[-1][2], (v[0], v[1] or persone[-1][3][1])) for n, i, c, v in persone]
        valide = [p for p in persone if p[2] and (p[0] or p[1])]
        if not valide:
            senza["nome o cognome singolo"] += 1
            soli[testo] += 1
            continue
        apre_mid[mid] = apre_voce
        for nomi, iniziali, cognomi, vista in valide:
            dato = (mid, num, testo, corr, nomi, iniziali, cognomi, vista, len(valide) > 1)
            if iniziali:
                persone_iniziali.append(dato)
            else:
                aggiungi_persona(ent, *dato)

    # menzioni con iniziali: unite solo a un'entità completa compatibile e unica
    complete = defaultdict(list)          # cognomi → entità complete
    for (tipo, chiave), e in entita.items():
        if tipo == "persona":
            complete[e["cognomi"]].append(e)
    for dato in persone_iniziali:
        mid, num, testo, corr, nomi, iniziali, cognomi, vista, multipla = dato
        cand = [e for e in complete.get(tuple(sorted(cognomi)), []) if compatibile(e["nomi"], iniziali, nomi)]
        # prima si cerca il nome per intero nella stessa voce; poi in tutto l'inventario
        stessa_voce = [e for e in cand if num in e["voci"]]
        if len(stessa_voce) == 1:
            e = stessa_voce[0]
            e["note"].add("iniziali sciolte nella stessa voce")
            registra(e, *dato)
        elif len(cand) == 1:
            e = cand[0]
            e["note"].add("comprende forme con iniziali")
            registra(e, *dato)
        else:
            e = aggiungi_persona(ent, *dato)
            if len(cand) > 1:
                e["note"].add("iniziali compatibili con più persone: " +
                              "; ".join(sorted(x["intestazione"] for x in cand)))

    # coerenza tra le voci: le stesse parole con cognome dedotto in ordini diversi
    # («Gaetano Donizetti» / «Donizetti Gaetano», «Liliano Giulio» nelle voci 56–58) diventano
    # una sola entità; prevale la lettura dell'intestazione di voce, poi la più frequente
    gruppi = defaultdict(list)
    for k, e in entita.items():
        if k[0] == "persona" and e.get("cognomi") and any(c in DEDOTTI for c in e["cognomi"]):
            parole = frozenset(w for w in k[1].replace("|", " ").split() if w != "/")   # iniziali comprese
            gruppi[parole].append(k)
    for parole, kk in gruppi.items():
        if len(kk) < 2:
            continue
        kk.sort(key=lambda k: (not any(apre_mid.get(m) for m in entita[k]["menzioni"]),
                               -len(entita[k]["menzioni"])))
        dest = entita[kk[0]]
        for k in kk[1:]:
            e = entita.pop(k)
            for v, rif in e["varianti"].items():
                dest["varianti"][v] |= rif
            dest["menzioni"] += e["menzioni"]
            dest["voci"] |= e["voci"]
            dest["grafie"] |= e["grafie"]
            dest["note"] |= e["note"]
        dest["note"].add("ordine nome/cognome unificato tra le voci")

    # segnalazioni
    for (tipo, chiave), e in entita.items():
        if tipo != "persona":
            continue
        if any(c in DEDOTTI for c in e["cognomi"]):
            e["note"].add("cognome che è anche nome di battesimo: ordine dedotto")
        if any(c in COGNOMI_OMONIMI for c in e["cognomi"]):
            e["note"].add("famiglia con omonimi noti: controllare")
        grafie = {g for g in e["grafie"]}
        if len({normalizza(g) for g in grafie}) == 1 and len({g.lower() for g in grafie}) > 1:
            e["note"].add("cognome in grafie diverse: " + ", ".join(sorted(grafie)))

    scrivi(con, entita)
    report(con, entita, senza, soli)
    con.close()


def intestazione_persona(vista):
    nomi, cognome = vista
    if not cognome:
        return " ".join(nomi)
    return f"{cognome}, {' '.join(nomi)}" if nomi else cognome


def registra(e, mid, num, testo, corr, nomi, iniziali, cognomi, vista, multipla):
    e["varianti"][(testo, "testo")].add(num)
    if corr:
        e["varianti"][(corr.strip("[] "), "correzione_curatore")].add(num)
    e["menzioni"].append(mid)
    e["voci"].add(num)
    e["grafie"].add(vista[1])
    if multipla:
        e["note"].add("menzione con più persone («… e …»)")


def aggiungi_persona(ent, mid, num, testo, corr, nomi, iniziali, cognomi, vista, multipla):
    nomi_k = list(nomi) + [(i + ".",) for i in iniziali]
    e = ent("persona", chiave_persona(nomi_k, cognomi), None)
    if e["intestazione"] is None:
        e["intestazione"] = intestazione_persona(vista)
        e["nomi"] = list(nomi)
        e["cognomi"] = tuple(sorted(cognomi))
        e["grafie"] = set()
    registra(e, mid, num, testo, corr, nomi, iniziali, cognomi, vista, multipla)
    return e


def chiave_voce(n):
    m = re.match(r"(\d+)", str(n))
    return (int(m.group(1)) if m else 0, str(n))


def scrivi(con, entita):
    for (tipo, chiave), e in sorted(entita.items(), key=lambda x: (x[0][0], x[1]["intestazione"])):
        cur = con.execute("INSERT INTO entita (tipo, forma_intestazione, stato, chiave, nota) VALUES (?,?,?,?,?)",
                          (tipo, e["intestazione"], "proposto", chiave, "; ".join(sorted(e["note"])) or None))
        eid = cur.lastrowid
        e["id"] = eid
        in_testo = {f for (f, o) in e["varianti"] if o == "testo"}
        esterne = {f for (f, o) in e["varianti"] if o == "fonte_esterna"}
        for (forma, origine), rif in sorted(e["varianti"].items()):
            # la forma di riferimento si registra a parte solo se non compare già nel testo
            # (e una volta sola: la fonte esterna prevale sulla lista manuale)
            if origine in ("fonte_esterna", "manuale") and (forma in in_testo or
                                                             (origine == "manuale" and forma in esterne)):
                continue
            if origine in ("testo", "correzione_curatore"):
                r = ", ".join(str(v) for v in sorted(rif, key=chiave_voce))
            else:
                r = "; ".join(sorted(x for x in rif if x)) or None
            con.execute("INSERT INTO varianti (entita, forma, forma_normalizzata, origine, riferimento) "
                        "VALUES (?,?,?,?,?)", (eid, forma, normalizza(forma), origine, r))
        con.executemany("UPDATE menzioni SET entita=? WHERE id=?", [(eid, m) for m in e["menzioni"]])
    con.commit()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def report(con, entita, senza, soli):
    q = lambda s, *a: con.execute(s, a).fetchall()  # noqa: E731
    r = []
    w = r.append
    w("# Fase 4 — Entità proposte\n")
    w("Tutte le entità sono in stato **proposto**: diventano «validato» solo dopo la conferma del curatore. "
      "Tabelle: `entita` (tipo, forma di intestazione, chiave, nota), `varianti` (forma, forma normalizzata, "
      "origine, riferimento), `menzioni.entita`.\n")
    w("## Riepilogo\n")
    w("| Tipo | Entità | con più forme | Menzioni collegate |\n|---|---|---|---|")
    for tipo in ("persona", "luogo", "santo"):
        n = q("SELECT count(*) FROM entita WHERE tipo=?", tipo)[0][0]
        piu = q("SELECT count(*) FROM entita e WHERE tipo=? AND (SELECT count(*) FROM varianti v "
                "WHERE v.entita=e.id AND v.origine='testo') > 1", tipo)[0][0]
        m = q("SELECT count(*) FROM menzioni m JOIN entita e ON e.id=m.entita WHERE e.tipo=?", tipo)[0][0]
        w(f"| {tipo} | {n} | {piu} | {m} |")
    tot = q("SELECT count(*) FROM menzioni")[0][0]
    coll = q("SELECT count(*) FROM menzioni WHERE entita IS NOT NULL")[0][0]
    w(f"\nMenzioni collegate a un'entità: {coll} su {tot}. Senza entità: "
      + ", ".join(f"{k} {v}" for k, v in senza.most_common()) + ".\n")
    w("Le menzioni senza entità restano trovabili con la ricerca per forma normalizzata e con il lessico "
      "(fase 3): sono soprattutto cognomi o nomi isolati («Pirona», «Ciceronis»), che possono indicare "
      "una famiglia o più persone.\n")

    def elenca(titolo, spiega, righe):
        w(f"## {titolo}\n")
        if spiega:
            w(spiega + "\n")
        if not righe:
            w("_Nessuna._\n")
        for eid, intest, nota in righe:
            forme = q("SELECT forma, origine, riferimento FROM varianti WHERE entita=? ORDER BY origine, forma", eid)
            testo = "; ".join(f"{f} ({rif})" if o == "testo" else f"{f} [{o}]" for f, o, rif in forme)
            w(f"- **{intest}**" + (f" — _{nota}_" if nota else "") + f": {testo}")
        w("")

    elenca("1. Persone: iniziali compatibili con più entità",
           "Le menzioni con iniziali non sono state unite: indica a quale persona appartengono.",
           q("SELECT id, forma_intestazione, nota FROM entita WHERE tipo='persona' AND nota LIKE '%più persone%' "
             "ORDER BY forma_intestazione"))
    elenca("2. Persone: possibili omonimi",
           "Famiglie con omonimi noti: l'entità può riunire più persone.",
           q("SELECT id, forma_intestazione, nota FROM entita WHERE tipo='persona' AND "
             "(nota LIKE '%omonimi%') ORDER BY forma_intestazione"))
    elenca("3. Persone: cognome in grafie diverse",
           "Forme unite dalla normalizzazione grafica (doppie, j/i, accenti): controllare che sia la stessa persona.",
           q("SELECT id, forma_intestazione, nota FROM entita WHERE tipo='persona' AND nota LIKE '%grafie diverse%' "
             "ORDER BY forma_intestazione"))
    elenca("3 bis. Persone: cognome che è anche nome di battesimo",
           "Nessuna parola è stata riconosciuta come cognome: è stata presa la parola preceduta da un articolo "
           "(Del Bianco) o quella usata più di rado come nome accanto a un altro cognome (Wolf, Venerio, Florio). Controllare l'ordine.",
           q("SELECT id, forma_intestazione, NULL FROM entita WHERE tipo='persona' AND nota LIKE '%ordine dedotto%' "
             "ORDER BY forma_intestazione"))
    elenca("4. Persone: forme con iniziali unite a un nome completo (nella stessa voce o unico nell'inventario)", None,
           q("SELECT id, forma_intestazione, NULL FROM entita WHERE tipo='persona' AND (nota LIKE '%forme con iniziali%' OR nota LIKE '%stessa voce%') "
             "ORDER BY forma_intestazione"))
    elenca("5. Persone: altre entità con più forme (forme inverse, abbreviazioni, latino)", None,
           q("SELECT e.id, e.forma_intestazione, NULL FROM entita e WHERE tipo='persona' AND (nota IS NULL) AND "
             "(SELECT count(*) FROM varianti v WHERE v.entita=e.id AND v.origine='testo') > 1 "
             "ORDER BY forma_intestazione"))
    elenca("6. Luoghi con più forme", None,
           q("SELECT e.id, e.forma_intestazione, e.nota FROM entita e WHERE tipo='luogo' AND "
             "(SELECT count(*) FROM varianti v WHERE v.entita=e.id) > 1 ORDER BY forma_intestazione"))
    elenca("7. Santi con più forme", None,
           q("SELECT e.id, e.forma_intestazione, e.nota FROM entita e WHERE tipo='santo' AND "
             "(SELECT count(*) FROM varianti v WHERE v.entita=e.id) > 1 ORDER BY forma_intestazione"))
    w("## 8. Persone con una sola forma\n")
    n1 = q("SELECT count(*) FROM entita e WHERE tipo='persona' AND "
           "(SELECT count(*) FROM varianti v WHERE v.entita=e.id) = 1")[0][0]
    w(f"{n1} entità: elenco completo nella tabella `entita`.\n")
    w("## 9. Nomi singoli senza entità (più frequenti)\n")
    w(", ".join(f"{t} ({n})" for t, n in soli.most_common(150)) + "\n")
    OUT.write_text("\n".join(r) + "\n", encoding="utf-8")
    print(f"Report scritto in {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
