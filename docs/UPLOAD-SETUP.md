# Setup walkthrough

Follow these once. After that, uploads Just Work — you'll only revisit this
guide if something breaks or you're rebuilding on a fresh Google account /
n8n instance.

## 0. Prerequisites

- A Google account with a spreadsheet you can write to.
- An n8n instance you can log into (cloud or self-hosted).
- The Excel files you'll be uploading each day (a DPR / stock valuation
  report and/or a Purchase Order report).

## 1. Prepare the Google Sheet

1. Create (or pick) the Google Spreadsheet you'll use as the destination.
2. Create these tabs by name (exact spelling — lowercase, underscores):
   - `stock_valuation`
   - `stock_valuation_columns` *(will auto-create if missing, but pre-making is fine)*
   - `combined` *(auto-creates too)*
   - `po`
   - `po_highlighted_columns` *(auto-creates too)*
3. Copy the spreadsheet's ID from the URL — the long string between
   `/spreadsheets/d/` and `/edit`. You'll paste it into the n8n workflows.

## 2. Import the n8n workflows

For each of `n8n/dpr-workflow.json` and `n8n/po-workflow.json`:

1. In n8n → **Workflows → Add workflow → (⋯ menu) → Import from File**.
2. Select the JSON file.
3. Open **every** Google Sheets node in the workflow and:
   - Under **Credential**, pick or create the Google Sheets OAuth2 credential
     for the account that owns your spreadsheet.
   - Under **Document**, replace the placeholder ID with your spreadsheet's ID
     (or click the picker and select from your Drive).
   - Under **Sheet**, verify the correct tab name is picked (`stock_valuation`
     for the DPR workflow, `po` for the PO workflow).
4. Open the "Sync … via Apps Script" HTTP Request node and (for now) leave the
   URL placeholder — you'll paste the real one after step 4.
5. Verify the HTTP Request node has **Execute Once = ON** (Settings tab on the
   node). This is critical — if it's off, Google will rate-limit you.
6. Toggle the workflow **Active** (top right).
7. Copy the webhook's **Production URL** from the Webhook node — you'll
   configure the portal to point at these next.

## 3. Point the portal at your webhooks

Open [portal/index.html](portal/index.html) in a text editor. Near the top of
the `<script>` block, find:

```js
const WEBHOOK_URLS = {
  dpr: 'https://jollyclamps.app.n8n.cloud/webhook/excel-upload',
  po:  'https://jollyclamps.app.n8n.cloud/webhook/purchase-order-upload'
};
```

Replace both URLs with the production webhook URLs from step 2.7 above.
Save the file. Test-open it in a browser — you should see the upload page
with two buttons at the top.

## 4. Deploy the Apps Script

1. Open your Google Spreadsheet → **Extensions → Apps Script**.
2. Delete the placeholder code. Paste in the entire contents of
   [apps-script/sync-columns.gs](apps-script/sync-columns.gs). Save.
3. In the toolbar, click **Deploy → New deployment**.
4. Click the gear icon (⚙) → **Web app**.
5. Fill in:
   - **Description**: `Excel upload column sync`
   - **Execute as**: **Me** (your Google account)
   - **Who has access**: **Anyone** *(not "Anyone within your workspace" — that
     blocks n8n from calling it; treat the URL like a password instead)*
6. Click **Deploy**. Google will prompt you to authorize permissions the first
   time — go through **Advanced → Go to [project name] (unsafe) → Allow**.
7. Copy the **Web app URL** it gives you (looks like
   `https://script.google.com/macros/s/AKfycb…/exec`).

## 5. Capture the reference columns (one-time per report type)

The Apps Script needs to know **which columns to mirror**. You tell it by
highlighting header cells with a fill color, then running a "capture" function
once. The names get saved to the document's persistent properties, so they
survive future uploads even though the highlighting itself doesn't.

For **DPR**:

1. Do one manual DPR upload through the portal so the `stock_valuation` tab
   has headers (or upload directly in n8n's Webhook test mode).
2. In the `stock_valuation` tab, select the header cells for the columns you
   want mirrored → apply any fill color (Format → Fill color → pick anything
   non-white).
3. In the Apps Script editor, in the function-name dropdown at the top, pick
   **`captureHighlightedColumnNames`** → click ▶ Run.
4. Check the Execution log — it should print something like
   `[stock_valuation] Captured 6 column names: Location Code, Item Code, …`.

For **PO**:

1. Do one manual PO upload so the `po` tab has headers.
2. Highlight the desired header cells in the `po` tab.
3. In the Apps Script editor, pick **`captureHighlightedColumnNamesPO`** →
   click ▶ Run. Confirm the log shows the captured names.

If you ever want to change the mirrored column set, just re-highlight and
re-run the matching capture function — it overwrites the saved list.

## 6. Wire the Apps Script URL back into n8n

For **each** workflow:

1. Open the "Sync … via Apps Script" HTTP Request node.
2. Paste the Web app URL from step 4.7 into the **URL** field.
3. **PO workflow only**: also add the query parameter `type=po` — either by
   turning on "Send Query Parameters" and adding a row `{name: type, value: po}`,
   or by appending `?type=po` directly to the URL. This is what tells the
   Apps Script to run the PO sync (not the DPR one).
4. Save the workflow. It's still Active from step 2.6.

## 7. Test end-to-end

1. Open the portal page in a browser.
2. Click **📊 DPR Report** → drop your DPR Excel file → click Upload.
3. Wait ~30–60 seconds (large files can take a minute).
4. Check the spreadsheet:
   - `stock_valuation` — fresh data (previous data replaced).
   - `stock_valuation_columns` — just the highlighted subset.
   - `combined` — same rows, appended to whatever was there previously.
5. Click **📦 Purchase Order** → drop your PO Excel file → click Upload.
6. Check the spreadsheet:
   - `po` — fresh data.
   - `po_highlighted_columns` — just the highlighted subset.

If any tab doesn't get filled, run **`diagnoseDPR`** (or **`listTabs`**) from
the Apps Script editor and check the Execution log — the diagnostic messages
point at the exact cause (missing capture, header mismatch, wrong spreadsheet
binding, etc.).

## Troubleshooting quick reference

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Portal spins forever on "Uploading…" | Webhook `responseMode` isn't `onReceived` | Open the Webhook node → **Respond → Immediately** |
| n8n HTTP node output = Google login HTML | Web app access is "Anyone within [workspace]" | Redeploy Apps Script with access = **Anyone** |
| n8n HTTP node output = "Zu viele gleichzeitige Aufrufe" | Execute Once off → 1 request per row → rate limit | Toggle **Execute Once = ON** on the HTTP node |
| `Sheet "..." not found` | Tab name mismatch (rename, typo, case) | Rename the tab OR wait — the script's forgiving lookup handles most cases. Run `listTabs` to see what's actually there |
| `None of the saved column names were found` | Captured names don't match current headers | Re-highlight in the source tab → re-run the matching capture function |
| Apps Script code changes don't take effect | Web app deployment wasn't refreshed | Deploy → Manage deployments → pencil-edit → **Version: New version** → Deploy |
