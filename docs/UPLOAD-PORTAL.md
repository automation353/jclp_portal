# Excel → Google Sheet Daily Dump Portal

A tiny web page for uploading daily Excel reports. An n8n workflow parses the
file and refreshes the target Google Sheet tab, and a Google Apps Script then
mirrors a subset of highlighted columns into a companion tab. Two report
types are supported side by side — **DPR** (stock valuation) and **Purchase
Orders** — from a single upload page.

## What's where

```
protal_for_datadumping/
├── README.md              ← you are here
├── SETUP.md               ← step-by-step deploy walkthrough
├── portal/
│   └── index.html         ← self-contained upload page (open in a browser)
├── n8n/
│   ├── dpr-workflow.json  ← import into n8n as the DPR workflow
│   └── po-workflow.json   ← import into n8n as the Purchase Order workflow
└── apps-script/
    └── sync-columns.gs    ← paste into the sheet's Extensions → Apps Script
```

- **`portal/index.html`** is a single self-contained HTML file (no build step,
  no dependencies). Open it directly, host it anywhere static, or drop it into
  an `<iframe>` on your existing portal.
- **`n8n/*.json`** are two independent n8n workflows. Import each once and toggle
  Active. Both write into the same Google Sheet but into different tabs.
- **`apps-script/sync-columns.gs`** is one Apps Script that handles both flows.
  The n8n workflow calls its Web app URL after every upload — no query param
  for DPR, `?type=po` for PO.

## Data flow at a glance

```
Upload page ── (POST xlsx) ──► n8n Webhook ──► Extract + Bundle
                                                     │
                                                     ▼
                                     Clear + Rewrite source tab
                                                     │
                                                     ▼
                                     HTTP POST to Apps Script Web app
                                                     │
                                                     ▼
                              Copy highlighted columns → target tab
                              (DPR also appends into `combined` history)
```

## Google Sheet tabs used

| Tab                       | Written by            | Purpose |
| ------------------------- | --------------------- | ------- |
| `stock_valuation`         | n8n (DPR workflow)    | Fresh raw upload each day, all columns |
| `stock_valuation_columns` | Apps Script           | Subset (only the columns you highlight) |
| `combined`                | Apps Script           | Append-only history of `stock_valuation_columns` batches |
| `po`                      | n8n (PO workflow)     | Fresh raw PO upload each day, all columns |
| `po_highlighted_columns`  | Apps Script           | Subset (only the columns highlighted in `po`) |

Which columns get mirrored is controlled by **which header cells you highlight**
with a fill color in `stock_valuation` (or `po`). The Apps Script captures those
names once and remembers them — later uploads wipe the highlight fill, but the
saved names stay.

## Portal → n8n mapping

The portal has a **📊 DPR Report / 📦 Purchase Order** selector at the top.
Whichever is active decides which webhook it POSTs to:

| Selector button   | Webhook path                       | Workflow file          |
| ----------------- | ---------------------------------- | ---------------------- |
| 📊 DPR Report     | `/webhook/excel-upload`            | `n8n/dpr-workflow.json` |
| 📦 Purchase Order | `/webhook/purchase-order-upload`   | `n8n/po-workflow.json`  |

Both webhooks live on the same n8n cloud host — currently hardcoded to
`https://jollyclamps.app.n8n.cloud/…` inside [portal/index.html](portal/index.html)
(look for the `WEBHOOK_URLS` object; change it if you move to a different n8n
instance).

## Deploying / setting this up from scratch

See **[SETUP.md](SETUP.md)** for the full step-by-step walkthrough — importing
the workflows, wiring the credentials, deploying the Apps Script Web app,
capturing the highlighted columns, and testing.

## Things worth knowing

- **`executeOnce` must be ON** on the "Sync … via Apps Script" HTTP node in
  both workflows. Otherwise n8n fires the HTTP call once per row, floods Apps
  Script, and hits Google's concurrent-execution cap. Symptom: German error
  `Zu viele gleichzeitige Aufrufe: Tabellen`.
- **Apps Script Web app access must be "Anyone"**, not "Anyone within
  [your-workspace-domain]". Domain-restricted deployments redirect n8n to a
  login page. Symptom: n8n's HTTP node output starts with `window['_ppConfig']`
  or contains a Google sign-in HTML page.
- **Every code change to the Apps Script requires a fresh Web app deployment**
  (Deploy → Manage deployments → pencil-edit → Version: *New version* → Deploy).
  Otherwise the old code keeps running at the URL.
- **Tab-name lookup is now forgiving** (case-insensitive + whitespace-tolerant),
  so small typos don't break anything. If a source tab really is missing, the
  Apps Script returns a clear error listing every tab it *did* find.
