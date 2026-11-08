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
PAGES = RADICE / "docs" / "index.html"      # copia pubblicata con GitHub Pages (cartella /docs)

MODELLO = r"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fondo Principale — ricerca</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,500;0,600;0,700;1,500;1,600&family=Roboto:wght@700&family=Roboto+Condensed:wght@300;400;700&display=swap" rel="stylesheet">
<style>
/* Stile ripreso da Teche Udine (www.techeudine.it/fondo-principale), senza loghi:
   colori --color1…--color4, Roboto Condensed per il testo, Lora per i titoli, Roboto maiuscolo per le etichette. */
:root {
  --color1: #bcb439; --colorHref: #7d7a00; --color2: #2d2b30; --color3: #3d3938; --color4: #575756;
  --sfondo: #ffffff; --carta: #ffffff; --fascia: #f1eeea; --testo: var(--color4); --scuro: var(--color2);
  --tenue: #7b7a78; --linea: #d9d5cf; --accento: var(--colorHref); --evidenza: #ebe6a6;
  --font-testo: "Roboto Condensed", "Arial Narrow", sans-serif; --font-titoli: "Lora", Georgia, serif;
  --font-etichette: "Roboto", "Helvetica Neue", Arial, sans-serif; --larghezza: 1200px;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; color-scheme: light; }   /* come Teche: sempre chiaro */
body { margin: 0; background: var(--sfondo); color: var(--testo); font: 18px/1.5 var(--font-testo); }
a { color: var(--accento); text-decoration: none; } a:hover { text-decoration: underline; }
.container { max-width: var(--larghezza); margin: 0 auto; padding: 0 16px; }
.lyt { padding-top: 40px; min-height: 70vh; }
.row-1 { display: flex; }
.column-1 { width: 275px; flex: none; }
.column-2 { width: calc(100% - 275px); padding-left: 25px; min-width: 0; }
.section { color: #fff; background: var(--color1); letter-spacing: 1.5px; font: italic 500 28px/34px var(--font-titoli);
  margin: 0; padding: 0 0 0 5px; }
h1.page-title { font: 600 34px/1.2 var(--font-titoli); color: var(--scuro); margin: 0 0 6px; }
.sottotitolo { font: italic 500 19px/1.4 var(--font-titoli); color: var(--testo); margin: 0 0 4px; }
.ricerca { padding: 20px 0; border-bottom: 1px solid var(--testo); margin-bottom: 8px; }
form { display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: center; }
input[type=search] { flex: 1 1 260px; min-width: 0; font: 18px var(--font-testo); padding: 11px; border: 1px solid var(--color4);
  border-radius: 0; background: var(--carta); color: var(--scuro); }
input[type=search]::placeholder { color: #46494c; opacity: .5; }
input[type=search]:focus { outline: 2px solid var(--color1); outline-offset: 0; }
button { background: var(--color1); color: #fff; border: 0; font: bold 20px/20px var(--font-testo); width: 150px;
  padding: 15px 0; text-transform: uppercase; cursor: pointer; }
button:hover { filter: brightness(.93); }
.opzioni { font-size: 16px; color: var(--tenue); margin-top: 12px; }
.parte { margin-right: 16px; white-space: nowrap; cursor: pointer; }
.esempi a { cursor: pointer; margin-right: 12px; font-weight: bold; }
.stato { font: bold 19px var(--font-etichette); text-transform: uppercase; color: var(--scuro); margin: 22px 0 4px; }
.stato::first-letter { color: var(--color1); }
.forme { font-size: 15px; color: var(--tenue); margin: 0 0 18px; }
form.segnala { display: block; margin: 12px 0 0; }
.segnala label { display: block; margin-bottom: 4px; }
.segnala-riga { display: flex; gap: 8px; max-width: 640px; }
.segnala input { flex: 1 1 auto; min-width: 0; font: inherit; font-size: 16px; padding: 5px 8px; border: 1px solid #fff; background: #fff; color: var(--color2); }
.segnala button, .segnala-riga button { flex: 0 0 auto; width: auto; font: inherit; font-size: 16px; font-weight: bold; padding: 5px 16px;
  border: 1px solid #fff; background: var(--color2); color: #fff; cursor: pointer; text-transform: none; }
#segnala-esito { display: block; margin-top: 4px; min-height: 1em; }
.forme a.forma { font-family: var(--font-testo); background: var(--fascia); padding: 1px 5px; color: inherit; text-decoration: none; cursor: pointer; display: inline-block; margin: 2px 0; }
.forme a.forma:hover { text-decoration: underline; color: var(--colorHref); }
.voce { border-top: 1px solid var(--linea); padding: 14px 0 12px; }
.voce h2 { font: bold 21px var(--font-etichette); text-transform: uppercase; color: var(--scuro); margin: 0 0 6px;
  display: flex; gap: 10px; flex-wrap: wrap; align-items: baseline; }
.voce h2::first-letter { color: var(--color1); }
.etichetta { font: italic 500 15px var(--font-titoli); text-transform: none; color: var(--accento); }
.punto { margin: 4px 0; overflow-wrap: anywhere; }
.punto .seg { font-weight: bold; color: var(--scuro); margin-right: 6px; }
mark { background: var(--evidenza); color: inherit; padding: 0 1px; }
.entita { font-size: 16px; color: var(--tenue); }
.entita b { color: var(--scuro); }
details { margin-top: 6px; } summary { font: italic 500 16px var(--font-titoli); color: var(--accento); cursor: pointer; }
.testo-voce { white-space: pre-wrap; background: var(--fascia); padding: 10px 14px; margin-top: 6px; font-size: 17px; }
footer { background: var(--color1); color: #fff; margin-top: 30px; padding: 16px 0; font-size: 16px; }
footer b { font-family: var(--font-titoli); font-weight: 600; }
@media (max-width: 991px) {
  .row-1 { display: block; } .column-1, .column-2 { width: 100%; padding-left: 0; }
  .section { margin-bottom: 16px; display: inline-block; padding-right: 10px; }
}
@media (max-width: 575px) { h1.page-title { font-size: 28px; } button { width: 100%; } .lyt { padding-top: 24px; } }
</style>
</head>
<body>
<div class="lyt"><div class="container"><div class="row-1">
  <div class="column-1"><div class="section">Ricerca</div></div>
  <div class="column-2">
  <h1 class="page-title">Fondo Principale</h1>
  <p class="sottotitolo">Inventario dei manoscritti, voci 1–4519</p>
  <p class="opzioni" style="margin-top:4px">Persone e luoghi in qualunque grafia.</p>
  <div class="ricerca">
  <form id="f"><input type="search" id="q" placeholder="Es. Zuan de Udene, Utinum, Florio Daniele, S. Pietro" autocomplete="off" autofocus aria-label="Nome di persona o di luogo">
  <button>Cerca</button></form>
  <div class="opzioni"><label class="parte"><input type="checkbox" id="parte"> anche parte di parola</label> <span class="esempi">Prova: <a>Giovanni da Udine</a><a>Utinum</a><a>Jac. Pirona</a><a>Paulus Venetus</a><a>Ermes di Colloredo</a></span></div>
  </div>
  <div class="stato" id="stato">Scrivi un nome di persona o di luogo.</div>
  <div class="forme" id="forme"></div>
  <div id="risultati"></div>
  </div>
</div></div></div>
<footer><div class="container">
  La ricerca normalizza la grafia (maiuscole, accenti, j/i, y/i, doppie) e la estende con le varianti registrate:
  forme latine, venete e friulane, abbreviazioni, varianti dei nomi, correzioni del curatore, forme di Wikidata. Trova le voci attraverso la <b>forma di riferimento</b>
  (tutte le grafie registrate dello stesso nome, anche lontane) e nel <b>testo</b> (tutte le parole vicine nella voce);
  solo se non trova nulla, prova la ricerca <b>approssimata</b> (una lettera di differenza), segnalata accanto alla voce.
  I collegamenti a Wikidata e al Dizionario Biografico dei Friulani indicano la fonte della forma di riferimento. La forma di riferimento raccoglie
  grafie diverse dello stesso nome: non identifica una persona, e omonimi compaiono insieme.
  I collegamenti alle schede sono proposti in base al nome e agli anni citati nella voce e <b>possono riferirsi a un omonimo</b>:
  quando più schede sono compatibili, sono indicate tutte, con le date, e la scelta spetta al lettore.
  <form id="segnala" class="segnala"><label for="segnala-testo">Hai trovato una persona confusa con un'altra o un collegamento sbagliato? Segnalalo
  (le grafie diverse sono quelle del manoscritto, non errori):</label>
  <span class="segnala-riga"><input id="segnala-testo" type="text" maxlength="2000" required
    placeholder="voce e nome da correggere"><button>Invia</button></span>
  <span id="segnala-esito" role="status"></span></form>
  <p style="margin:12px 0 0">Trascrizione dall'inventario manoscritto a cura di Gregorio Grasselli · indice del __DATA__.</p>
</div></footer>
<script>
const IDX = __INDICE__;
const VUOTE = new Set(IDX.vuote);
const LUOGHI = new Set(IDX.luoghi);   // parole soprattutto di luogo: da sole non riconoscono una persona
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
function vocabolario() {       // parole dei testi e delle varianti, per la ricerca approssimata e per parte di parola
  if (!VOCAB) { VOCAB = new Set(); SEDI.forEach(sedi => sedi.forEach(([, , pw]) => pw.forEach(p => VOCAB.add(p[0]))));
    ENT.forEach(e => e.vs.forEach(vw => vw.forEach(w => VOCAB.add(w)))); }
  return VOCAB;
}
function cerca(domanda, parte = false) {
  let q = chiave(domanda);
  // solo parole di solito ignorate (titoli, particelle: «abate»): si cercano così come sono
  if (!q.length) q = parole(domanda).map(p => p[0]).filter(w => w);
  if (!q.length) return {q, ris: []};
  let insiemi = q.map(espandi);
  // parte di parola: ogni parola cercata (almeno 3 lettere) vale anche dentro parole più lunghe
  if (parte) insiemi = insiemi.map(s => { const n = new Set(s);
    vocabolario().forEach(w => { if ([...s].some(t => t.length >= 3 && w.includes(t))) espandi(w).forEach(x => n.add(x)); }); return n; }); const finestra = Math.max(q.length + 2, 4);
  const ris = new Map(); const add = (vi, h) => { if (!ris.has(vi)) ris.set(vi, []); ris.get(vi).push(h); };
  const soloLuoghi = q.every(t => LUOGHI.has(t));   // solo nomi di luogo: nessuna persona per forma
  for (const e of ENT) {
    if ((e.t !== "persona" || !soloLuoghi || ((e.c || []).length && insiemi.every(s => e.c.some(w => s.has(w)))
                                               && e.c.every(w => insiemi.some(s => s.has(w)))))
        && e.vs.some(vw => insiemi.every(s => [...s].some(w => vw.has(w)))))
      for (const [vi, sede, ini, fin] of e.m) add(vi, [1, sede === "testo" ? "t" : sede === "coda" ? "c" : sede, ini, fin, e]);
  }
  for (const [vi, hs] of nelTesto(insiemi, finestra)) for (const [s, i, f] of hs) add(vi, [2, s, i, f, null]);
  let approssimata = false;
  if (!ris.size) {
    const larghi = insiemi.map(s => { const n = new Set(s); s.forEach(t => { if (t.length >= 5) vocabolario().forEach(w => { if (distUno(t, w)) n.add(w); }); }); return n; });
    for (const [vi, hs] of nelTesto(larghi, finestra)) for (const [s, i, f] of hs) add(vi, [3, s, i, f, null]);
    approssimata = true;
  }
  const out = [...ris.entries()].map(([vi, hs]) => { hs.sort((a, b) => a[0] - b[0] || (a[1] !== "t") - (b[1] !== "t") || a[2] - b[2]); return {vi, hs, liv: hs[0][0]}; });
  out.sort((a, b) => a.liv - b.liv || a.vi - b.vi);
  return {q, insiemi, ris: out, approssimata};
}
const esc = s => s.replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const LIV = {1: "forma di riferimento", 2: "testo", 3: "approssimata"};
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
  const r = cerca(domanda, document.getElementById("parte").checked);
  const el = document.getElementById("risultati"), st = document.getElementById("stato"), fo = document.getElementById("forme");
  if (!r.q.length) { st.textContent = "Scrivi un nome di persona o di luogo."; fo.innerHTML = ""; el.innerHTML = ""; return; }
  fo.innerHTML = "Forme cercate: " + r.insiemi.map(s => { const xs = [...s];
    return xs.slice(0, 25).map(w => `<a class="forma" title="Cerca solo questa forma">${esc(w)}</a>`).join(" ") + (xs.length > 25 ? ` … e altre ${xs.length - 25}` : ""); }).join(" + ");
  st.textContent = `${r.ris.length} voci` + (r.approssimata && r.ris.length ? " (ricerca approssimata)" : "");
  el.innerHTML = r.ris.slice(0, 300).map(({vi, hs, liv}) => {
    const v = IDX.voci[vi]; const visti = new Set(); const punti = [];
    for (const h of hs) {        // niente doppioni: un tratto contenuto in uno già mostrato non si ripete
      const k = h[1] + h[2]; if (visti.has(k)) continue;
      if (punti.some(p => p[1] === h[1] && p[2] <= h[2] && h[3] <= p[3])) continue;
      visti.add(k); punti.push(h);
    }
    // schede del Dizionario (più d'una per gli omonimi: con la forma e gli anni) e pagine del curatore
    function collegamenti(d) {
      if (!d) return "";
      const per = new Map(); d.forEach(x => { if (!per.has(x[1])) per.set(x[1], []); per.get(x[1]).push(x); });
      return [...per].map(([fonte, xs]) => xs.every(x => !x[2])
        ? ` · <a href="${esc(xs[0][0])}" target="_blank" rel="noopener">${esc(fonte)}</a>`
        : ` · ${esc(fonte)}: ` + xs.map(x => `<a href="${esc(x[0])}" target="_blank" rel="noopener">${esc(x[2] || x[0])}</a>`).join(", ")).join("");
    }
    const ent = [...new Map(hs.filter(h => h[4]).map(h => [h[4].i, h[4]])).values()];
    const sedi = new Map(); punti.forEach(h => { if (!sedi.has(h[1])) sedi.set(h[1], []); sedi.get(h[1]).push([h[2], h[3]]); });
    return `<article class="voce"><h2>Voce ${esc(v.n)}${liv === 3 ? ` <span class="etichetta">ricerca approssimata</span>` : ""}</h2>` +
      punti.slice(0, 3).map(h => { const seg = segmento(v, h[1], h[2]);
        return `<div class="punto">${seg ? `<span class="seg">${esc(seg)}</span>` : ""}${frammento(testoSede(v, h[1]), h[2], h[3])}</div>`; }).join("") +
      (punti.length > 3 ? `<div class="entita">… e altri ${punti.length - 3} punti nella voce</div>` : "") +
      ent.map(e => `<div class="entita">Forma di riferimento${e.t === "luogo" ? " (luogo)" : e.t === "santo" ? " (santo)" : ""}: <b>${esc(e.f)}</b>` +
        (e.st === "validato" ? "" : " · da validare") + (e.q ? ` · <a href="https://www.wikidata.org/wiki/${e.q}" target="_blank" rel="noopener">Wikidata ${e.q}</a>` : "") +
        collegamenti(e.d) + `</div>`).join("") +
      `<details><summary>Testo della voce</summary><div class="testo-voce">${evidenzia(v.t, sedi.get("t") || [])}` +
      (v.c ? `\n\n<i>${evidenzia(v.c, sedi.get("c") || [])}</i>` : "") +
      v.a.map((a, k) => `\n\n[${evidenzia(a, sedi.get("a" + k) || [])}]`).join("") + `</div></details></article>`;
  }).join("") + (r.ris.length > 300 ? `<p class="stato">Mostrate le prime 300 voci di ${r.ris.length}.</p>` : "");
}
const form = document.getElementById("f"), q = document.getElementById("q");
form.addEventListener("submit", ev => { ev.preventDefault(); mostra(q.value); history.replaceState(null, "", "#" + encodeURIComponent(q.value)); });
// segnalazioni: si inviano in silenzio al modulo configurato in dati/liste/segnalazioni.json (un modulo
// Google: le risposte finiscono nel foglio del curatore), senza lasciare la pagina
const SEGNALA = __SEGNALA__;
document.getElementById("segnala").addEventListener("submit", async ev => {
  ev.preventDefault();
  const t = document.getElementById("segnala-testo"), esito = document.getElementById("segnala-esito");
  if (!SEGNALA.modulo) { esito.textContent = "Le segnalazioni non sono ancora attive."; return; }
  const dati = new URLSearchParams();
  dati.append(SEGNALA.campi.messaggio, t.value.trim());
  if (SEGNALA.campi.ricerca) dati.append(SEGNALA.campi.ricerca, q.value.trim());
  esito.textContent = "Invio in corso…";
  try {
    await fetch(SEGNALA.modulo, {method: "POST", mode: "no-cors", body: dati});
    t.value = ""; esito.textContent = "Grazie, la segnalazione è stata inviata.";
  } catch (e) { esito.textContent = "Invio non riuscito: controlla la connessione e riprova."; }
});
// le forme cercate sono cliccabili: una nuova ricerca per quella sola forma
document.getElementById("forme").addEventListener("click", ev => {
  const a = ev.target.closest("a.forma"); if (!a) return;
  q.value = a.textContent; form.requestSubmit(); window.scrollTo({top: 0, behavior: "smooth"});
});
document.getElementById("parte").addEventListener("change", () => { if (q.value.trim()) form.requestSubmit(); });
document.querySelectorAll(".esempi a").forEach(a => a.addEventListener("click", () => { q.value = a.textContent; form.requestSubmit(); }));
if (location.hash.length > 1) { q.value = decodeURIComponent(location.hash.slice(1)); mostra(q.value); }
</script>
</body>
</html>
"""


def main():
    indice = costruisci_indice()
    dati = json.dumps(indice, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    conf = RADICE / "dati" / "liste" / "segnalazioni.json"     # {"modulo": url formResponse, "campi": {...}}
    segnala = json.loads(conf.read_text(encoding="utf-8")) if conf.exists() else {"modulo": "", "campi": {}}
    html = MODELLO.replace("__INDICE__", dati).replace("__DATA__", date.today().strftime("%d/%m/%Y")) \
        .replace("__SEGNALA__", json.dumps(segnala, ensure_ascii=False))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    PAGES.write_text(html, encoding="utf-8")
    print(f"Pagina scritta in {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
