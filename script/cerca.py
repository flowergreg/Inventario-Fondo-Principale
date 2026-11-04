#!/usr/bin/env python3
"""Ricerca da riga di comando nell'inventario (fase 7).

Uso:
    python3 script/cerca.py "Zuan de Udene"
    python3 script/cerca.py --prove        # batteria di prove
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ricerca import cerca, costruisci_indice, frammento  # noqa: E402

LIVELLI = {1: "entità", 2: "testo", 3: "approssimata"}

# domanda → voci che devono esserci (casi emersi nelle fasi precedenti)
PROVE = {
    "Giovanni da Udine": ["870", "1195", "1197"],
    "Zuan de Udene": ["870", "1195", "1197"],     # Zuan → Giovanni, Udene → Udine
    "Utinum": ["555"],
    "Udene": ["2598"],
    "Daniele Florio": ["23", "195"],
    "Florio Daniele": ["23", "195"],
    "Jacopo Pirona": ["493", "511", "525"],
    "San Pietro": ["919"],
    "Savorgnan": ["1247"],
    "Girolamo Cortenovis": ["593"],
    "Domanins": ["2036"],
    "Paulus Venetus": ["628"],
    "Ermes di Colloredo": ["341", "350"],
    "Mistruzi": ["824"],
    "Ludovico Ariosto": ["434"],                   # Ludovico → Lodovico
    "Gerolamo Cortenovis": ["593"],
}


def stampa(domanda, indice, massimo=15):
    r = cerca(domanda, indice)
    print(f"\n«{domanda}»: {len(r)} voci")
    for x in r[:massimo]:
        p = x["punti"][0]
        ent = f" — {p['entita'][0]} ({p['entita'][2]})" if p["entita"] else ""
        seg = f" [{p['segmento']}]" if p["segmento"] else ""
        print(f"  {x['voce']}{seg} ({LIVELLI[p['livello']]}{ent}): "
              f"{frammento(indice, x['indice'], p['sede'], p['inizio'], p['fine'])[:160]}")
    return r


def main():
    indice = costruisci_indice()
    if len(sys.argv) > 1 and sys.argv[1] == "--prove":
        esito = []
        for domanda, attese in PROVE.items():
            r = stampa(domanda, indice, massimo=5)
            trovate = {x["voce"] for x in r}
            mancanti = [v for v in attese if v not in trovate]
            esito.append((domanda, len(r), mancanti))
        print("\nRiepilogo prove:")
        for d, n, m in esito:
            print(f"  {'OK ' if not m else 'NO '} {d}: {n} voci" + (f"; mancano {', '.join(m)}" if m else ""))
        return
    for domanda in sys.argv[1:]:
        stampa(domanda, indice)


if __name__ == "__main__":
    main()
