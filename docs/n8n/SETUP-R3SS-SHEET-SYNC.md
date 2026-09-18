# R3SS Sheet Sync — n8n + Google Sheet Setup

## Overview

Django sends R3SS data → n8n webhook → Google Sheet.  
9 tabs in one sheet. One n8n workflow handles all 9.

**Sheet ID:** `1AHkBgdOLO4YZO6vBqVQHNPmlT-IwFygCf2O8rpidRDU`  
**Webhook:** `JCLP_PPC_R3SS_WEBHOOK` env var (already configured in `/root/.env`)

---

## Step 1 — Verify Google Sheet has all 9 tabs

Open the R3SS sheet and make sure these 9 tabs exist (create any missing ones):

| Tab Name | Purpose | Rows |
|----------|---------|------|
| **PLAN** | Day-wise production plan per item | 52 items × 30+ columns |
| **_MAP** | Calendar metadata (dates, weeks, working days) | 4 rows |
| **CONTROL** | 10 acceptance tests | 10 rows |
| **_IMP_MASTER** | Joined master data | 78 items |
| **_IMP_DEMAND** | Demand transaction log | varies |
| **_IMP_FG** | Current FG stock (opening + receipt + issued + closing) | 52 items |
| **_IMP_FG_OPEN** | Month-start FG opening balance | 52 items |
| **_IMP_DJR** | Production entries this month | varies |
| **_IMP_INVOICE** | Dispatch (issued) data | 52 items |

Tab names must be **exact** (case-sensitive, including the underscore prefix).

---

## Step 2 — Import the n8n workflow

1. Go to **https://jollyclamps.app.n8n.cloud** → Workflows
2. Click **Import from File**
3. Select: `docs/n8n/7-ppc-r3ss-sheet-sync-v3.json`
4. The workflow will appear as "7 — PPC R3SS Sheet Sync v3"

---

## Step 3 — Set Google credentials on ALL nodes

This is the most common issue — PLAN and _IMP_MASTER were empty because credentials weren't set.

1. Open the imported workflow
2. For **each Google Sheets node** (18 nodes total — 9 Clear + 9 Write):
   - Double-click the node
   - In the **Credential** dropdown, select your Google Sheets OAuth2 credential
   - Click **Save**
3. The nodes have a placeholder `GOOGLE_CRED_ID` — you MUST replace it

**Quick check:** Click each node name below and verify credential is set:
- Clear PLAN / Write PLAN
- Clear _MAP / Write _MAP
- Clear CONTROL / Write CONTROL
- Clear _IMP_MASTER / Write _IMP_MASTER  ← **this was empty before**
- Clear _IMP_DEMAND / Write _IMP_DEMAND
- Clear _IMP_FG / Write _IMP_FG
- Clear _IMP_FG_OPEN / Write _IMP_FG_OPEN
- Clear _IMP_DJR / Write _IMP_DJR
- Clear _IMP_INVOICE / Write _IMP_INVOICE

---

## Step 4 — Activate the workflow

1. Toggle the workflow to **Active** (top right)
2. The webhook URL will be: `https://jollyclamps.app.n8n.cloud/webhook/ppc-r3ss`
3. This matches `JCLP_PPC_R3SS_WEBHOOK` in `/root/.env`

---

## Step 5 — Test from Django

Run the R3SS compute which triggers sync:

```bash
cd /root/jclp_automation_portal/jcpl
source .venv/bin/activate
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jcpl.settings')
django.setup()
from ppc_data.sheet_sync import sync_r3ss_to_sheet
result = sync_r3ss_to_sheet('2026-09')
for tab, res in result.items():
    print(f'{tab}: {res}')
"
```

All 9 tabs should show `ok: True, http_status: 200`.

Then check the Google Sheet — all 9 tabs should have data.

---

## Step 6 — Deactivate old workflow

If you have an older version of the R3SS sync workflow (v1 or v2), **deactivate it** to avoid double-writes. Only one workflow should handle the `ppc-r3ss` webhook path.

---

## Troubleshooting

**PLAN or _IMP_MASTER still empty?**
- Most likely: Google credential not set on those specific Clear/Write nodes
- Check: Open the node → Credential dropdown → must show your Google Sheets credential, not "Select..."
- After setting credential: run the test command above

**HTTP 200 but no data in sheet?**
- n8n returns 200 immediately (responseMode: onReceived), before processing
- Check n8n execution log for errors: Executions → filter by this workflow
- Common error: "Sheet not found" → tab name doesn't match exactly

**_tabName column appearing in sheet?**
- You're on v2. Import v3 which has Strip Meta nodes that remove internal fields

---

## Workflow Architecture (v3)

```
Webhook (POST /ppc-r3ss)
  ↓
Extract Rows (Code: flatten JSON → n8n items, add _tabName)
  ↓
Route by Tab (Switch: 9 outputs based on _tabName)
  ↓ × 9 branches
Clear {tab} → Strip Meta → Write {tab}
```

Each tab gets: Clear → Strip `_tabName` → Append rows to Google Sheet.
