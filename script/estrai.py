#!/usr/bin/env python3
"""Fase 3 — Estrazione delle menzioni di persone, luoghi e santi.

Legge voci (testo e coda), annotazioni e segmenti da dati/inventario.sqlite e
popola le tabelle `menzioni` e `non_classificati`. Metodo a regole:

1. si individuano le sequenze di nomi: parole con l'iniziale maiuscola, unite
   da particelle (di, de', della, d', von…, anche «(di)»), iniziali e
   abbreviazioni di nomi («G. B.», «Gio.», «Ant.°»); le correzioni del
   curatore tra quadre («Marlupino [Morlupino]») restano fuori dal testo
   esatto e vanno nel campo `correzione`;
2. ogni sequenza si classifica:
   - santo («S. Giorgio», «San Daniele»…): tipo `santo`, da dirimere;
   - persona: contiene un nome di battesimo o un'iniziale, è preceduta da un
     titolo («co.», «ab.», «D.r»…) o da un articolo («il Fontanini»), è in
     ordine inverso («Loschi, Giuseppe»), segue «Raccolta/Collezione/Legato…»;
   - luogo: forma della lista dei luoghi (ISTAT, GeoNames, lista manuale),
     con un peso: le forme deboli valgono solo dopo «in», «a», «presso»…;
   - le istituzioni non si estraggono, ma il luogo che contengono sì
     («Archivio di Stato di Venezia» → Venezia);
3. ciò che non si sa classificare va in `non_classificati` (mai perso).

Ogni menzione registra voce, sede (testo | coda | annotazione), segmento,
posizione, metodo e affidabilità (alta | media | bassa).

Uso: python3 script/estrai.py [--campione]
"""

import csv
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalizza import normalizza  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
DB = RADICE / "dati" / "inventario.sqlite"
LISTE = RADICE / "dati" / "liste"

CAMPIONE = "(numero_base BETWEEN 1 AND 100) OR (numero_base BETWEEN 464 AND 497) OR numero = '2134'"

SCHEMA = """
DROP TABLE IF EXISTS menzioni;
DROP TABLE IF EXISTS non_classificati;
CREATE TABLE menzioni (
    id            INTEGER PRIMARY KEY,
    voce          INTEGER NOT NULL REFERENCES voci(id),
    sede          TEXT NOT NULL,     -- testo | coda | annotazione
    annotazione   INTEGER REFERENCES annotazioni(id),
    segmento      INTEGER REFERENCES segmenti(id),   -- solo per sede = testo
    testo_esatto  TEXT NOT NULL,     -- come nel testo, senza titoli né correzioni tra quadre
    inizio        INTEGER NOT NULL,  -- offset nel testo della sede (voci.testo, voci.coda, annotazioni.testo)
    fine          INTEGER NOT NULL,
    tipo          TEXT NOT NULL,     -- persona | luogo | santo (da dirimere) | opera
    correzione    TEXT,              -- forma tra quadre del curatore («Morlupino»)
    forma_riferimento TEXT,          -- forma di riferimento da lista manuale (opere: «Eneidi» → «Eneide»)
    metodo        TEXT NOT NULL,     -- regola che ha prodotto la classificazione
    affidabilita  TEXT NOT NULL,     -- alta | media | bassa
    entita        INTEGER            -- fase 4
);
CREATE INDEX ix_menzioni_voce ON menzioni(voce);
CREATE INDEX ix_menzioni_segmento ON menzioni(segmento);
CREATE TABLE non_classificati (
    id           INTEGER PRIMARY KEY,
    voce         INTEGER NOT NULL REFERENCES voci(id),
    sede         TEXT NOT NULL,
    annotazione  INTEGER,
    testo_esatto TEXT NOT NULL,
    inizio       INTEGER NOT NULL,
    fine         INTEGER NOT NULL
);
"""

# ---------------------------------------------------------------------------
# Liste
# ---------------------------------------------------------------------------


def leggi_parole(nome):
    parole = set()
    for riga in (LISTE / nome).read_text(encoding="utf-8").splitlines():
        if riga.startswith("#"):
            continue
        parole.update(riga.split())
    return parole


def carica_liste(corpus_parole):
    titoli = {t.lower() for t in leggi_parole("titoli.txt")}
    istituzioni = leggi_parole("parole_istituzioni.txt")
    abbreviazioni = set()
    for riga in (LISTE / "abbreviazioni_nomi.txt").read_text(encoding="utf-8").splitlines():
        if riga and not riga.startswith("#"):
            abbreviazioni.add(riga.split("\t")[0])
    # i luoghi si confrontano con la forma esatta (accenti compresi, «Però» non è
    # «Pero»), salvo j/i; la forma solo normalizzata vale come ripiego, un grado sotto
    luoghi = {}
    ordine = {"forte": 0, "medio": 1, "debole": 2}
    for r in csv.DictReader(open(LISTE / "luoghi.tsv", encoding="utf-8"), delimiter="\t"):
        for chiave, peso in ((chiave_luogo(r["forma"]), r["peso"]),
                             ("~" + r["forma_normalizzata"], {"forte": "medio"}.get(r["peso"], "debole"))):
            if chiave not in luoghi or ordine[peso] < ordine[luoghi[chiave]]:
                luoghi[chiave] = peso
    citta = {chiave_luogo(r["forma"]) for r in csv.DictReader(open(LISTE / "luoghi.tsv", encoding="utf-8"),
                                                                delimiter="\t") if r["citta"] == "1"}
    citta |= {chiave_luogo(x) for x in ("Cividale", "Gemona", "Venzone", "Palma", "Palmanova", "Sacile",
                                         "Tolmezzo", "San Daniele", "Codroipo", "Latisana", "Portogruaro",
                                         "Aquileia", "Aquileja", "Marano", "Pordenone", "Gorizia", "Trieste")}
    luoghi["__citta__"] = citta
    luoghi["__manuali__"] = {chiave_luogo(r["forma"]) for r in
                             csv.DictReader(open(LISTE / "luoghi_manuali.tsv", encoding="utf-8"), delimiter="\t")}
    luoghi["__riferimento__"] = {chiave_luogo(r["forma"]): r["riferimento"] for r in
                                 csv.DictReader(open(LISTE / "luoghi_manuali.tsv", encoding="utf-8"), delimiter="\t")
                                 if r.get("riferimento")}
    luoghi["__capoluoghi__"] = {chiave_luogo(x) for x in
                                (LISTE / "capoluoghi.txt").read_text(encoding="utf-8").splitlines() if x} | {
        chiave_luogo(x) for x in ("Vienna", "Parigi", "Londra", "Madrid", "Lisbona", "Praga", "Berlino",
                                  "Monaco", "Costantinopoli", "Lubiana", "Graz", "Salisburgo", "Innsbruck")}
    for r in csv.DictReader(open(LISTE / "luoghi_manuali.tsv", encoding="utf-8"), delimiter="\t"):
        luoghi[chiave_luogo(r["forma"])] = "forte"
        luoghi["~" + normalizza(r["forma"])] = "forte"
    nomi = set()
    for r in csv.DictReader(open(LISTE / "nomi.tsv", encoding="utf-8"), delimiter="\t"):
        nomi.add(r["forma_normalizzata"])
    # parole comuni: compaiono nel corpus anche con l'iniziale minuscola
    comuni, molto_comuni = set(), set()
    for parola, (maiuscole, minuscole) in corpus_parole.items():
        if minuscole >= 2 and minuscole >= 0.3 * (maiuscole + minuscole):
            comuni.add(parola)
        if minuscole >= 5 and minuscole >= 3 * maiuscole:
            molto_comuni.add(parola)          # «nelle», «già»: comuni anche se esiste un nome uguale
    nomi -= {n for n in nomi if n in comuni}          # «Felice», «Pace»… se usati come parole comuni
    # nomi di battesimo nella forma esatta (accenti compresi: «Già» non è «Gia»), salvo j/i
    nomi_esatti = {chiave_luogo(r["forma"]) for r in csv.DictReader(open(LISTE / "nomi.tsv", encoding="utf-8"),
                                                                    delimiter="\t")}
    autori = {chiave_luogo(r["forma"]) for r in csv.DictReader(open(LISTE / "autori.tsv", encoding="utf-8"),
                                                               delimiter="\t")}
    nomi_esatti |= autori
    nomi_tutti = set(nomi_esatti)          # anche i nomi che sono parole comuni («Domenica»)
    nomi_esatti -= {n for n in nomi_esatti if n in comuni}
    non_nomi = {p.lower() for p in leggi_parole("parole_non_nomi.txt")}
    nomi_esatti -= non_nomi
    # declinazioni latine: radici dei nomi latini e degli autori («Ciceronis» → Cicero,
    # «Boetij» → Boetius, «Tebaldi» → Tebaldo) e dei luoghi forti («Mediolani» → Mediolanum)
    radici_nomi = radici_latine(nomi_esatti, frozenset(autori))
    radici_luoghi = radici_latine({k for k, v in luoghi.items() if v == "forte" and not k.startswith("~")
                                   and isinstance(v, str) and re.fullmatch(r"[a-z]+", k)
                                   and k.endswith(("um", "a", "us"))})
    opere = {chiave_luogo(r["forma"]): r["titolo"] for r in
             csv.DictReader(open(LISTE / "opere.tsv", encoding="utf-8"), delimiter="\t")}
    return {"opere": opere, "titoli": titoli, "istituzioni": istituzioni, "abbreviazioni": abbreviazioni, "luoghi": luoghi,
            "nomi": nomi, "nomi_esatti": nomi_esatti, "comuni": comuni, "non_nomi": non_nomi,
            "molto_comuni": molto_comuni, "nomi_tutti": nomi_tutti,
            "radici_nomi": radici_nomi, "radici_luoghi": radici_luoghi}


DESINENZE = {
    "us": ("i", "o", "um", "e", "ii", "ium", "orum", "is"),
    "um": ("i", "o"),
    "a": ("ae", "am"),
    "o": ("i", "us", "um"),                              # Tebaldo → Tebaldi, Tebaldus
    "es": ("is", "i", "em"),
    "is": ("is", "i", "em"),
    "": ("is", "i", "em", "e"),                          # Caesar → Caesaris
}


def radici_latine(forme, solo_consonante=frozenset()):
    """Mappa forma declinata → forma di base, per le desinenze latine più comuni."""
    out = {}
    for f in forme:
        if len(f) < 4 or not re.fullmatch(r"[a-z]+", f):
            continue
        for fin, desinenze in DESINENZE.items():
            if fin and not f.endswith(fin):
                continue
            if not fin and f[-1] in "aeiou":
                continue
            radice = f[:-len(fin)] if fin else f
            if len(radice) < 3:
                continue
            if not fin and f not in solo_consonante:
                break                         # la declinazione dei nomi in consonante vale solo per gli autori
            for d in desinenze:
                declinata = radice + d
                if declinata != f:
                    out.setdefault(declinata, f)
            if fin == "o" and f in solo_consonante:
                for d in ("nis", "ni", "nem", "ne"):          # Cicero → Ciceronis, Plato → Platonis
                    out.setdefault(f + d, f)
            break
    return out


def chiave_luogo(forma):
    return forma.lower().replace("j", "i").replace("’", "'")


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------

RX_TOKEN = re.compile(r"""
    (?P<parola>(?:[^\W\d_]+\[[^\W\d_]+\][^\W\d_]*)          # «G[aspero]»
             |[dD]e['’](?=\s)                                          # «De' Rubeis»
             |(?:d|de|dell|degl|dall|all|nell|sull|l|L|All|Nell|Sull)['’](?=[A-ZÀ-Ý])  # «d'Abelardo», «L'Estate»: articolo staccato
             |(?:D(?:e(?:ll|gl)?|all)?['’](?=[A-ZÀ-Ý]))?[^\W\d_][^\W\d_'’]*(?:['’][^\W\d_]+)*(?:-[A-ZÀ-Ý][^\W\d_'’]*|-(?:hill|on|upon|sur|am|an|de|del|di)\b)*)  # «Franchi-Muratori», «Har Dās»
    (?P<punto>\.(?:[°ºªo](?![A-Za-z]))?|°|ª)?                   # «Gio.», «Ant.°», «Fr.co» gestito sotto
  | (?P<quadra>\[[^\]\n]{1,60}\])
  | (?P<altro>\S)
""", re.X)

PARTICELLE = {"di", "de", "de'", "de’", "del", "della", "delle", "dei", "degli", "da", "dal", "dalla",
              "d'", "d’", "dell'", "dell’", "von", "van", "der", "den", "la", "le", "lo", "du", "des", "y"}
ELISIONI = re.compile(r"^(?:d|de|dell|degl|dall|all|nell|sull|l)['’]$", re.I)   # (D', Dell' maiuscoli restano nel cognome)
TITOLI_ECCLESIASTICI = {"co.", "conte", "contessa", "marchese", "duca", "barone", "bar.", "signore", "sig.",
                        "abbate", "abbate.", "cardinale", "card.", "vescovo", "vesc.", "arcivescovo", "arciv.", "patriarca", "patr.",
                        "abate", "pievano", "piovano", "arciprete", "priore", "parroco", "vicario"}
CUE_OPERA = {"tragedia", "tragedie", "commedia", "dramma", "melodramma", "poema", "romanzo", "libretto",
             "farsa", "novella", "cantata", "oratorio", "intitolata", "intitolato", "intitolate"}
SUFFISSI_AGGETTIVO = re.compile(r"(?:ico|ica|ici|iche|ale|ali|oso|osa|osi|ose|ivo|iva|ario|aria|ese|esi|ense|ensi|"
                                r"ano|ana|ino|ina|eo|ea|ena|eno)$")
# per staccare un aggettivo prima di «di» solo i suffissi tipici degli aggettivi
# («Eroicomico di …»), non quelli frequenti nei nomi («Cechino di Caporiaco»)
SUFFISSI_AGGETTIVO_FORTI = re.compile(r"(?:ico|ica|ici|iche|ale|ali|oso|osa|osi|ose|ivo|iva|ario|aria|ense|ensi)$")
CUE_RINVIO = {"cfr.", "v.", "vedi", "vedasi"}
PARTICELLE_TRA_PARENTESI = re.compile(r"\((?:di|de|da|della|del|dalla|de')\)")
ARTICOLI_PERSONA = {"allo", "dallo", "collo", "sullo", "nello", "un", "una", "il", "lo", "del", "dello", "dal", "al", "col", "sul", "nel"}   # «il Fontanini», «del Burchiello»
PREPOSIZIONI_LUOGO_FORTI = {"in", "a", "ad", "presso", "nel", "nella", "per", "verso", "fino", "sino", "da", "dalla"}
PREPOSIZIONI_LUOGO = PREPOSIZIONI_LUOGO_FORTI | {"di", "de", "da"}
PARTICELLE_MAIUSCOLE = {"De", "Di", "Da", "Del", "Della", "Delle", "Dei", "Degli", "Dal", "Dalla", "De'", "De’",
                        "Van", "Von", "Du", "Des"}
SANTI = re.compile(r"^(?:S\.|SS\.|Ss\.|S\.ta|S\.to|San|Santo|Santa|Sant['’]|Santi|Sancti|Sancte|Sanctus|Sancta)$")
CARICHE = {"Doge", "Papa", "Imperatore", "Imperatrice", "Pontefice"}
FAMIGLIA_DEBOLE = {"eredità", "i", "dei", "ai", "dai", "coi", "nozze", "archivio", "documenti", "scritt.", "copia", "mano",
                   "manoscritti", "manoscritto", "mss.", "ms.", "carte"}
CUE_LUOGO = {"liberazione", "assedio", "battaglia", "presa", "pace", "terremoto", "guerra", "città", "terra", "villa", "castello",
             "contado", "territorio", "diocesi", "provincia", "porto", "isola", "chiesa", "parrocchia", "pieve"}
FAMIGLIA = {"domus", "famiglia", "fam.", "casa", "casato", "eredi", "nobili", "conti", "fratelli", "f.lli"}
FONDI = {"Raccolta", "Racc.", "Collezione", "Collez.", "Coll.", "Legato", "Fondo", "Dono", "Provenienza",
         "Acquisto", "Lascito", "Deposito", "Proven."}


# parole che, seguite da «di» e da un nome, non sono un luogo a sé: «Monte di Pietà», «Sacco di Udine»,
# «Mels di Colloretto» (famiglia)
LUOGO_E_PERSONA_NO = {"monte", "sacco", "mels"}


def tokenizza(testo):
    toks = []
    fine_prec = 0
    for m in RX_TOKEN.finditer(testo):
        if m.start() < fine_prec:
            continue                          # già compreso nell'abbreviazione precedente («S.ta», «Dom.co»)
        fine_prec = m.end()
        if m.group("parola"):
            parola = m.group("parola")
            fine = m.end()
            # «Fr.co», «Dom.co», «Bart.meo», «C.sse», «S.ri»: abbreviazione con lettere in esponente.
            # Un punto seguito subito da minuscole (senza spazio) non chiude la parola
            m2 = re.match(r"\.[a-zàèéìòù]+\b", testo[m.end("parola"):])
            if m2:
                fine = m.end("parola") + m2.end()
            fine_prec = fine
            toks.append({"t": testo[m.start():fine], "parola": parola, "i": m.start(), "f": fine,
                         "abbr": testo[m.start():fine] != parola,
                         # a capo prima della parola: un nome non prosegue sulla riga dopo
                         "a_capo": "\n" in testo[(toks[-1]["f"] if toks else 0):m.start()]})
        elif m.group("quadra"):
            toks.append({"t": m.group(0), "quadra": True, "i": m.start(), "f": m.end()})
        else:
            toks.append({"t": m.group(0), "altro": True, "i": m.start(), "f": m.end(),
                         "a_capo": "\n" in testo[(toks[-1]["f"] if toks else 0):m.start()]})
    # i token «parola» che finiscono con «.» sono stati presi con il punto
    return toks


def maiuscola(tok):
    p = tok.get("parola")
    if not p:
        return False
    p = re.sub(r"^[A-Za-z]{1,4}['’]", "", p)      # «D'Arcano» sì, «L'eguaglianza» no
    return p[:1].isupper()


# ---------------------------------------------------------------------------
# Estrazione
# ---------------------------------------------------------------------------


class Estrattore:
    def __init__(self, liste):
        for k, v in liste.items():
            setattr(self, k, v)

    def e_iniziale(self, tok):
        return bool(tok.get("parola")) and re.fullmatch(r"[A-Z]\.", tok["t"]) is not None

    def e_abbreviazione_nome(self, tok):
        return tok.get("t") in self.abbreviazioni or self.e_iniziale(tok)

    def e_nome_battesimo(self, tok):
        p = tok.get("parola")
        if not p:
            return False
        k = chiave_luogo(re.sub(r"\[|\]", "", p))
        return k in self.nomi_esatti or k in self.radici_nomi    # «Ciceronis», «Boetij», «Tebaldi»

    def non_nome(self, tok):
        p = tok.get("parola")
        if p and re.search(r"(?:orum|arum)$", p) and not self.e_nome_battesimo(tok):
            return True                       # «Rettoricorum», «Odarum»
        return bool(p) and p.lower() in self.non_nomi

    def e_titolo(self, tok):
        if not tok.get("parola"):
            return False
        t = tok["t"].lower()
        return t in self.titoli or tok["parola"].lower() in self.titoli or \
            re.sub(r"^(?:dell|all|dall|nell|sull|l)['’]", "", t) in self.titoli

    def comune(self, tok):
        p = tok.get("parola")
        if p and re.search(r"(?:orum|arum)$", p) and not self.e_nome_battesimo(tok):
            return True                       # «Rettoricorum», «Odarum», «Hymnorum»
        if p and p.lower() in SOLO_INIZIO_FRASE and not self.e_nome_battesimo(tok) \
                and not self.peso_luogo(p) and p.lower() not in self.nomi_esatti:
            return True                       # «Scrittura», «Cartaceo»: maiuscole solo a inizio frase
        return bool(p) and (self.non_nome(tok) or p.lower() in self.molto_comuni
                            or (p.lower() in self.comuni and not self.e_nome_battesimo(tok)))

    def peso_luogo(self, testo_span):
        testo_span = re.sub(r"\s*\[[^\]]*\]", "", testo_span).strip().rstrip(".")
        k = chiave_luogo(testo_span)
        if k in self.non_nomi:
            return None
        if k in self.radici_luoghi:
            return "forte"                    # «Mediolani», «Veronae»
        return self.luoghi.get(k) or self.luoghi.get("~" + normalizza(testo_span))

    def fine_frase(self, tok):
        """Il punto del token chiude la frase? («Sommaripa.» sì, «Gio.», «G.», «Bapt.» no)."""
        if not tok.get("abbr") or not tok["t"].endswith("."):
            return False
        breve = len(tok["parola"]) <= 4 and chiave_luogo(tok["parola"]) not in self.luoghi["__citta__"] \
            and not self.e_nome_battesimo(tok)
        # i titoli abbreviati («co.», «Rev.mo») non chiudono; un cognome che coincide con un titolo sì («De Dottori.»)
        titolo_abbreviato = self.e_titolo(tok) and (len(tok["parola"]) <= 5 or tok["parola"][:1].islower())
        return not (self.e_abbreviazione_nome(tok) or titolo_abbreviato or breve)   # «Roma.» chiude, «Bapt.» no

    def romano(self, tok):
        return bool(tok.get("parola")) and re.fullmatch(r"[IVXLCDM]+(?:-[IVXLCDM]+)*", tok["parola"]) is not None

    def particella_maiuscola(self, toks, j):
        """«De», «Della», «Di», «Da», «Dal», «De'», «Van», «Von», seguita da maiuscola."""
        t = toks[j]
        return (bool(t.get("parola")) and t["t"] in PARTICELLE_MAIUSCOLE
                and j + 1 < len(toks) and maiuscola(toks[j + 1]))

    def nome_token(self, tok):
        return self.e_nome_battesimo(tok) or self.e_abbreviazione_nome(tok)

    def sequenze(self, toks):
        """Raggruppa i token in sequenze di nomi. Restituisce liste di indici."""
        seq, k, n = [], 0, len(toks)
        while k < n:
            tok = toks[k]
            succ = toks[k + 1] if k + 1 < n else {}
            if self.particella_maiuscola(toks, k):
                avvio = True                  # «De' Rubeis», «Della Torre», «Di Colloredo»
            elif self.e_iniziale(tok) and maiuscola(succ):
                avvio = True                  # «L. Mazzei», «G. B. Ciconi»
            elif self.e_iniziale(tok) and (succ.get("parola") or "").lower() in PARTICELLE and \
                    k + 2 < n and maiuscola(toks[k + 2]):
                avvio = True                  # «A. di Brazzà»
            elif (tok.get("parola") or "") in PARTICELLE and k and self.e_titolo(toks[k - 1]) and \
                    k + 1 < n and maiuscola(succ) and not self.comune(succ):
                avvio = True                  # «al P. de Rubeis»: la particella apre il cognome
            else:
                avvio = (maiuscola(tok) and not self.e_titolo(tok) and not self.romano(tok)
                         and tok["t"] not in FONDI and tok.get("parola") not in FONDI
                         and tok["t"] not in self.istituzioni and tok.get("parola") not in self.istituzioni
                         and (not self.comune(tok) or SANTI.match(tok["t"])
                              # cognome che è anche parola comune, seguito da un nome: «Bassi G.B.»
                              or (not self.fine_frase(tok) and not self.non_nome(tok)
                                  and succ.get("parola") and self.nome_token(succ))))
                if avvio and tok["t"] in PARTICELLE_MAIUSCOLE and not self.particella_maiuscola(toks, k):
                    avvio = False             # «De consolatione»
                prec = toks[k - 1] if k else {}
                if not avvio and maiuscola(tok) and prec.get("parola") and self.e_titolo(prec) \
                        and not self.e_titolo(tok) and not self.non_nome(tok) and tok["t"] not in self.istituzioni:
                    avvio = True              # «dell'Ab. Casi»: dopo un titolo vale anche una parola comune
            vicini = " ".join(t2["t"].lower() for t2 in toks[max(0, k - 4):k])
            if not avvio and maiuscola(tok) and re.search(r"pseudonimo|soprannom|detto", vicini) and \
                    not self.non_nome(tok) and k and toks[k - 1]["t"] not in (".", "»", ";", ")"):
                avvio = True                  # «sotto il pseudonimo di «Infarinato Academico sventato»»
            if not avvio and k == 0 and maiuscola(tok) and not self.non_nome(tok) and \
                    succ.get("t") in (",", "(") and tok["t"] not in self.istituzioni:
                avvio = True                  # autore in testa alla voce: «Dotti, satire»
            if tok.get("t") in self.abbreviazioni and self.e_titolo(tok) and succ.get("parola") and \
                    self.e_abbreviazione_nome(succ):
                avvio = True                  # «Fr. Man. Heliconio»: «Fr.» è Francesco, non frate
            if not avvio and maiuscola(tok) and not self.non_nome(tok) and succ.get("parola") and \
                    tok["t"] not in FONDI and tok["t"] not in self.istituzioni and not self.e_titolo(tok) and \
                    self.e_titolo(succ) and k + 2 < n and maiuscola(toks[k + 2]) and not self.comune(toks[k + 2]):
                avvio = True                  # «Bianchi ab. Giuseppe», «Pari D.r Antongiuseppe»
            if tok.get("t") in CARICHE and not (succ.get("parola") and maiuscola(succ)):
                avvio = True                  # «al Doge di Venezia»: la carica vale come nome
            if tok.get("t") == "Fr." and succ.get("parola") and maiuscola(succ) and not self.e_nome_battesimo(succ) \
                    and not self.comune(succ):
                avvio = True                  # «Fr. Pelizzo» = Francesco Pelizzo
            if not avvio and maiuscola(tok) and k >= 2 and toks[k - 1].get("parola") == "di" and \
                    (toks[k - 2].get("t") or "").lower() in TITOLI_ECCLESIASTICI and not self.non_nome(tok):
                avvio = True                  # «bar. di Forte Olivo»: il luogo può cominciare con una parola comune
            if tok.get("t") == "P." and succ.get("t") == "P.":
                avvio = False                 # «P. P.» = Padri
            if not avvio:
                k += 1
                continue
            idx = [k]
            j = k + 1
            ultimo = tok
            while j < n and not self.fine_frase(ultimo):
                t = toks[j]
                if t.get("a_capo"):
                    break                     # «Har Dās.» / «Complessivamente 120 cc.» su righe diverse
                if t.get("quadra") and j + 1 < n and maiuscola(toks[j + 1]) and t["t"][1:2].isupper():
                    idx.append(j)             # correzione a metà nome: «Forcari [Foscari] Francesco»
                    j += 1
                    continue
                cognome_istituzione = (t["t"] in self.istituzioni and self.e_nome_battesimo(toks[idx[-1]])
                                       and not (j + 2 < n and (toks[j + 1].get("parola") or "") in PARTICELLE
                                                and maiuscola(toks[j + 2])))
                if self.non_nome(t):
                    break                     # «Ciceronis Epistolae»
                if t["t"] == "-" and j + 1 < n and maiuscola(toks[j + 1]) and toks[j + 1]["i"] - t["f"] <= 1 \
                        and t["i"] - ultimo["f"] <= 1:
                    idx += [j, j + 1]         # «Basadonna - Manin Maria»: doppio cognome
                    ultimo = toks[j + 1]
                    j += 2
                    continue
                if t.get("parola") and t["parola"][:1].islower() and j + 1 < n and maiuscola(toks[j + 1]) and \
                        chiave_luogo(t["parola"].capitalize()) in self.nomi_esatti and \
                        any(self.e_abbreviazione_nome(toks[x]) or self.e_nome_battesimo(toks[x]) for x in idx):
                    idx += [j, j + 1]         # «Elis. francesca Reggio»
                    ultimo = toks[j + 1]
                    j += 2
                    continue
                if self.e_iniziale(ultimo) and len(idx) >= 2 and self.comune(t) and not self.e_iniziale(t):
                    break                     # «Greatti G. Versi»: il punto dell'iniziale chiudeva la frase
                if maiuscola(t) and (t["t"] not in self.istituzioni or cognome_istituzione) and t["t"] not in FONDI \
                        and not self.e_titolo(t) and (
                        not self.romano(t) or len(idx) >= 1):
                    if t["t"] in PARTICELLE_MAIUSCOLE and not self.particella_maiuscola(toks, j):
                        break
                    if t["t"] in PARTICELLE_MAIUSCOLE:
                        idx += [j, j + 1]     # «Carlo De Dottori»: dopo la particella il cognome, anche se è un titolo
                        ultimo = toks[j + 1]
                        j += 2
                        continue
                    idx.append(j)
                    ultimo = t
                    j += 1
                    continue
                # titolo dentro il nome, seguito da un nome: «Beretta cav. Antonio», «Rezzonico card. C.»
                # (non con l'articolo eliso: «Griffini all'ab. Cortenovis» sono due persone)
                solo_iniz = all(self.e_iniziale(toks[x]) for x in idx)
                if self.e_titolo(t) and "'" not in t["t"] and "’" not in t["t"] and j + 1 < n \
                        and not self.fine_frase(t) and maiuscola(toks[j + 1]) and (
                            (self.nome_token(toks[j + 1]) and not any(self.e_nome_battesimo(toks[x]) for x in idx))
                            or (solo_iniz and not self.comune(toks[j + 1]))      # «M. D.r Benvenisti»
                            or (len(idx) == 1 and not self.comune(toks[j + 1]) and not self.e_titolo(toks[idx[0]]))):
                    idx += [j, j + 1]
                    ultimo = toks[j + 1]
                    j += 2
                    continue
                if t.get("parola") == "a" and j + 1 < n and maiuscola(toks[j + 1]) and \
                        self.e_nome_battesimo(toks[idx[-1]]) and re.search(r"(?:us|i|is)$", toks[idx[-1]]["parola"]) \
                        and chiave_luogo(toks[j + 1].get("parola") or "") not in self.luoghi["__citta__"]:
                    idx += [j, j + 1]         # latino: «Philippi a Turre», «Hieronymus a Valle»
                    ultimo = toks[j + 1]
                    j += 2
                    continue
                low = t.get("parola", "").lower() if t.get("parola") else t["t"]
                # particella seguita da maiuscola: «di Prampero», «de' Rubeis»
                if (t.get("parola") and (t["t"].lower() in PARTICELLE or low in PARTICELLE)
                        and j + 1 < n and maiuscola(toks[j + 1]) and not self.romano(toks[j + 1])
                        and (not self.e_titolo(toks[j + 1]) or t["t"][:1].isupper())   # «del Padre Follard» no, «De Dottori» sì
                        and toks[j + 1]["t"] not in self.istituzioni):
                    idx += [j, j + 1]
                    ultimo = toks[j + 1]
                    j += 2
                    continue
                if t["t"] == "(" and j + 2 < n and toks[j + 2]["t"] == ")" and \
                        (toks[j + 1].get("parola") or "").lower() in PARTICELLE:
                    idx += [j, j + 1, j + 2]
                    j += 3
                    continue
                break
            seq.append(idx)
            k = j
        return seq

    def classifica(self, toks, idx, testo):
        """Restituisce (tipo, metodo, affidabilita) oppure None."""
        primi = toks[idx[0]]
        parole = [toks[i] for i in idx if toks[i].get("parola")]
        maiusc = [t for t in parole if maiuscola(t)]
        span_testo = testo[toks[idx[0]]["i"]:toks[idx[-1]]["f"]]
        prec = [toks[i] for i in range(max(0, idx[0] - 3), idx[0])]
        prec_parole = [t["t"].lower() for t in prec if t.get("parola")]
        p1 = re.sub(r"^\w+['’]", "", prec_parole[-1]) if prec_parole else ""     # «sull'eredità» → «eredità»
        prec_tok = toks[idx[0] - 1] if idx[0] > 0 else None
        # articolo eliso staccato: «d'Epitteto» = «di», «dell'Argagna» = «del», «all'» = «al»
        if prec_tok is not None and ELISIONI.match(prec_tok["t"]):
            p1 = {"d": "di", "de": "di", "dell": "del", "degl": "degli", "dall": "dal", "all": "al",
                  "nell": "nel", "sull": "sul", "l": "il"}[re.sub(r"['’]$", "", prec_tok["t"].lower())]
        p2 = prec_parole[-2] if len(prec_parole) >= 2 else ""
        succ_tok = toks[idx[-1] + 1] if idx[-1] + 1 < len(toks) else None

        # parola a inizio frase o di citazione: serve qualcosa di più della lista dei nomi
        # («Deo gratias. Amen», «Iste Boetius»)
        inizio_frase = prec_tok is None or prec_tok["t"] in ("«", '"', "“") or (
            prec_tok.get("abbr") and self.fine_frase(prec_tok)) or prec_tok["t"] in (".", "!", "?")
        if re.match(r"N\.\s?B\.", span_testo):
            return None                       # «N.B.»
        if SANTI.match(primi["t"]) and len(maiusc) >= 2 and len(idx) > 1 and \
                len(toks[idx[1]].get("parola") or "") > 1:
            return "santo", "santo", "alta"   # prima di ogni altro contesto («chiesa di S. Giorgio»)
        k_span = chiave_luogo(span_testo.rstrip("."))
        citta_o_regione = k_span in self.luoghi["__citta__"] or k_span in self.luoghi["__manuali__"]
        nome_singolo = len(maiusc) == 1 and any(self.e_nome_battesimo(t) for t in maiusc)
        # titolo di un'opera: «la tragedia Sardi Liberata»
        if (p1 in CUE_OPERA or (p2 in CUE_OPERA and p1 in {"il", "la", "lo", "i", "le", "del", "della"})) \
                and self.peso_luogo(span_testo) != "forte":
            return None                       # (un luogo noto nel titolo resta luogo: «Vienna trionfante»)
        if p1.startswith("regg") or p1 == "reggimento":
            return None                       # «milite del regg.° Starai»: nome del reggimento
        if "pseudonimo" in prec_parole or p1 in ("detto", "detta", "soprannominato"):
            return "persona", "pseudonimo", "media"
        # cognome seguito da «fam.», «famª», «famiglia»: «Braida fam.», «Elti (famª)»
        dopo_span = testo[toks[idx[-1]]["f"]:toks[idx[-1]]["f"] + 12]
        if re.match(r"\s\(?(?:fam\.|famª|fam\b|famiglia|famiglie)", dopo_span):
            return "persona", "famiglia", "alta"
        # nome in testa a un paragrafo seguito dal punto, in una voce-elenco di luoghi: «Varmo. Documenti…»
        inizio_par = toks[idx[0]]["i"] == 0 or testo[toks[idx[0]]["i"] - 1] == "\n"
        if inizio_par and toks[idx[0]]["i"] > 0 and self.peso_luogo(span_testo) and \
                re.match(r"\.\s", testo[toks[idx[-1]]["f"] - 1:toks[idx[-1]]["f"] + 1]) and not nome_singolo:
            return "luogo", "intestazione_paragrafo", "media"
        if primi["t"] in CARICHE and len(maiusc) == 1:
            return "persona", "carica", "media"       # «Doge», «Papa»: univoci
        # cognome seguito da un titolo: «Zacagni ab.», «Lambertini papa», «Spinola card.», «Vacani bar.»
        if len(maiusc) == 1 and succ_tok is not None and succ_tok.get("parola") and self.e_titolo(succ_tok) \
                and not citta_o_regione and self.peso_luogo(span_testo) != "forte" and not nome_singolo:
            return "persona", "cognome_e_titolo", "media"
        # tipografo o editore: «S. Vito. Pascutti 1841»
        if len(maiusc) == 1 and not self.peso_luogo(span_testo) and \
                re.match(r"\s1[4-9]\d\d\b", testo[toks[idx[-1]]["f"]:toks[idx[-1]]["f"] + 6]):
            return "persona", "editore", "bassa"
        # «assedio di Corfù», «terremoto di …», «castello di …»: luogo
        if p1 in ("di", "de") and p2 in CUE_LUOGO and len(maiusc) <= 3:
            return "luogo", "contesto_luogo", "media"
        # autore in un elenco numerato di pagine: «136 Parini, Il pericolo», «21-51 Cimbriaco.», «12° Davalus.»
        if len(maiusc) == 1 and ((succ_tok is not None and succ_tok["t"] == ",") or toks[idx[-1]]["t"].endswith(".")) and \
                re.search(r"\d[\d\-–]*°?\s$", testo[max(0, toks[idx[0]]["i"] - 10):toks[idx[0]]["i"]]) and \
                self.peso_luogo(span_testo) != "forte":
            return "persona", "autore_in_elenco", "bassa"
        # «cardinale di Pietramala», «vescovo di Traù»: luogo
        if p1 in ("di", "de") and p2 in TITOLI_ECCLESIASTICI:     # anche «Arcivescovo d'Efeso»
            return "luogo", "sede_ecclesiastica", "media"
        # nome tra parentesi chiuse: «(Monti)», «(Parini)», «(Cortenovis)»
        if prec_tok is not None and prec_tok["t"] == "(" and succ_tok is not None and succ_tok["t"] == ")" \
                and not citta_o_regione:
            return "persona", "tra_parentesi", "media"
        # destinatario: «a Buonaparte», «lettera a Fillide», «ode a Silvia»
        if p1 in ("a", "ad", "al") and len(maiusc) == 1 and (not self.peso_luogo(span_testo) or (
                nome_singolo and not citta_o_regione)):
            return "persona", "destinatario", "bassa" if not nome_singolo else "media"
        # «del Monti», «il Parini»: articolo + nome, se non è una città o una regione
        if p1 in ARTICOLI_PERSONA and len(maiusc) == 1 and self.peso_luogo(span_testo) and not citta_o_regione \
                and p1 != "nel":
            return "persona", "articolo", "media"
        # «cfr. Mazzoliceti»
        if p1 in CUE_RINVIO and self.peso_luogo(span_testo) != "forte":
            return "persona", "rinvio", "bassa"

        if SANTI.match(primi["t"]) and len(maiusc) >= 2 and len(idx) > 1 and \
                len(toks[idx[1]].get("parola") or "") > 1:
            return "santo", "santo", "alta"
        titolo_prima = prec_tok is not None and (self.e_titolo(prec_tok) or (
            prec_tok["t"] in ("Sig.", "Sig.r", "S.r") ))
        nome = any(self.e_nome_battesimo(t) for t in maiusc)
        abbr = any(self.e_abbreviazione_nome(toks[i]) for i in idx)
        luogo = self.peso_luogo(span_testo)
        primo_k = chiave_luogo(maiusc[0]["parola"]) if maiusc else ""
        if len(maiusc) == 2 and not abbr and not SUFFISSI_AGGETTIVO.search(maiusc[1]["parola"]) and (
                primo_k in self.luoghi["__capoluoghi__"] or (
                primo_k in self.luoghi["__citta__"] and not self.e_nome_battesimo(maiusc[0]))) and \
                chiave_luogo(maiusc[1]["parola"]) not in self.nomi_esatti and len(idx) == 2:
            return "luogo+persona", "luogo_ed_editore", "media"    # «Venezia Antonelli 1848»
        if len(maiusc) >= 2 and (nome or abbr):
            # «Udine Venezia»? due luoghi forti di fila sono improbabili: si tiene persona
            return "persona", "nome_di_battesimo", "alta"
        if titolo_prima:
            return "persona", "titolo", "alta"
        # in testa alla voce di solito c'è l'autore: «Bajamonte Tiepolo.», «Dotti (Sig. K.r)», «Marzona.»
        if prec_tok is None and not citta_o_regione and self.peso_luogo(span_testo) != "forte":
            return "persona", "intestazione_voce", "media"
        if prec_tok is not None and prec_tok["t"] in FONDI or (prec_parole and prec_parole[-1] in
                                                               {x.lower() for x in FONDI}):
            return "persona", "fondo_o_provenienza", "media"     # «Dono Pagani», «Legato Toppo»
        if p1 in FAMIGLIA and prec_tok is not None and prec_tok.get("parola"):
            return "persona", "famiglia", "alta"                 # «stemma della famiglia Belgrado»
        if p1 in FAMIGLIA_DEBOLE and not citta_o_regione and prec_tok is not None and prec_tok.get("parola"):
            # plurali di gruppo («i Turchi», «dei Barnabiti», «i Provveditori»): affidabilità bassa, da rivedere
            gruppo = len(maiusc) == 1 and re.search(r"(?:ori|iti|ani|ini|esi|ensi|chi|ssi)$", maiusc[0]["parola"])
            return "persona", "famiglia", "bassa" if gruppo else "media"   # «dei Savorgnan», «scritt. Joppi»
        citta = chiave_luogo(span_testo.rstrip(".")) in self.luoghi["__citta__"]
        if len(maiusc) == 1 and nome and not citta_o_regione:
            return "persona", "solo_nome_di_battesimo", "media"   # «Morgana quel che…», «Ciceronis»
        if luogo and (luogo == "forte" or not inizio_frase):
            if luogo == "forte":
                return "luogo", "lista_luoghi_forte", "alta"
            if luogo == "medio" and p1 in PREPOSIZIONI_LUOGO:
                return "luogo", "lista_luoghi_contesto", "media"
            if luogo == "debole" and p1 in PREPOSIZIONI_LUOGO_FORTI:
                return "luogo", "lista_luoghi_contesto", "bassa"
        if len(maiusc) == 1 and nome and not luogo:
            return "persona", "solo_nome_di_battesimo", "media"
        if p1 in ARTICOLI_PERSONA or (prec_tok and re.match(r"(?i)^(?:dell|all|dall|nell|sull)['’]$", prec_tok["t"])):
            return "persona", "articolo", "media"
        if any(toks[i]["t"].lower() in PARTICELLE for i in idx) and len(maiusc) >= 2:
            return "persona", "particella", "media"
        if len(maiusc) >= 2 and chiave_luogo(maiusc[-1]["parola"]) in self.nomi_tutti and \
                chiave_luogo(maiusc[0]["parola"]) not in self.luoghi["__citta__"]:
            return "persona", "ordine_inverso", "media"     # «Volpato Morghen Domenica»
        if len(maiusc) >= 2:
            primo_luogo = self.peso_luogo(maiusc[0]["parola"])
            if primo_luogo in ("forte", "medio") and not self.e_nome_battesimo(maiusc[1]):
                if len(maiusc) == 2 and re.search(r"[io]$", maiusc[1]["parola"]) and \
                        not self.peso_luogo(maiusc[1]["parola"]):
                    return "luogo+persona", "luogo_ed_editore", "media"   # «Venezia Antonelli 1848»
                return "luogo", "luogo_con_specificazione", "media"     # «Macerata Picena»
            if inizio_frase and not nome:
                return None
            return "persona", "sequenza_maiuscole", "bassa"
        # cognome isolato dopo «di», «del», «dal»…, o tra parentesi: «di Fedro», «(Cortenovis)»
        if len(maiusc) == 1 and (not luogo or luogo == "debole") and not inizio_frase and (
                p1 in {"di", "de", "da", "del", "dal", "dello", "degli"} or (prec_tok and prec_tok["t"] == "(")):
            return "persona", "cognome_isolato", "bassa"
        if luogo == "medio" and not inizio_frase:
            return "luogo", "lista_luoghi_medio", "bassa"
        return None

    def estrai(self, testo):
        """Restituisce (menzioni, non_classificati) con offset in `testo`."""
        toks = tokenizza(testo)
        menzioni, scarti = [], []
        gia_presi = set()
        for idx in self.sequenze(toks):
            # istituzione immediatamente prima: «Biblioteca Guarneriana», «Accademia degli Sventati»
            prec = toks[idx[0] - 1] if idx[0] > 0 else None
            prec2 = toks[idx[0] - 2] if idx[0] > 1 else None
            if prec is not None and (prec["t"] in self.istituzioni or (
                    prec.get("parola", "").lower() in ("degli", "dei", "delle") and prec2 is not None
                    and prec2["t"] in self.istituzioni)):
                if not self.peso_luogo(testo[toks[idx[0]]["i"]:toks[idx[-1]]["f"]]):
                    continue
            # aggettivo prima di «di»: «Poema Eroicomico di Catuffio…» → il nome comincia dopo «di»
            if len(idx) > 2 and (toks[idx[1]].get("parola") or "").lower() in ("di", "de") and \
                    SUFFISSI_AGGETTIVO_FORTI.search(toks[idx[0]].get("parola") or "") and \
                    not self.e_nome_battesimo(toks[idx[0]]) and not self.peso_luogo(toks[idx[0]]["parola"]):
                idx = idx[2:]
            if self.e_nome_battesimo(toks[idx[0]]) and len(idx) > 2:
                coda_ini = len(idx)
                while coda_ini > 1 and self.e_iniziale(toks[idx[coda_ini - 1]]):
                    coda_ini -= 1
                if 1 < coda_ini < len(idx) and not self.e_iniziale(toks[idx[coda_ini - 1]]) and \
                        len(idx) - coda_ini >= 2:
                    idx = idx[:coda_ini]          # sigla dell'ordine religioso: «C. R. S.»
            while len(idx) > 1 and self.e_iniziale(toks[idx[-1]]) and \
                    re.match(r"\s[a-z]+\.", testo[toks[idx[-1]]["f"]:toks[idx[-1]]["f"] + 8]) and \
                    not self.e_iniziale(toks[idx[0]]):
                idx = idx[:-1]                # «Forte Olivo I.R. gen. del genio»: «I.R.» non fa parte del nome
                while len(idx) > 1 and self.e_iniziale(toks[idx[-1]]):
                    idx = idx[:-1]
            parole_span = [toks[i] for i in idx if toks[i].get("parola")]
            solo_iniziali = all(self.e_iniziale(t) for t in parole_span)
            # opera nota seguita da «di/del» + autore: «La Faonide di Saffo» → opera + persona
            if len(idx) > 2 and chiave_luogo(toks[idx[0]]["t"]) in self.opere and \
                    (toks[idx[1]].get("parola") or "").lower() in ("di", "del", "dello", "della"):
                o0, o1 = toks[idx[0]]["i"], toks[idx[0]]["f"]
                menzioni.append({"testo_esatto": testo[o0:o1], "inizio": o0, "fine": o1, "tipo": "opera",
                                 "correzione": None, "metodo": "opera_nota", "affidabilita": "alta",
                                 "forma_riferimento": self.opere[chiave_luogo(toks[idx[0]]["t"])]})
                idx = idx[2:]
            fine_span = toks[idx[-1]]["f"]
            if solo_iniziali and re.match(r"[a-z]", testo[fine_span:fine_span + 1]):
                continue                      # «M.S.S.i» = manoscritti
            if solo_iniziali and len(parole_span) >= 2 and re.match(r"\s[a-z]+\.", testo[fine_span:fine_span + 8]):
                continue                      # «I.R. gab. Numis.», «I.R. gen. del genio»
            prima_span = testo[max(0, toks[idx[0]]["i"] - 3):toks[idx[0]]["i"]]
            if (solo_iniziali or all(re.fullmatch(r"[MDCLXVI]\.", t["t"]) for t in parole_span)) and \
                    all(re.fullmatch(r"[MDCLXVI]\.?", t["t"]) for t in parole_span) and \
                    (len(parole_span) >= 3 or re.search(r"\d\s$", prima_span)):
                continue                      # «il dì 14 M.D.I.C.»: anno in cifre romane
            if solo_iniziali and len(parole_span) >= 2 and \
                    re.match(r"\s?[A-ZÀ-Ý]\w+", testo[fine_span:fine_span + 20]) and \
                    self.non_nome({"parola": re.match(r"\s?(\w+)", testo[fine_span:]).group(1)}):
                continue                      # «I. R. Censura»
            if solo_iniziali and re.match(r"\s?\([A-ZÀ-Ý][\w'’]+\)", testo[fine_span:]):
                # «A.M.C. (Cortenovis)»: sigla e nome tra parentesi, una sola persona
                fine_par = fine_span + testo[fine_span:].index(")") + 1
                menzioni.append({"testo_esatto": testo[toks[idx[0]]["i"]:fine_par], "inizio": toks[idx[0]]["i"],
                                 "fine": fine_par, "tipo": "persona", "correzione": None,
                                 "metodo": "sigla_e_nome", "affidabilita": "alta"})
                gia_presi.add(fine_span + testo[fine_span:].index("(") + 1)
                continue
            if toks[idx[0]]["i"] in gia_presi:
                continue
            # inversione «Loschi, Giuseppe»: si unisce alla sequenza successiva di soli nomi
            esito = self.classifica(toks, idx, testo)
            i0, i1 = toks[idx[0]]["i"], toks[idx[-1]]["f"]
            if self.fine_frase(toks[idx[-1]]):
                i1 -= 1                       # il punto fermo non fa parte del nome
            correzione = None
            dopo = idx[-1] + 1
            interne = [toks[i] for i in idx if toks[i].get("quadra")]
            if interne:
                # correzione a metà nome: la forma corretta sostituisce quella del testo
                parti = [toks[i] for i in idx]
                corr = []
                for k2, t2 in enumerate(parti):
                    if k2 + 1 < len(parti) and parti[k2 + 1].get("quadra"):
                        continue
                    corr.append(t2["t"][1:-1] if t2.get("quadra") else t2["t"])
                correzione = " ".join(corr)
            elif dopo < len(toks) and toks[dopo].get("quadra"):
                contenuto = toks[dopo]["t"][1:-1].strip()
                if contenuto[:1].isupper() and not re.match(r"(?i)sic|nota|commento", contenuto):
                    # la forma corretta è il nome intero, con le ultime parole sostituite:
                    # «P. Tisabesano Secchia [Sechia]» → «P. Tisabesano Sechia»
                    parole_nome = testo[i0:i1].split()
                    n_corr = len(contenuto.split())
                    correzione = " ".join(parole_nome[:-n_corr] + [contenuto]) if len(parole_nome) > n_corr \
                        else contenuto
                    if esito is None:
                        esito = ("persona", "correzione_curatore", "media")
            if esito is None:
                scarti.append((testo[i0:i1], i0, i1))
                continue
            tipo, metodo, aff = esito
            if tipo == "luogo" and self.peso_luogo(testo[i0:i1]) == "forte":
                aff = "alta"                  # «Udine» trovato per contesto resta un luogo certo
            prima_parola = toks[idx[0] - 1]["t"].lower() if idx[0] else ""
            parti_nozze = [toks[i] for i in idx if toks[i].get("parola")]
            if prima_parola == "nozze" and len(parti_nozze) >= 2 and all(maiuscola(t) for t in parti_nozze) and \
                    not any(self.e_nome_battesimo(t) for t in parti_nozze):
                for t in parti_nozze:             # «nozze Mauroner Antivari»: due famiglie
                    menzioni.append({"testo_esatto": t["parola"], "inizio": t["i"], "fine": t["i"] + len(t["parola"]),
                                     "tipo": "persona", "correzione": None, "metodo": "nozze",
                                     "affidabilita": "media"})
                continue
            if tipo == "luogo+persona":
                spazio = testo.index(" ", i0)
                menzioni.append({"testo_esatto": testo[i0:spazio], "inizio": i0, "fine": spazio, "tipo": "luogo",
                                 "correzione": None, "metodo": metodo, "affidabilita": "alta"})
                menzioni.append({"testo_esatto": testo[spazio + 1:i1], "inizio": spazio + 1, "fine": i1,
                                 "tipo": "persona", "correzione": correzione, "metodo": metodo, "affidabilita": "media"})
                continue
            # persona che termina con un luogo seguito da una data: «C. Aless. Carnier Portogruaro 1842»
            parole_m = [toks[i] for i in idx if toks[i].get("parola")]
            if tipo == "persona" and len(parole_m) >= 3 and self.peso_luogo(parole_m[-1]["parola"]) == "forte" and \
                    re.match(r"\s\d", testo[i1:i1 + 2]) and not self.e_nome_battesimo(parole_m[-1]):
                ul = parole_m[-1]
                fine_p = parole_m[-2]["i"] + len(parole_m[-2]["t"])
                menzioni.append({"testo_esatto": testo[i0:fine_p], "inizio": i0, "fine": fine_p, "tipo": "persona",
                                 "correzione": correzione, "metodo": metodo, "affidabilita": aff})
                menzioni.append({"testo_esatto": ul["parola"], "inizio": ul["i"], "fine": ul["i"] + len(ul["parola"]),
                                 "tipo": "luogo", "correzione": None, "metodo": "luogo_della_lettera",
                                 "affidabilita": "media"})
                continue
            # famiglia + «di» + luogo: «dei Rizzi di Colugna» → famiglia Rizzi + luogo Colugna
            if tipo == "persona" and metodo == "famiglia":
                m_f = re.search(r"\s(?:di|da)\s([A-ZÀ-Ý][\w'’]+)$", testo[i0:i1])
                if m_f and self.peso_luogo(m_f.group(1)):
                    menzioni.append({"testo_esatto": testo[i0:i0 + m_f.start()], "inizio": i0, "fine": i0 + m_f.start(),
                                     "tipo": "persona", "correzione": None, "metodo": metodo, "affidabilita": aff})
                    a2 = i0 + m_f.start(1)
                    menzioni.append({"testo_esatto": testo[a2:i1], "inizio": a2, "fine": i1, "tipo": "luogo",
                                     "correzione": None, "metodo": "luogo_della_famiglia", "affidabilita": "media"})
                    continue
            # luogo seguito da nome e cognome: «Patriarca d'Aquileja Giovanni Grimani» → luogo + persona
            parole_m = [toks[i] for i in idx if toks[i].get("parola")]
            if tipo != "santo" and len(parole_m) >= 3 and self.peso_luogo(parole_m[0]["parola"]) == "forte" and \
                    not self.e_nome_battesimo(parole_m[0]) and self.e_nome_battesimo(parole_m[1]):
                l0, l1 = parole_m[0]["i"], parole_m[0]["i"] + len(parole_m[0]["parola"])
                menzioni.append({"testo_esatto": testo[l0:l1], "inizio": l0, "fine": l1, "tipo": "luogo",
                                 "correzione": None, "metodo": "luogo_prima_del_nome", "affidabilita": "media"})
                menzioni.append({"testo_esatto": testo[parole_m[1]["i"]:i1], "inizio": parole_m[1]["i"], "fine": i1,
                                 "tipo": "persona", "correzione": correzione, "metodo": metodo, "affidabilita": aff})
                continue
            # santo seguito da «di» + persona: «panegirici di S. Tommaso di Alberto Unaccio»
            if tipo == "santo":
                m_p = re.search(r"\s(?:di|de)\s([A-ZÀ-Ý][\w'’]+)(?:\s[A-ZÀ-Ý].*)?$", testo[i0:i1])
                if m_p and chiave_luogo(m_p.group(1)) in self.nomi_esatti and \
                        chiave_luogo(m_p.group(1)) not in self.luoghi["__citta__"]:
                    a2 = i0 + m_p.start(1)
                    menzioni.append({"testo_esatto": testo[i0:i0 + m_p.start()], "inizio": i0,
                                     "fine": i0 + m_p.start(), "tipo": "santo", "correzione": None,
                                     "metodo": "santo", "affidabilita": "alta"})
                    menzioni.append({"testo_esatto": testo[a2:i1], "inizio": a2, "fine": i1, "tipo": "persona",
                                     "correzione": correzione, "metodo": "nome_dopo_santo", "affidabilita": "media"})
                    continue
            # santo dopo un nome: «Giusto Fontanini di San Daniele» → persona + santo (da dirimere)
            if tipo == "persona":
                m_s = re.search(r"\s(?:di|da)\s((?:S\.|SS\.|S\.ta|S\.to|San|Santo|Santa|Sant['’])\s?[A-ZÀ-Ý].*)$",
                                testo[i0:i1])
                if m_s:
                    menzioni.append({"testo_esatto": testo[i0:i0 + m_s.start()], "inizio": i0,
                                     "fine": i0 + m_s.start(), "tipo": "persona", "correzione": correzione,
                                     "metodo": metodo, "affidabilita": aff})
                    a2 = i0 + m_s.start(1)
                    menzioni.append({"testo_esatto": testo[a2:i1], "inizio": a2, "fine": i1, "tipo": "santo",
                                     "correzione": None, "metodo": "santo_dopo_nome", "affidabilita": "alta"})
                    continue
            # persona seguita da «di/da» + città: provenienza, non predicato nobiliare
            # («libreria Pagani di Udine» → Pagani + Udine). I predicati («Ermes di Colloredo») restano uniti.
            if tipo == "persona":
                m_c = re.search(r"\s(?:di|da)\s([A-ZÀ-Ý][\w'’]+(?:\s(?:del|di|al)?\s?[A-ZÀ-Ý][\w'’]+){0,2})$",
                                testo[i0:i1])
                if m_c and chiave_luogo(m_c.group(1)) in self.luoghi["__citta__"] and \
                        len(testo[i0:i0 + m_c.start()].split()) >= 1:
                    menzioni.append({"testo_esatto": testo[i0:i0 + m_c.start()], "inizio": i0,
                                     "fine": i0 + m_c.start(), "tipo": "persona", "correzione": correzione,
                                     "metodo": metodo, "affidabilita": aff})
                    a2 = i0 + m_c.start(1)
                    menzioni.append({"testo_esatto": testo[a2:i1], "inizio": a2, "fine": i1, "tipo": "luogo",
                                     "correzione": None, "metodo": "provenienza_citta", "affidabilita": "alta"})
                    continue
            menzioni.append({"testo_esatto": testo[i0:i1], "inizio": i0, "fine": i1, "tipo": tipo,
                             "correzione": correzione, "metodo": metodo, "affidabilita": aff})
        menzioni = self.unisci_inversioni(menzioni, testo)
        for m in menzioni:
            titolo = self.opere.get(chiave_luogo(m["testo_esatto"]))
            if titolo:
                m.update(tipo="opera", metodo="opera_nota", affidabilita="alta", forma_riferimento=titolo)
        for s_t, a0, a1 in list(scarti):
            titolo = self.opere.get(chiave_luogo(s_t))
            if titolo:
                scarti.remove((s_t, a0, a1))
                menzioni.append({"testo_esatto": s_t, "inizio": a0, "fine": a1, "tipo": "opera", "correzione": None,
                                 "metodo": "opera_nota", "affidabilita": "alta", "forma_riferimento": titolo})
        for m in menzioni:
            if m["tipo"] == "persona" and testo[m["inizio"] - 1:m["inizio"]] == "(" and \
                    testo[m["fine"]:m["fine"] + 2] == ") ":
                seguito = [x for x in scarti if x[1] == m["fine"] + 2]
                if seguito:
                    scarti.remove(seguito[0])
                    m.update(testo_esatto=testo[m["inizio"] - 1:seguito[0][2]], inizio=m["inizio"] - 1,
                             fine=seguito[0][2], metodo="nome_tra_parentesi")
        # locuzioni devozionali: «Cuor di Gesù», «Sacro Cuore»: non sono nomi
        for m_l in re.finditer(r"(?:Cuor|Cuore|Sacro Cuore|Nome)\s+di\s+(?:Gesù|Maria)", testo):
            menzioni = [m for m in menzioni if not (m_l.start() <= m["inizio"] < m_l.end())]
            scarti = [x for x in scarti if not (m_l.start() <= x[1] < m_l.end())]
        for m in menzioni:
            if m["tipo"] == "luogo" and not m.get("forma_riferimento"):
                rif = self.luoghi["__riferimento__"].get(chiave_luogo(m["testo_esatto"]))
                if rif and rif != m["testo_esatto"]:
                    m["forma_riferimento"] = rif      # «Gerosolima» → Gerusalemme
        # elenchi separati da virgole con prevalenza di persone: anche gli elementi incerti sono persone
        # («poesie del Navagero, Muzio, Castiglione, Sanchio, Molza…»)
        elementi = sorted([("m", m["inizio"], m["fine"], m) for m in menzioni] +
                          [("s", a0, a1, (s_t, a0, a1)) for s_t, a0, a1 in scarti], key=lambda x: x[1])
        serie, corrente = [], []
        for el in elementi:
            if corrente and re.fullmatch(r",\s|\s(?:e|ed)\s", testo[corrente[-1][2]:el[1]]):
                corrente.append(el)
            else:
                if len(corrente) >= 3:
                    serie.append(corrente)
                corrente = [el]
        if len(corrente) >= 3:
            serie.append(corrente)
        for sr in serie:
            persone = sum(1 for el in sr if el[0] == "m" and el[3]["tipo"] == "persona")
            luoghi_certi = sum(1 for el in sr if el[0] == "m" and el[3]["tipo"] == "luogo" and (
                chiave_luogo(el[3]["testo_esatto"]) in self.luoghi["__citta__"]
                or chiave_luogo(el[3]["testo_esatto"]) in self.luoghi["__manuali__"]))
            if persone < 2 or persone <= luoghi_certi:
                continue
            for el in sr:
                if el[0] == "s":
                    s_t, a0, a1 = el[3]
                    scarti.remove(el[3])
                    menzioni.append({"testo_esatto": s_t, "inizio": a0, "fine": a1, "tipo": "persona",
                                     "correzione": None, "metodo": "elenco_di_persone", "affidabilita": "media"})
                elif el[3]["tipo"] == "luogo" and " " not in el[3]["testo_esatto"] and \
                        chiave_luogo(el[3]["testo_esatto"]) not in self.luoghi["__citta__"] and \
                        chiave_luogo(el[3]["testo_esatto"]) not in self.luoghi["__manuali__"]:
                    el[3].update(tipo="persona", metodo="elenco_di_persone", affidabilita="media")
        menzioni.sort(key=lambda m: m["inizio"])
        # «fra Melibeo e Coridone»: dopo una persona e «e/ed», anche il nome sconosciuto è persona;
        # un cognome già riconosciuto come persona nella stessa voce vale anche dove compare da solo
        cognomi = {m["testo_esatto"].split()[-1] for m in menzioni if m["tipo"] == "persona"}
        cognomi |= {m["testo_esatto"] for m in menzioni if m["tipo"] == "persona"}
        restano = []
        RX_COORD = r"\s(?:e|ed|o|et)\s"
        for s_t, a0, a1 in scarti:
            prima = sorted((m for m in menzioni if m["fine"] <= a0), key=lambda m: m["fine"])
            dopo = sorted((m for m in menzioni if m["inizio"] >= a1), key=lambda m: m["inizio"])
            tipo_c = None
            if prima and re.fullmatch(RX_COORD, testo[prima[-1]["fine"]:a0]) and prima[-1]["tipo"] in ("persona", "luogo"):
                tipo_c = prima[-1]["tipo"]            # «Strasoldo et Soffimbergo», «Zorzi o Rasponi»
            elif dopo and re.fullmatch(RX_COORD, testo[a1:dopo[0]["inizio"]]) and dopo[0]["tipo"] == "persona":
                tipo_c = "persona"                    # «tra Murtola e Marini»
            # elenchi di lettere «Cognome Nome, Luogo anno»: tra la virgola e la data c'è un luogo
            data_dopo = re.match(r"\s(?:\d|\(|$)", testo[a1:a1 + 2]) or re.match(r",\s\d", testo[a1:a1 + 3])
            if tipo_c is None and prima and prima[-1]["tipo"] == "persona" and testo[prima[-1]["fine"]:a0] == ", " \
                    and data_dopo and " " not in s_t:
                tipo_c = "luogo"
            # mittente prima di «a/al» + persona: «Zannier a C. Aless. Carnier», «Bicego… al prof. Gratognini»
            if tipo_c is None and dopo and dopo[0]["tipo"] == "persona" and \
                    re.fullmatch(r"…?\s(?:a|al|ad|all['’]|alla)\s(?:[\w.]+\.\s)*", testo[a1:dopo[0]["inizio"]]):
                tipo_c = "persona"
            if tipo_c is None and re.match(r",\s(?:fratelli|f\.lli|e figli)", testo[a1:a1 + 12]):
                tipo_c = "persona"                    # «Soresi, fratelli, Milano 1809»
            # elemento tra una virgola e una data: luogo della lettera («Garibaldi (autogr.), Caprera 7 sett. 1868»)
            if tipo_c is None and testo[max(0, a0 - 2):a0] == ", " and re.match(r"\s\d", testo[a1:a1 + 2]) and \
                    " " not in s_t and prima and a0 - prima[-1]["fine"] < 40:
                tipo_c = "luogo"
            # cognome isolato prima di «, Luogo anno»: «Zambon, Venezia 1851»
            if tipo_c is None and dopo and dopo[0]["tipo"] == "luogo" and testo[a1:dopo[0]["inizio"]] == ", " and \
                    re.match(r"\s\d", testo[dopo[0]["fine"]:dopo[0]["fine"] + 2]):
                tipo_c = "persona"
            if tipo_c or s_t in cognomi:
                menzioni.append({"testo_esatto": s_t, "inizio": a0, "fine": a1, "tipo": tipo_c or "persona",
                                 "correzione": None, "metodo": "coordinazione" if tipo_c else "stessa_voce",
                                 "affidabilita": "media"})
            else:
                restano.append((s_t, a0, a1))
        menzioni.sort(key=lambda m: m["inizio"])
        # nome singolo incerto tra «Persona, » e una data, o in «(X, 7 sett. 1649)»: è il luogo della lettera
        for k, m in enumerate(menzioni):
            if m["tipo"] != "persona" or m["affidabilita"] == "alta" or " " in m["testo_esatto"]:
                continue
            dopo_data = re.match(r"(?:,?\s\d|,\s\d)", testo[m["fine"]:m["fine"] + 3])
            prec_persona = (k and menzioni[k - 1]["tipo"] == "persona" and testo[menzioni[k - 1]["fine"]:m["inizio"]] == ", ") \
                or (testo[max(0, m["inizio"] - 2):m["inizio"]] == ", " and not self.e_nome_battesimo({"parola": m["testo_esatto"]}))
            tra_parentesi = testo[m["inizio"] - 1:m["inizio"]] == "(" and re.match(r",\s\d", testo[m["fine"]:m["fine"] + 3])
            if dopo_data and (prec_persona or tra_parentesi):
                m.update(tipo="luogo", metodo="luogo_della_lettera", affidabilita="media")
        return menzioni, restano

    def unisci_inversioni(self, menzioni, testo):
        """«Loschi, Giuseppe» e «Girolamo e Paolo Fistulario»: una sola menzione."""
        out = []
        for m in menzioni:
            if out:
                a = out[-1]
                tra = testo[a["fine"]:m["inizio"]]
                solo_nome = m["tipo"] != "luogo" and all(normalizza(p) in self.nomi or p in self.abbreviazioni
                                                         for p in m["testo_esatto"].split())
                cognome = normalizza(a["testo_esatto"]) not in self.nomi
                dopo_m = testo[m["fine"]:m["fine"] + 2]
                in_elenco = dopo_m.startswith(",") or testo[max(0, a["inizio"] - 2):a["inizio"]] == ", "
                if tra == ", " and a["tipo"] in ("persona", "luogo") and solo_nome and cognome \
                        and " " not in a["testo_esatto"] and not in_elenco:
                    a.update(testo_esatto=testo[a["inizio"]:m["fine"]], fine=m["fine"], metodo="ordine_inverso",
                             affidabilita="alta", tipo="persona")
                    continue
                if tra == " e " and a["tipo"] == "persona" and m["tipo"] == "persona" and \
                        all(normalizza(p) in self.nomi for p in a["testo_esatto"].split()):
                    a.update(testo_esatto=testo[a["inizio"]:m["fine"]], fine=m["fine"], metodo="nomi_coordinati")
                    continue
            out.append(m)
        return out


# ---------------------------------------------------------------------------


SOLO_INIZIO_FRASE = set()


def statistiche_corpus(con):
    """Per ogni parola: quante volte compare con iniziale maiuscola e minuscola.
    Calcola anche le parole che hanno la maiuscola solo a inizio frase («Scrittura»,
    «Cartaceo»): sono parole comuni, non nomi."""
    conta, dentro = Counter(), Counter()
    for (t,) in con.execute("SELECT testo FROM voci UNION ALL SELECT coalesce(coda,'') FROM voci "
                            "UNION ALL SELECT testo FROM annotazioni"):
        for m in re.finditer(r"(?<![\w.])([A-Za-zÀ-ÿ]+)", t):
            conta[m.group(1)] += 1
            if m.group(1)[:1].isupper():
                prima = t[max(0, m.start() - 3):m.start()]
                if m.start() > 0 and not re.search(r"(?:[.!?«:\n]\s*|^\s*|[\d(]\s?)$", prima):
                    dentro[m.group(1)] += 1
    global SOLO_INIZIO_FRASE
    # (serve anche almeno un'occorrenza in minuscolo: i cognomi in testa alle voci,
    # «Loschi, Giuseppe», non compaiono mai in minuscolo)
    SOLO_INIZIO_FRASE = {p.lower() for p, n in conta.items()
                         if p[:1].isupper() and n >= 3 and dentro[p] <= 0.05 * n and conta[p.lower()] >= 1}
    stat = {}
    for parola, n in conta.items():
        chiave = parola.lower()
        maiu, minu = stat.get(chiave, (0, 0))
        if parola[:1].isupper():
            maiu += n
        else:
            minu += n
        stat[chiave] = (maiu, minu)
    return stat


def main():
    campione = "--campione" in sys.argv
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    estrattore = Estrattore(carica_liste(statistiche_corpus(con)))
    filtro = f"WHERE {CAMPIONE}" if campione else ""
    n_m = n_s = 0
    for vid, testo, coda in con.execute(f"SELECT id, testo, coda FROM voci {filtro} ORDER BY id").fetchall():
        segmenti = con.execute("SELECT id, inizio, fine FROM segmenti WHERE voce=? ORDER BY inizio", (vid,)).fetchall()
        fonti = [("testo", None, testo)]
        if coda:
            fonti.append(("coda", None, coda))
        for aid, atesto in con.execute("SELECT id, testo FROM annotazioni WHERE voce=?", (vid,)):
            fonti.append(("annotazione", aid, atesto))
        for sede, aid, t in fonti:
            menzioni, scarti = estrattore.estrai(t)
            divise = []
            for m in menzioni:
                # «Padova di Giacomo Belgrado», «Aquileia di A. Altan»: un luogo seguito da un nome completo
                # (almeno due parole maiuscole o iniziali) sono due menzioni; «Valvasone di Maniago» resta intera
                x = re.match(r"(\S+) (?:di|da|d')\s?(?=[A-Z])", m["testo_esatto"])
                resto = m["testo_esatto"][x.end():] if x else ""
                k_l = chiave_luogo(x.group(1)) if x else ""
                if x and m["tipo"] == "persona" and x.group(1).lower() not in LUOGO_E_PERSONA_NO \
                        and x.group(1).lower() not in estrattore.nomi_esatti and (k_l in estrattore.luoghi["__citta__"] or
                                                     k_l in estrattore.luoghi["__manuali__"] or
                                                     estrattore.peso_luogo(x.group(1)) == "forte") \
                        and len(re.findall(r"\b[A-Z][\w']*\.?", resto)) >= 2:
                    divise.append(dict(m, testo_esatto=x.group(1), fine=m["inizio"] + len(x.group(1)), tipo="luogo",
                                       correzione=None, forma_riferimento=None, metodo="luogo_e_persona",
                                       affidabilita="media"))
                    m = dict(m, testo_esatto=resto, inizio=m["inizio"] + x.end())
                divise.append(m)
            for m in divise:
                # «A-K. A. Altan», «L-Z. Liruti»: le lettere della partizione alfabetica appartengono alla
                # frase precedente, non al nome
                x = re.match(r"[A-Z]-[A-Z]\.\s+", m["testo_esatto"])
                if x and m["tipo"] == "persona" and len(m["testo_esatto"]) > x.end():
                    m["testo_esatto"] = m["testo_esatto"][x.end():]
                    m["inizio"] += x.end()
                seg = None
                if sede == "testo":
                    seg = next((s for s, a, b in segmenti if a <= m["inizio"] < b), None)
                con.execute(
                    "INSERT INTO menzioni (voce, sede, annotazione, segmento, testo_esatto, inizio, fine, tipo,"
                    " correzione, forma_riferimento, metodo, affidabilita) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (vid, sede, aid, seg, m["testo_esatto"], m["inizio"], m["fine"], m["tipo"],
                     m["correzione"], m.get("forma_riferimento"), m["metodo"], m["affidabilita"]))
                n_m += 1
            for s, a, b in scarti:
                con.execute("INSERT INTO non_classificati (voce, sede, annotazione, testo_esatto, inizio, fine)"
                            " VALUES (?,?,?,?,?,?)", (vid, sede, aid, s, a, b))
                n_s += 1
    # decisioni del curatore su una forma, valide in tutte le voci (dati/liste/decisioni_forme.tsv);
    # tipo «nessuno» = non è un nome. Le classificazioni per singola voce, applicate dopo, prevalgono.
    for r in csv.DictReader(open(LISTE / "decisioni_forme.tsv", encoding="utf-8"), delimiter="\t"):
        rif = r["forma_riferimento"] or None
        if r["tipo"] == "nessuno":
            con.execute("DELETE FROM menzioni WHERE testo_esatto=?", (r["forma"],))
            con.execute("DELETE FROM non_classificati WHERE testo_esatto=?", (r["forma"],))
            continue
        con.execute("UPDATE menzioni SET tipo=?, forma_riferimento=coalesce(?, forma_riferimento), "
                    "metodo='curatore', affidabilita='alta' WHERE testo_esatto=?", (r["tipo"], rif, r["forma"]))
        for nid, vid, sede, aid, a0, a1 in con.execute(
                "SELECT id, voce, sede, annotazione, inizio, fine FROM non_classificati WHERE testo_esatto=?",
                (r["forma"],)).fetchall():
            seg = None
            if sede == "testo":
                x = con.execute("SELECT id FROM segmenti WHERE voce=? AND inizio<=? AND ?<fine", (vid, a0, a0)).fetchone()
                seg = x[0] if x else None
            con.execute("INSERT INTO menzioni (voce, sede, annotazione, segmento, testo_esatto, inizio, fine, tipo,"
                        " forma_riferimento, metodo, affidabilita) VALUES (?,?,?,?,?,?,?,?,?,'curatore','alta')",
                        (vid, sede, aid, seg, r["forma"], a0, a1, r["tipo"], rif))
            con.execute("DELETE FROM non_classificati WHERE id=?", (nid,))
    # classificazioni del curatore per singola voce (dati/liste/classificazioni_manuali.tsv)
    for r in csv.DictReader(open(LISTE / "classificazioni_manuali.tsv", encoding="utf-8"), delimiter="\t"):
        ids = [x[0] for x in con.execute("SELECT id FROM voci WHERE numero=?", (r["voce"],))]
        for vid in ids:
            rif = r["forma_riferimento"] or None
            if r["tipo"] == "nessuno":
                con.execute("DELETE FROM menzioni WHERE voce=? AND testo_esatto=?", (vid, r["forma"]))
                continue
            con.execute("UPDATE menzioni SET tipo=?, forma_riferimento=?, metodo='curatore', affidabilita='alta' "
                        "WHERE voce=? AND testo_esatto=?", (r["tipo"], rif, vid, r["forma"]))
            for nid, sede, aid, a0, a1 in con.execute(
                    "SELECT id, sede, annotazione, inizio, fine FROM non_classificati WHERE voce=? AND testo_esatto=?",
                    (vid, r["forma"])).fetchall():
                con.execute("INSERT INTO menzioni (voce, sede, annotazione, testo_esatto, inizio, fine, tipo,"
                            " forma_riferimento, metodo, affidabilita) VALUES (?,?,?,?,?,?,?,?,'curatore','alta')",
                            (vid, sede, aid, r["forma"], a0, a1, r["tipo"], rif))
                con.execute("DELETE FROM non_classificati WHERE id=?", (nid,))
    # cognomi riconosciuti con sicurezza come persona (almeno tre volte, mai come luogo): valgono
    # anche dove compaiono da soli e le regole non li hanno classificati («Nel frontespizio «Pirona»»)
    sicuri = Counter()
    luoghi_visti = set()
    for t, tipo, aff in con.execute("SELECT testo_esatto, tipo, affidabilita FROM menzioni"):
        ultima = t.split()[-1] if t.split() else t
        if tipo == "persona" and aff == "alta":
            sicuri[ultima] += 1
        elif tipo == "luogo":
            luoghi_visti.add(ultima)
    noti = {c for c, n in sicuri.items() if n >= 3 and c not in luoghi_visti and len(c) > 3}
    righe = con.execute("SELECT id, voce, sede, annotazione, testo_esatto, inizio, fine FROM non_classificati").fetchall()
    for nid, vid, sede, aid, t, a0, a1 in righe:
        if t in noti:
            seg = None
            if sede == "testo":
                r = con.execute("SELECT id FROM segmenti WHERE voce=? AND inizio<=? AND ?<fine", (vid, a0, a0)).fetchone()
                seg = r[0] if r else None
            con.execute(
                "INSERT INTO menzioni (voce, sede, annotazione, segmento, testo_esatto, inizio, fine, tipo,"
                " correzione, metodo, affidabilita) VALUES (?,?,?,?,?,?,?,'persona',NULL,'noto_altrove','media')",
                (vid, sede, aid, seg, t, a0, a1))
            con.execute("DELETE FROM non_classificati WHERE id=?", (nid,))
            n_m += 1
            n_s -= 1
    con.commit()
    con.close()
    print(f"Menzioni: {n_m} — non classificati: {n_s}" + (" (campione)" if campione else ""))


if __name__ == "__main__":
    main()
