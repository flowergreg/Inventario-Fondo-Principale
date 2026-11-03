"""Normalizzazione per la ricerca (CLAUDE.md): minuscole, niente accenti né
segni diacritici, j→i, y→i, doppie semplificate, punteggiatura ignorata.
Si applica sia alla stringa cercata sia al testo.

Eccezione: le parole fatte solo di cifre romane maiuscole (XVI, XVII, VII…)
non subiscono né j→i né la semplificazione delle doppie, altrimenti «Luigi
XVII» diventerebbe «Luigi XVI» e «Pio VII» «Pio VI»."""

import re
import unicodedata

RX_ROMANO = re.compile(r"^[IVXLCDM]+$")


def _parola(p):
    if RX_ROMANO.match(p):
        return p.lower()
    p = p.lower().replace("j", "i").replace("y", "i")
    p = p.replace("æ", "ae").replace("œ", "oe").replace("ß", "ss")
    return re.sub(r"(\w)\1+", r"\1", p)          # doppie semplificate


def normalizza(testo):
    t = unicodedata.normalize("NFKD", testo)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s]|_", " ", t)              # punteggiatura ignorata
    return " ".join(_parola(p) for p in t.split())
