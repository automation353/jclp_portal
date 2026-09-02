"""Generate n8n workflow JSON files for all 17 ERP feeds.

Usage:
    python manage.py generate_n8n_erp_workflows [--outdir docs/n8n/erp]

Each workflow:
  - Schedule trigger (daily at the appropriate time)
  - HTTP Request node to pull from TCS iON ERP (placeholder URL)
  - Code node to clean / transform rows
  - HTTP Request node to POST to Django's /api/ppc-data/erp-landing/

The generated JSONs can be imported directly into n8n. You only need to:
  1. Configure the TCS iON HTTP credentials
  2. Set the correct ERP report URL for each workflow
  3. Set the Django server URL (default: http://200.141.14.164)
"""

import json
import os
import uuid

from django.core.management.base import BaseCommand

from ppc_data.field_maps.erp import ERP_REGISTRY


# Schedule times: daily feeds at 05:00, on_change at 06:00, weekly at Sunday 04:00
SCHEDULE_MAP = {
    "daily": {"hour": 5, "minute": 0, "cron": "0 5 * * *"},
    "on_change": {"hour": 6, "minute": 0, "cron": "0 6 * * *"},
    "weekly": {"hour": 4, "minute": 0, "cron": "0 4 * * 0"},
}

DJANGO_BASE_URL = "http://200.141.14.164"


def _uuid():
    return str(uuid.uuid4())


def _build_workflow(report_key, info):
    """Build a single n8n workflow JSON for an ERP feed."""
    field_map = info["field_map"]
    report_num = info["report_number"]
    freq = info["frequency"]
    schedule = SCHEDULE_MAP.get(freq, SCHEDULE_MAP["daily"])

    # Column names the ERP system sends (the "Excel header" side of the field map)
    erp_columns = list(field_map.values())

    workflow = {
        "name": f"ERP #{report_num} — {report_key} → Django ({freq})",
        "nodes": [
            # 1. Schedule trigger
            {
                "parameters": {
                    "rule": {
                        "interval": [{"triggerAtHour": schedule["hour"]}]
                    }
                },
                "id": _uuid(),
                "name": "Schedule Trigger",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [400, 300],
            },
            # 2. HTTP Request — pull from ERP
            {
                "parameters": {
                    "method": "GET",
                    "url": f"={{{{ $env.ERP_BASE_URL }}}}/api/reports/{report_key}",
                    "authentication": "genericCredentialType",
                    "genericAuthType": "httpHeaderAuth",
                    "options": {
                        "timeout": 120000,
                    },
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Accept", "value": "application/json"},
                        ]
                    },
                },
                "id": _uuid(),
                "name": "Pull from ERP",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [640, 300],
                "credentials": {
                    "httpHeaderAuth": {
                        "id": "PASTE_ERP_CREDENTIAL_ID",
                        "name": "TCS iON API Key",
                    }
                },
            },
            # 3. Code — clean and transform rows
            {
                "parameters": {
                    "jsCode": _build_transform_code(report_key, erp_columns),
                },
                "id": _uuid(),
                "name": "Clean & Transform",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [880, 300],
            },
            # 4. HTTP Request — POST to Django erp-landing
            {
                "parameters": {
                    "method": "POST",
                    "url": f"{DJANGO_BASE_URL}/api/ppc-data/erp-landing/",
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ JSON.stringify($input.first().json) }}",
                    "options": {
                        "timeout": 60000,
                    },
                },
                "id": _uuid(),
                "name": "POST to Django",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1120, 300],
            },
        ],
        "connections": {
            "Schedule Trigger": {
                "main": [
                    [{"node": "Pull from ERP", "type": "main", "index": 0}]
                ]
            },
            "Pull from ERP": {
                "main": [
                    [{"node": "Clean & Transform", "type": "main", "index": 0}]
                ]
            },
            "Clean & Transform": {
                "main": [
                    [{"node": "POST to Django", "type": "main", "index": 0}]
                ]
            },
        },
        "settings": {
            "executionOrder": "v1",
        },
        "tags": [
            {"name": "ERP Feed"},
            {"name": f"#{report_num}"},
            {"name": freq},
        ],
    }

    return workflow


def _build_transform_code(report_key, erp_columns):
    """Build the JS code for the n8n Code node that cleans ERP rows."""
    cols_json = json.dumps(erp_columns, indent=2)

    return f"""// ERP feed: {report_key}
// Expected columns from ERP: {', '.join(erp_columns[:5])}...
//
// Adapt the input parsing below to match your ERP's actual response format.
// The output must be a single item with {{report_key, rows, meta}}.

const input = $input.first().json;

// --- ADAPT THIS SECTION ---
// If your ERP returns {{data: [{{...}}, ...]}}:
let rawRows = input.data || input.rows || input.results || [];

// If the response IS the array directly:
if (Array.isArray(input)) rawRows = input;

// --- END ADAPT ---

const expectedColumns = {cols_json};

// Clean rows: trim strings, remove fully-empty rows
const cleanedRows = [];
for (const raw of rawRows) {{
  const row = {{}};
  let hasValue = false;

  for (const [key, value] of Object.entries(raw)) {{
    const cleanKey = String(key).replace(/\\r|\\n/g, ' ').replace(/\\s+/g, ' ').trim();
    if (!cleanKey) continue;

    if (value === null || value === undefined) continue;
    const strVal = String(value).trim();
    if (strVal === '') continue;

    row[cleanKey] = value;
    hasValue = true;
  }}

  if (hasValue) cleanedRows.push(row);
}}

// Build the payload for Django's /api/ppc-data/erp-landing/
return [{{
  json: {{
    report_key: '{report_key}',
    rows: cleanedRows,
    meta: {{
      pulled_at: new Date().toISOString(),
      report_name: '{report_key}',
      row_count: cleanedRows.length,
      source: 'n8n_scheduled',
    }}
  }}
}}];
"""


class Command(BaseCommand):
    help = "Generate n8n workflow JSON files for all 17 ERP feeds"

    def add_arguments(self, parser):
        parser.add_argument(
            "--outdir",
            default="docs/n8n/erp",
            help="Output directory for workflow JSON files (default: docs/n8n/erp)",
        )

    def handle(self, *args, **options):
        outdir = options["outdir"]
        os.makedirs(outdir, exist_ok=True)

        for report_key, info in sorted(
            ERP_REGISTRY.items(), key=lambda x: x[1]["report_number"]
        ):
            workflow = _build_workflow(report_key, info)
            filename = f"erp-{info['report_number']:02d}-{report_key}.json"
            filepath = os.path.join(outdir, filename)

            with open(filepath, "w") as f:
                json.dump(workflow, f, indent=2)

            self.stdout.write(
                f"  #{info['report_number']:2d} {report_key:25s} → {filepath}"
            )

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Generated {len(ERP_REGISTRY)} workflow files in {outdir}/"
        ))
        self.stdout.write(
            "\nNext steps:\n"
            "  1. Import each JSON into n8n (jollyclamps.app.n8n.cloud)\n"
            "  2. Set the ERP_BASE_URL environment variable in n8n\n"
            "  3. Create an 'TCS iON API Key' HTTP Header Auth credential\n"
            "  4. Adapt the 'Pull from ERP' URL to match your ERP API\n"
            "  5. Activate each workflow\n"
        )
