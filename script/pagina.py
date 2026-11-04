#!/usr/bin/env python3
"""Fase 7 — pagina web di ricerca (un solo file HTML, funziona anche offline).

Esporta l'indice di ricerca.py dentro web/index.html, insieme alla stessa logica di
ricerca riscritta in JavaScript (normalizzazione, espansioni, entità, testo vicino,
ricerca approssimata). Lo stile sta tutto nelle variabili CSS in cima al file.

Uso: python3 script/pagina.py
"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ricerca import costruisci_indice  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
OUT = RADICE / "web" / "index.html"

MODELLO = r"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fondo Principale — ricerca</title>
<style>
:root {
  --sfondo: #fbfaf7; --carta: #ffffff; --testo: #22201c; --tenue: #6b655c; --linea: #e3ded5;
  --accento: #7a2e1f; --accento-chiaro: #f3e7e2; --evidenza: #fde9a8; --font-testo: Georgia, "Times New Roman", serif;
  --font-ui: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; --raggio: 4px; --larghezza: 920px;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --sfondo: #1b1a18; --carta: #24221f; --testo: #ece7df; --tenue: #a39b8f; --linea: #3a3631;
    --accento: #e09a85; --accento-chiaro: #3a2a25; --evidenza: #6b5a1e;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--sfondo); color: var(--testo); font-family: var(--font-testo); line-height: 1.55; }
header, main, footer { max-width: var(--larghezza); margin: 0 auto; padding: 0 16px; }
header { padding-top: 32px; padding-bottom: 8px; }
h1 { font-family: var(--font-ui); font-size: 1.5rem; font-weight: 600; margin: 0 0 4px; color: var(--accento); }
.sottotitolo { color: var(--tenue); font-family: var(--font-ui); font-size: .9rem; margin: 0; }
form { display: flex; gap: 8px; margin: 20px 0 8px; }
input[type=search] { flex: 1; min-width: 0; font: inherit; font-size: 1.05rem; padding: 10px 12px; border: 1px solid var(--linea);
  border-radius: var(--raggio); background: var(--carta); color: var(--testo); }
input[type=search]:focus { outline: 2px solid var(--accento); outline-offset: 1px; }
button { font-family: var(--font-ui); font-size: .95rem; padding: 10px 16px; border: 0; border-radius: var(--raggio);
  background: var(--accento); color: #fff; cursor: pointer; }
.opzioni { font-family: var(--font-ui); font-size: .85rem; color: var(--tenue); display: flex; gap: 16px; flex-wrap: wrap; }
.esempi a { color: var(--accento); cursor: pointer; text-decoration: underline dotted; margin-right: 8px; }
.stato { font-family: var(--font-ui); font-size: .9rem; color: var(--tenue); margin: 16px 0 8px; }
.forme { font-family: var(--font-ui); font-size: .8rem; color: var(--tenue); margin: 0 0 16px; }
.forme code { background: var(--accento-chiaro); padding: 1px 4px; border-radius: 3px; }
.voce { background: var(--carta); border: 1px solid var(--linea); border-radius: var(--raggio); padding: 12px 16px; margin: 0 0 10px; }
.voce h2 { font-family: var(--font-ui); font-size: 1rem; margin: 0 0 6px; display: flex; gap: 8px; flex-wrap: wrap; align-items: baseline; }
.etichetta { font-family: var(--font-ui); font-size: .75rem; padding: 1px 6px; border-radius: 10px; background: var(--accento-chiaro); color: var(--accento); }
.punto { margin: 4px 0; overflow-wrap: anywhere; }
.punto .seg { font-family: var(--font-ui); font-size: .8rem; color: var(--tenue); margin-right: 6px; }
mark { background: var(--evidenza); color: inherit; padding: 0 1px; }
.entita { font-family: var(--font-ui); font-size: .8rem; color: var(--tenue); }
.entita a { color: var(--accento); }
details { margin-top: 6px; } summary { font-family: var(--font-ui); font-size: .85rem; color: var(--accento); cursor: pointer; }
.testo-voce { white-space: pre-wrap; font-size: .95rem; margin-top: 6px; }
footer { font-family: var(--font-ui); font-size: .8rem; color: var(--tenue); padding-top: 24px; padding-bottom: 32px; }
</style>
</head>
<body>
<header>
  <h1>Inventario dei manoscritti del Fondo Principale</h1>
  <p class="sottotitolo">Ricerca di persone e luoghi in qualunque grafia · voci 1–4519 · trascrizione a cura di Gregorio Grasselli</p>
</header>
<main>
  <form id="f"><input type="search" id="q" placeholder="Es. Zuan de Udene, Utinum, Florio Daniele, S. Pietro" autocomplete="off" autofocus>
  <button>Cerca</button></form>
  <div class="opzioni"><span class="esempi">Prova: <a>Giovanni da Udine</a><a>Utinum</a><a>Jac. Pirona</a><a>Paulus Venetus</a><a>Ermes di Colloredo</a></span></div>
  <div class="stato" id="stato">Scrivi un nome di persona o di luogo.</div>
  <div class="forme" id="forme"></div>
  <div id="risultati"></div>
</main>
<footer>
  La ricerca normalizza la grafia (maiuscole, accenti, j/i, y/i, doppie) e la estende con le varianti registrate:
  forme latine, venete e friulane, abbreviazioni, correzioni del curatore, forme di Wikidata. Livelli: <b>entità</b>
  (stessa persona o stesso luogo, anche in grafie lontane), <b>testo</b> (tutte le parole vicine nella voce),
  <b>approssimata</b> (una lettera di differenza, solo se il resto non trova nulla). I raggruppamenti in entità sono
  proposti e non ancora validati. Indice del __DATA__.
</footer>
<script>
const IDX = __INDICE__;
const VUOTE = new Set(IDX.vuote);
const RX_PAROLA = /[\p{L}\p{N}]+/gu;
const RX_STACCO = /[,;:\n\[\]]|\((?!\s*(?:di|de|da|d['’])\s*\))|(?<!\((?:di|de|da))\)/;
function normParola(p) {
  if (/^[IVXLCDM]+$/.test(p)) return p.toLowerCase();
  p = p.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().replace(/j/g, "i").replace(/y/g, "i")
       .replace(/æ/g, "ae").replace(/œ/g, "oe").replace(/ß/g, "ss");
  return p.replace(/([\p{L}\p{N}_])\1+/gu, "$1");
}
function parole(testo) {
  const out = []; let blocco = 0, ultimo = 0; testo = testo || "";
  for (const m of testo.matchAll(RX_PAROLA)) {
    if (RX_STACCO.test(testo.slice(ultimo, m.index))) blocco++;
    out.push([normParola(m[0]), m.index, m.index + m[0].length, blocco]); ultimo = m.index + m[0].length;
  }
  return out;
}
const chiave = t => parole(t).map(p => p[0]).filter(w => w && !VUOTE.has(w));
// testi delle voci già divisi in parole (una volta sola, al caricamento)
const SEDI = IDX.voci.map(v => {
  const s = [["t", v.t, parole(v.t)]];
  if (v.c) s.push(["c", v.c, parole(v.c)]);
  v.a.forEach((a, k) => s.push(["a" + k, a, parole(a)]));
  return s;
});
const ENT = IDX.entita.map(e => ({...e, vs: e.v.map(x => new Set(x.split(" ")))}));
let VOCAB = null;
const espandi = t => new Set([t, ...(IDX.espansioni[t] || [])]);
function distUno(a, b) {
  if (a === b) return true; if (Math.abs(a.length - b.length) > 1) return false;
  if (a.length === b.length) { let d = 0; for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) d++; return d === 1; }
  if (a.length > b.length) [a, b] = [b, a]; let i = 0; while (i < a.length && a[i] === b[i]) i++;
  return a.slice(i) === b.slice(i + 1);
}
function nelTesto(insiemi, finestra) {
  const tutte = new Set(); insiemi.forEach(s => s.forEach(w => tutte.add(w)));
  const trovati = new Map();
  SEDI.forEach((sedi, vi) => {
    for (const [sede, , pw] of sedi) {
      if (!insiemi.every(s => pw.some(p => s.has(p[0])))) continue;
      for (let i = 0; i < pw.length; i++) {
        if (!tutte.has(pw[i][0])) continue;
        const tratto = pw.slice(i, i + finestra).filter(p => p[3] === pw[i][3]);
        if (insiemi.every(s => tratto.some(p => s.has(p[0])))) {
          const fine = Math.max(...tratto.filter(p => tutte.has(p[0])).map(p => p[2]));
          if (!trovati.has(vi)) trovati.set(vi, []);
          trovati.get(vi).push([sede, pw[i][1], fine]); break;
        }
      }
    }
  });
  return trovati;
}
function cerca(domanda) {
  const q = chiave(domanda); if (!q.length) return {q, ris: []};
  const insiemi = q.map(espandi); const finestra = Math.max(q.length + 2, 4);
  const ris = new Map(); const add = (vi, h) => { if (!ris.has(vi)) ris.set(vi, []); ris.get(vi).push(h); };
  for (const e of ENT) {
    if (e.vs.some(vw => insiemi.every(s => [...s].some(w => vw.has(w)))))
      for (const [vi, sede, ini, fin] of e.m) add(vi, [1, sede === "testo" ? "t" : sede === "coda" ? "c" : sede, ini, fin, e]);
  }
  for (const [vi, hs] of nelTesto(insiemi, finestra)) for (const [s, i, f] of hs) add(vi, [2, s, i, f, null]);
  let approssimata = false;
  if (!ris.size) {
    if (!VOCAB) { VOCAB = new Set(); SEDI.forEach(sedi => sedi.forEach(([, , pw]) => pw.forEach(p => VOCAB.add(p[0])))); }
    const larghi = insiemi.map(s => { const n = new Set(s); s.forEach(t => { if (t.length >= 5) VOCAB.forEach(w => { if (distUno(t, w)) n.add(w); }); }); return n; });
    for (const [vi, hs] of nelTesto(larghi, finestra)) for (const [s, i, f] of hs) add(vi, [3, s, i, f, null]);
    approssimata = true;
  }
  const out = [...ris.entries()].map(([vi, hs]) => { hs.sort((a, b) => a[0] - b[0] || (a[1] !== "t") - (b[1] !== "t") || a[2] - b[2]); return {vi, hs, liv: hs[0][0]}; });
  out.sort((a, b) => a.liv - b.liv || a.vi - b.vi);
  return {q, insiemi, ris: out, approssimata};
}
const esc = s => s.replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const LIV = {1: "entità", 2: "testo", 3: "approssimata"};
function testoSede(v, sede) { return sede === "t" ? v.t : sede === "c" ? v.c : v.a[+sede.slice(1)]; }
function segmento(v, sede, ini) {
  if (sede !== "t") return sede[0] === "c" ? "coda" : "annotazione";
  const s = v.s.find(s => s[1] <= ini && ini < s[2]); return s ? s[0] : "";
}
function frammento(testo, ini, fin, c = 90) {
  const a = Math.max(0, ini - c), b = Math.min(testo.length, fin + c);
  return (a ? "…" : "") + esc(testo.slice(a, ini)) + "<mark>" + esc(testo.slice(ini, fin)) + "</mark>" + esc(testo.slice(fin, b)) + (b < testo.length ? "…" : "");
}
function evidenzia(testo, tratti) {
  tratti = tratti.slice().sort((a, b) => a[0] - b[0]); let out = "", p = 0;
  for (const [i, f] of tratti) { if (i < p) continue; out += esc(testo.slice(p, i)) + "<mark>" + esc(testo.slice(i, f)) + "</mark>"; p = f; }
  return out + esc(testo.slice(p));
}
function mostra(domanda) {
  const t0 = performance.now(); const r = cerca(domanda);
  const el = document.getElementById("risultati"), st = document.getElementById("stato"), fo = document.getElementById("forme");
  if (!r.q.length) { st.textContent = "Scrivi un nome di persona o di luogo."; fo.innerHTML = ""; el.innerHTML = ""; return; }
  fo.innerHTML = "Forme cercate: " + r.insiemi.map(s => [...s].map(w => "<code>" + esc(w) + "</code>").join(" ")).join(" + ");
  st.textContent = `${r.ris.length} voci` + (r.approssimata && r.ris.length ? " (ricerca approssimata)" : "") + ` · ${Math.round(performance.now() - t0)} ms`;
  el.innerHTML = r.ris.slice(0, 300).map(({vi, hs, liv}) => {
    const v = IDX.voci[vi]; const visti = new Set(); const punti = [];
    for (const h of hs) { const k = h[1] + h[2]; if (visti.has(k)) continue; visti.add(k); punti.push(h); }
    const ent = [...new Map(hs.filter(h => h[4]).map(h => [h[4].i, h[4]])).values()];
    const sedi = new Map(); punti.forEach(h => { if (!sedi.has(h[1])) sedi.set(h[1], []); sedi.get(h[1]).push([h[2], h[3]]); });
    return `<article class="voce"><h2>Voce ${esc(v.n)} <span class="etichetta">${LIV[liv]}</span></h2>` +
      punti.slice(0, 3).map(h => { const seg = segmento(v, h[1], h[2]);
        return `<div class="punto">${seg ? `<span class="seg">${esc(seg)}</span>` : ""}${frammento(testoSede(v, h[1]), h[2], h[3])}</div>`; }).join("") +
      (punti.length > 3 ? `<div class="entita">… e altri ${punti.length - 3} punti nella voce</div>` : "") +
      ent.map(e => `<div class="entita">${e.t === "persona" ? "Persona" : e.t === "luogo" ? "Luogo" : "Santo"}: <b>${esc(e.f)}</b>` +
        ` · raggruppamento ${esc(e.st)}` + (e.q ? ` · <a href="https://www.wikidata.org/wiki/${e.q}" target="_blank" rel="noopener">Wikidata ${e.q}</a>` : "") + `</div>`).join("") +
      `<details><summary>Testo della voce</summary><div class="testo-voce">${evidenzia(v.t, sedi.get("t") || [])}` +
      (v.c ? `\n\n<i>${evidenzia(v.c, sedi.get("c") || [])}</i>` : "") +
      v.a.map((a, k) => `\n\n[${evidenzia(a, sedi.get("a" + k) || [])}]`).join("") + `</div></details></article>`;
  }).join("") + (r.ris.length > 300 ? `<p class="stato">Mostrate le prime 300 voci di ${r.ris.length}.</p>` : "");
}
const form = document.getElementById("f"), q = document.getElementById("q");
form.addEventListener("submit", ev => { ev.preventDefault(); mostra(q.value); history.replaceState(null, "", "#" + encodeURIComponent(q.value)); });
document.querySelectorAll(".esempi a").forEach(a => a.addEventListener("click", () => { q.value = a.textContent; form.requestSubmit(); }));
if (location.hash.length > 1) { q.value = decodeURIComponent(location.hash.slice(1)); mostra(q.value); }
</script>
</body>
</html>
"""


def main():
    indice = costruisci_indice()
    dati = json.dumps(indice, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = MODELLO.replace("__INDICE__", dati).replace("__DATA__", date.today().strftime("%d/%m/%Y"))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Pagina scritta in {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
