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
    tipo          TEXT NOT NULL,     -- persona | luogo | santo (santo = da dirimere)
    correzione    TEXT,              -- forma tra quadre del curatore («Morlupino»)
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
    for r in csv.DictReader(open(LISTE / "luoghi_manuali.tsv", encoding="utf-8"), delimiter="\t"):
        luoghi[chiave_luogo(r["forma"])] = "forte"
        luoghi["~" + normalizza(r["forma"])] = "forte"
    nomi = set()
    for r in csv.DictReader(open(LISTE / "nomi.tsv", encoding="utf-8"), delimiter="\t"):
        nomi.add(r["forma_normalizzata"])
    # parole comuni: compaiono nel corpus anche con l'iniziale minuscola
    comuni = set()
    for parola, (maiuscole, minuscole) in corpus_parole.items():
        if minuscole >= 2 and minuscole >= 0.3 * (maiuscole + minuscole):
            comuni.add(parola)
    nomi -= {n for n in nomi if n in comuni}          # «Felice», «Pace»… se usati come parole comuni
    return titoli, istituzioni, abbreviazioni, luoghi, nomi, comuni


def chiave_luogo(forma):
    return forma.lower().replace("j", "i").replace("’", "'")


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------

RX_TOKEN = re.compile(r"""
    (?P<parola>(?:[A-Za-zÀ-ÿ]+\[[a-zà-ÿ]+\][a-zà-ÿ]*)          # «G[aspero]»
             |[dD]e['’](?=\s)                                          # «De' Rubeis»
             |(?:[dD](?:e(?:ll|gl)?|all)?['’](?=[A-ZÀ-Ý]))?[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’]*)  # «D'Arcano», «Dell'Ongaro»
    (?P<punto>\.(?:[°ºªo](?![A-Za-z]))?|°|ª)?                   # «Gio.», «Ant.°», «Fr.co» gestito sotto
  | (?P<quadra>\[[^\]\n]{1,60}\])
  | (?P<altro>\S)
""", re.X)

PARTICELLE = {"di", "de", "de'", "de’", "del", "della", "delle", "dei", "degli", "da", "dal", "dalla",
              "d'", "d’", "von", "van", "der", "den", "la", "le", "lo", "du", "des", "y"}
PARTICELLE_TRA_PARENTESI = re.compile(r"\((?:di|de|da|della|del|dalla|de')\)")
ARTICOLI_PERSONA = {"il", "lo", "del", "dello", "dal", "al", "col", "sul", "nel"}   # «il Fontanini», «del Burchiello»
PREPOSIZIONI_LUOGO_FORTI = {"in", "a", "ad", "presso", "nel", "nella", "per", "verso", "fino", "sino", "da", "dalla"}
PREPOSIZIONI_LUOGO = PREPOSIZIONI_LUOGO_FORTI | {"di", "de", "da"}
PARTICELLE_MAIUSCOLE = {"De", "Di", "Da", "Del", "Della", "Delle", "Dei", "Degli", "Dal", "Dalla", "De'", "De’",
                        "Van", "Von", "Du", "Des"}
SANTI = re.compile(r"^(?:S\.|SS\.|Ss\.|S\.ta|S\.to|San|Santo|Santa|Sant['’]|Santi|Sancti|Sancte|Sanctus|Sancta)$")
FONDI = {"Raccolta", "Racc.", "Collezione", "Collez.", "Coll.", "Legato", "Fondo", "Dono", "Provenienza",
         "Acquisto", "Lascito", "Deposito", "Proven."}


def tokenizza(testo):
    toks = []
    for m in RX_TOKEN.finditer(testo):
        if m.group("parola"):
            parola = m.group("parola")
            fine = m.end()
            # «Fr.co», «Dom.co», «Bart.meo», «Vinc.zo»: abbreviazione con lettere in esponente
            m2 = re.match(r"\.(co|meo|eo|zo|mo|ro|na|ne|ni|lo|to|so|r|ra|te|ssa)\b", testo[m.end("parola"):])
            if m2:
                fine = m.end("parola") + m2.end()
            toks.append({"t": testo[m.start():fine], "parola": parola, "i": m.start(), "f": fine,
                         "abbr": testo[m.start():fine] != parola})
        elif m.group("quadra"):
            toks.append({"t": m.group(0), "quadra": True, "i": m.start(), "f": m.end()})
        else:
            toks.append({"t": m.group(0), "altro": True, "i": m.start(), "f": m.end()})
    # i token «parola» che finiscono con «.» sono stati presi con il punto
    return toks


def maiuscola(tok):
    p = tok.get("parola")
    if not p:
        return False
    p = re.sub(r"^[dD](?:e(?:ll|gl)?|all)?['’]", "", p)
    return p[:1].isupper()


# ---------------------------------------------------------------------------
# Estrazione
# ---------------------------------------------------------------------------


class Estrattore:
    def __init__(self, liste):
        (self.titoli, self.istituzioni, self.abbreviazioni, self.luoghi,
         self.nomi, self.comuni) = liste

    def e_iniziale(self, tok):
        return bool(tok.get("parola")) and re.fullmatch(r"[A-Z]\.", tok["t"]) is not None

    def e_abbreviazione_nome(self, tok):
        return tok.get("t") in self.abbreviazioni or self.e_iniziale(tok)

    def e_nome_battesimo(self, tok):
        p = tok.get("parola")
        return bool(p) and normalizza(re.sub(r"\[|\]", "", p)) in self.nomi

    def e_titolo(self, tok):
        if not tok.get("parola"):
            return False
        t = tok["t"].lower()
        return t in self.titoli or re.sub(r"^(?:dell|all|dall|nell|sull|l)['’]", "", t) in self.titoli

    def comune(self, tok):
        p = tok.get("parola")
        return bool(p) and p.lower() in self.comuni and not self.e_nome_battesimo(tok)

    def peso_luogo(self, testo_span):
        testo_span = re.sub(r"\s*\[[^\]]*\]", "", testo_span).strip().rstrip(".")
        return self.luoghi.get(chiave_luogo(testo_span)) or self.luoghi.get("~" + normalizza(testo_span))

    def fine_frase(self, tok):
        """Il punto del token chiude la frase? («Sommaripa.» sì, «Gio.», «G.», «Bapt.» no)."""
        if not tok.get("abbr") or not tok["t"].endswith("."):
            return False
        breve = len(tok["parola"]) <= 4 and not self.peso_luogo(tok["parola"]) and not self.e_nome_battesimo(tok)
        return not (self.e_abbreviazione_nome(tok) or self.e_titolo(tok) or breve)   # «Roma.» chiude, «Bapt.» no

    def romano(self, tok):
        return bool(tok.get("parola")) and re.fullmatch(r"[IVXLCDM]+", tok["parola"]) is not None

    def particella_maiuscola(self, toks, j):
        """«De», «Della», «Di», «Da», «Dal», «De'», «Van», «Von», seguita da maiuscola."""
        t = toks[j]
        return (bool(t.get("parola")) and t["t"].lower() in PARTICELLE and t["t"][:1].isupper()
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
            else:
                avvio = (maiuscola(tok) and not self.e_titolo(tok) and not self.romano(tok)
                         and tok["t"] not in FONDI and tok.get("parola") not in FONDI
                         and tok["t"] not in self.istituzioni and tok.get("parola") not in self.istituzioni
                         and (not self.comune(tok) or SANTI.match(tok["t"])
                              # cognome che è anche parola comune, seguito da un nome: «Bassi G.B.»
                              or (not self.fine_frase(tok) and succ.get("parola") and self.nome_token(succ))))
                if avvio and tok["t"] in PARTICELLE_MAIUSCOLE and not self.particella_maiuscola(toks, k):
                    avvio = False             # «De consolatione»
            if not avvio:
                k += 1
                continue
            idx = [k]
            j = k + 1
            ultimo = tok
            while j < n and not self.fine_frase(ultimo):
                t = toks[j]
                if t.get("quadra") and j + 1 < n and maiuscola(toks[j + 1]) and t["t"][1:2].isupper():
                    idx.append(j)             # correzione a metà nome: «Forcari [Foscari] Francesco»
                    j += 1
                    continue
                if maiuscola(t) and t["t"] not in self.istituzioni and t["t"] not in FONDI \
                        and not self.e_titolo(t) and (
                        not self.romano(t) or len(idx) >= 1):
                    if t["t"] in PARTICELLE_MAIUSCOLE and not self.particella_maiuscola(toks, j):
                        break
                    idx.append(j)
                    ultimo = t
                    j += 1
                    continue
                # titolo dentro il nome, seguito da un nome: «Beretta cav. Antonio», «Rezzonico card. C.»
                if self.e_titolo(t) and j + 1 < n and maiuscola(toks[j + 1]):
                    idx += [j, j + 1]
                    ultimo = toks[j + 1]
                    j += 2
                    continue
                low = t.get("parola", "").lower() if t.get("parola") else t["t"]
                # particella seguita da maiuscola: «di Prampero», «de' Rubeis»
                if (t.get("parola") and (t["t"].lower() in PARTICELLE or low in PARTICELLE)
                        and j + 1 < n and maiuscola(toks[j + 1]) and not self.romano(toks[j + 1])
                        and not self.e_titolo(toks[j + 1])           # «Temistocle del Padre Follard»
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
        p1 = prec_parole[-1] if prec_parole else ""
        prec_tok = toks[idx[0] - 1] if idx[0] > 0 else None

        # parola a inizio frase o di citazione: serve qualcosa di più della lista dei nomi
        # («Deo gratias. Amen», «Iste Boetius»)
        inizio_frase = prec_tok is None or prec_tok["t"] in ("«", '"', "“") or (
            prec_tok.get("abbr") and self.fine_frase(prec_tok)) or prec_tok["t"] in (".", "!", "?")
        if re.match(r"N\.\s?B\.", span_testo):
            return None                       # «N.B.»
        if SANTI.match(primi["t"]) and len(maiusc) >= 2 and len(idx) > 1 and \
                len(toks[idx[1]].get("parola") or "") > 1:
            return "santo", "santo", "alta"
        titolo_prima = prec_tok is not None and (self.e_titolo(prec_tok) or (
            prec_tok["t"] in ("Sig.", "Sig.r", "S.r") ))
        nome = any(self.e_nome_battesimo(t) for t in maiusc)
        abbr = any(self.e_abbreviazione_nome(toks[i]) for i in idx)
        luogo = self.peso_luogo(span_testo)
        if len(maiusc) >= 2 and (nome or abbr):
            # «Udine Venezia»? due luoghi forti di fila sono improbabili: si tiene persona
            return "persona", "nome_di_battesimo", "alta"
        if titolo_prima:
            return "persona", "titolo", "alta"
        if prec_tok is not None and prec_tok["t"] in FONDI or (prec_parole and prec_parole[-1] in
                                                               {x.lower() for x in FONDI}):
            return "persona", "fondo_o_provenienza", "media"     # «Dono Pagani», «Legato Toppo»
        if len(maiusc) == 1 and nome and luogo != "forte" and p1 not in PREPOSIZIONI_LUOGO_FORTI \
                and not inizio_frase:
            return "persona", "solo_nome_di_battesimo", "media"
        if luogo and (luogo == "forte" or not inizio_frase):
            if luogo == "forte":
                return "luogo", "lista_luoghi_forte", "alta"
            if luogo == "medio" and p1 in PREPOSIZIONI_LUOGO:
                return "luogo", "lista_luoghi_contesto", "media"
            if luogo == "debole" and p1 in PREPOSIZIONI_LUOGO_FORTI:
                return "luogo", "lista_luoghi_contesto", "bassa"
        if len(maiusc) == 1 and nome and not luogo and not inizio_frase:
            return "persona", "solo_nome_di_battesimo", "media"
        if p1 in ARTICOLI_PERSONA or (prec_tok and re.match(r"(?i)^(?:dell|all|dall|nell|sull)['’]$", prec_tok["t"])):
            return "persona", "articolo", "media"
        if any(toks[i]["t"].lower() in PARTICELLE for i in idx) and len(maiusc) >= 2:
            return "persona", "particella", "media"
        if len(maiusc) >= 2:
            primo_luogo = self.peso_luogo(maiusc[0]["parola"])
            if primo_luogo in ("forte", "medio") and not self.e_nome_battesimo(maiusc[1]):
                return "luogo", "luogo_con_specificazione", "media"     # «Macerata Picena»
            if inizio_frase and not nome:
                return None
            return "persona", "sequenza_maiuscole", "bassa"
        # cognome isolato dopo «di», «del», «dal»…, o tra parentesi: «di Fedro», «(Cortenovis)»
        if len(maiusc) == 1 and not luogo and not inizio_frase and (
                p1 in {"di", "de", "da", "del", "dal", "dello", "degli"} or (prec_tok and prec_tok["t"] == "(")):
            return "persona", "cognome_isolato", "bassa"
        if luogo == "medio" and not inizio_frase:
            return "luogo", "lista_luoghi_medio", "bassa"
        return None

    def estrai(self, testo):
        """Restituisce (menzioni, non_classificati) con offset in `testo`."""
        toks = tokenizza(testo)
        menzioni, scarti = [], []
        for idx in self.sequenze(toks):
            # istituzione immediatamente prima: «Biblioteca Guarneriana», «Accademia degli Sventati»
            prec = toks[idx[0] - 1] if idx[0] > 0 else None
            prec2 = toks[idx[0] - 2] if idx[0] > 1 else None
            if prec is not None and (prec["t"] in self.istituzioni or (
                    prec.get("parola", "").lower() in ("degli", "dei", "delle") and prec2 is not None
                    and prec2["t"] in self.istituzioni)):
                if not self.peso_luogo(testo[toks[idx[0]]["i"]:toks[idx[-1]]["f"]]):
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
                    correzione = contenuto
                    if esito is None:
                        esito = ("persona", "correzione_curatore", "media")
            if esito is None:
                scarti.append((testo[i0:i1], i0, i1))
                continue
            tipo, metodo, aff = esito
            # persona seguita da «di/da» + città: provenienza, non predicato nobiliare
            # («libreria Pagani di Udine» → Pagani + Udine). I predicati («Ermes di Colloredo») restano uniti.
            if tipo == "persona":
                m_c = re.search(r"\s(?:di|da)\s([A-ZÀ-Ý][\w'’]+(?:\s(?:del|di)\s[A-ZÀ-Ý][\w'’]+)?)$", testo[i0:i1])
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
        return self.unisci_inversioni(menzioni, testo), scarti

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
                if tra == ", " and a["tipo"] in ("persona", "luogo") and solo_nome and cognome \
                        and " " not in a["testo_esatto"]:
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


def statistiche_corpus(con):
    """Per ogni parola: quante volte compare con iniziale maiuscola e minuscola."""
    conta = Counter()
    for (t,) in con.execute("SELECT testo FROM voci UNION ALL SELECT coalesce(coda,'') FROM voci "
                            "UNION ALL SELECT testo FROM annotazioni"):
        for m in re.finditer(r"(?<![\w.])([A-Za-zÀ-ÿ]+)", t):
            conta[m.group(1)] += 1
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
            for m in menzioni:
                seg = None
                if sede == "testo":
                    seg = next((s for s, a, b in segmenti if a <= m["inizio"] < b), None)
                con.execute(
                    "INSERT INTO menzioni (voce, sede, annotazione, segmento, testo_esatto, inizio, fine, tipo,"
                    " correzione, metodo, affidabilita) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (vid, sede, aid, seg, m["testo_esatto"], m["inizio"], m["fine"], m["tipo"],
                     m["correzione"], m["metodo"], m["affidabilita"]))
                n_m += 1
            for s, a, b in scarti:
                con.execute("INSERT INTO non_classificati (voce, sede, annotazione, testo_esatto, inizio, fine)"
                            " VALUES (?,?,?,?,?,?)", (vid, sede, aid, s, a, b))
                n_s += 1
    con.commit()
    con.close()
    print(f"Menzioni: {n_m} — non classificati: {n_s}" + (" (campione)" if campione else ""))


if __name__ == "__main__":
    main()
