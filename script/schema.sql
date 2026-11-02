-- Schema del database dell'inventario (fasi 1 e 2).
-- Tabelle: voci, annotazioni, segmenti.
-- Regola fissa: il testo dell'inventario non si altera mai; tutte le
-- elaborazioni vivono in campi o tabelle separate.

PRAGMA foreign_keys = ON;

-- Una riga per ogni numero d'inventario così come compare nel documento.
CREATE TABLE IF NOT EXISTS voci (
    id                  INTEGER PRIMARY KEY,  -- identificativo interno, in ordine di documento
    numero_originale    TEXT NOT NULL,        -- numero esattamente come scritto («542 a.», «1596-bis», «3074 (con 3079).»)
    numero              TEXT NOT NULL,        -- numero ripulito del punto finale («542 a», «2528 bis»)
    numero_base         INTEGER NOT NULL,     -- parte numerica iniziale (542, 2528, 2630…)
    chiave_ordinamento  TEXT NOT NULL,        -- base.sottonumero.variante, es. 02635.016.1 = 2635/16 bis
    tipo_numero         TEXT NOT NULL,        -- semplice | lettera | bis | sottonumero | sottonumero_bis | sottonumero_intervallo | fusa | annotato | omesso
    numeri_compresi     TEXT,                 -- per le voci fuse: numeri coperti (es. «2565,2566»)
    sezione             TEXT,                 -- intestazione di sezione in vigore (es. «Archivio Manzano»)
    testo_integrale     TEXT NOT NULL,        -- tutto il contenuto della voce nel .docx, intatto (paragrafi uniti da \n)
    testo               TEXT NOT NULL,        -- descrizione: senza numero, senza coda, senza annotazioni
    coda                TEXT,                 -- riga/e di coda originali (più righe unite da \n)
    supporto            TEXT,                 -- campo della coda: Cartaceo, Membranaceo, Pergam.…
    volumi              TEXT,                 -- campo della coda: consistenza («1 vol.», «7 voll.», «1 vol., 5 fascc.»)
    stato               TEXT,                 -- campo della coda: stato di conservazione (b., m., c.…)
    provenienza         TEXT,                 -- campo della coda: provenienza (dono, acquisto, legato…)
    paragrafo_inizio    INTEGER NOT NULL,     -- indice del primo paragrafo nel .docx (0 = primo paragrafo)
    paragrafo_fine      INTEGER NOT NULL,     -- indice dell'ultimo paragrafo della voce
    residuo             TEXT                  -- testo che il parser non ha saputo classificare (mai perso)
);
CREATE INDEX IF NOT EXISTS ix_voci_chiave ON voci(chiave_ordinamento);
CREATE INDEX IF NOT EXISTS ix_voci_numero ON voci(numero);

-- Annotazioni tra quadre con etichetta in grassetto ([Nota a margine: …] ecc.).
-- Le correzioni del curatore («Marlupino [Morlupino]») NON sono annotazioni:
-- restano nel testo.
CREATE TABLE IF NOT EXISTS annotazioni (
    id                  INTEGER PRIMARY KEY,
    voce                INTEGER REFERENCES voci(id),  -- NULL se l'annotazione riguarda l'indice in generale
    sede                TEXT NOT NULL,        -- testo | coda | indice
    tipo                TEXT NOT NULL,        -- tipo normalizzato: nota_a_margine, nota, commento_del_compilatore…
    etichetta_originale TEXT NOT NULL,        -- etichetta come scritta («Note a margine», «Da qui mano diversa. Nota a margine»)
    testo               TEXT NOT NULL,        -- contenuto dell'annotazione dopo i due punti
    testo_originale     TEXT NOT NULL,        -- annotazione completa, parentesi comprese, come nel .docx
    posizione           INTEGER,              -- offset in voci.testo (o voci.coda) dove l'annotazione stava
    paragrafo           INTEGER NOT NULL,     -- indice del paragrafo nel .docx
    etichetta_grassetto INTEGER NOT NULL      -- 1 se l'etichetta è in grassetto nel .docx (controllo)
);
CREATE INDEX IF NOT EXISTS ix_annotazioni_voce ON annotazioni(voce);

-- Parti di una voce delimitate dai soli riferimenti presenti nel testo.
CREATE TABLE IF NOT EXISTS segmenti (
    id          INTEGER PRIMARY KEY,
    voce        INTEGER NOT NULL REFERENCES voci(id),
    ordine      INTEGER NOT NULL,             -- posizione del segmento nella voce (1, 2, …): solo ordinamento, non è un'etichetta
    tipo        TEXT NOT NULL,                -- voce_intera | preambolo | riferimento | chiusura
    etichetta   TEXT NOT NULL DEFAULT '',     -- riferimento originale («fol. 45-47», «4°», «Fasc. 2°», «a)», nome nell'elenco); vuota per voce_intera, preambolo, chiusura
    testo       TEXT NOT NULL,                -- testo del segmento = voci.testo[inizio:fine]
    inizio      INTEGER NOT NULL,             -- offset iniziale in voci.testo
    fine        INTEGER NOT NULL              -- offset finale (escluso) in voci.testo
);
CREATE INDEX IF NOT EXISTS ix_segmenti_voce ON segmenti(voce);
