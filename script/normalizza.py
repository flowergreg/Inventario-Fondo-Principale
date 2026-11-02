"""Normalizzazione per la ricerca (CLAUDE.md): minuscole, niente accenti né
segni diacritici, j→i, y→i, doppie semplificate, punteggiatura ignorata.
Si applica sia alla stringa cercata sia al testo."""

import re
import unicodedata


def normalizza(testo):
    t = unicodedata.normalize("NFKD", testo)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().replace("j", "i").replace("y", "i")
    t = t.replace("æ", "ae").replace("œ", "oe").replace("ß", "ss")
    t = re.sub(r"[^\w\s]|_", " ", t)          # punteggiatura ignorata
    t = re.sub(r"(\w)\1+", r"\1", t)          # doppie semplificate
    return re.sub(r"\s+", " ", t).strip()
