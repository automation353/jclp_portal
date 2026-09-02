"""
Single source of truth for JCPL's organisational structure.

The 21 formal departments and the Purchase department's work portals, taken
verbatim from the approved portal prototype. Pure data — no Django imports —
so anything (models, serialisers, the legacy template UI) can import it
without circularity.

``is_open`` marks a department whose modules are actually built. Everything
else renders as a SOON placeholder, exactly as in the prototype.
"""

DEPARTMENTS = [
    {"slug": "accounts", "name": "Accounts", "icon": "📒",
     "description": "Ledgers, payables, receivables, MIS.", "is_open": False},
    {"slug": "aftermarket-sales", "name": "Aftermarket Sales", "icon": "🔧",
     "description": "Spares & replacement clamp sales.", "is_open": False},
    {"slug": "central-engineering", "name": "Central Engineering", "icon": "🏗️",
     "description": "Plant engineering & projects.", "is_open": False},
    {"slug": "costing", "name": "Costing", "icon": "🧾",
     "description": "Product costing, BOM & margins.", "is_open": False},
    {"slug": "design-and-development", "name": "Design & Development", "icon": "📐",
     "description": "New product design & drawings.", "is_open": False},
    {"slug": "despatch", "name": "Despatch", "icon": "🚚",
     "description": "Dispatch, logistics & delivery.", "is_open": False},
    {"slug": "digital-marketing", "name": "Digital Marketing", "icon": "📣",
     "description": "Web, campaigns & lead generation.", "is_open": False},
    {"slug": "hr", "name": "HR", "icon": "👥",
     "description": "Attendance, payroll, KRA scoring.", "is_open": False},
    {"slug": "it", "name": "IT", "icon": "💻",
     "description": "Systems, ERP support & security.", "is_open": False},
    {"slug": "international-trade", "name": "International Trade", "icon": "🌐",
     "description": "Exports, imports & compliance.", "is_open": False},
    {"slug": "maintenance", "name": "Maintenance", "icon": "🛠️",
     "description": "Machine upkeep & breakdowns.", "is_open": False},
    {"slug": "oem-sales", "name": "OEM Sales", "icon": "🤝",
     "description": "Original-equipment customer sales.", "is_open": True},
    {"slug": "operations", "name": "Operations", "icon": "⚙️",
     "description": "Production plan, WIP, reconciliation.", "is_open": True},
    {"slug": "ppc", "name": "PPC", "icon": "📋",
     "description": "Production planning & control.", "is_open": True},
    {"slug": "production", "name": "Production", "icon": "🏭",
     "description": "Strip line & shop-floor output.", "is_open": False},
    {"slug": "purchase", "name": "Purchase", "icon": "🛒",
     "description": "RM planning, EBQ, POs, suppliers.", "is_open": True},
    {"slug": "quality", "name": "Quality", "icon": "✅",
     "description": "Inspection, QC & certifications.", "is_open": False},
    {"slug": "s-and-op", "name": "S&OP", "icon": "🎯",
     "description": "Sales & Operations Planning — cross-functional monthly plan.",
     "is_open": True},
    {"slug": "safety", "name": "Safety", "icon": "🦺",
     "description": "EHS, audits & incident tracking.", "is_open": False},
    {"slug": "store", "name": "Store", "icon": "📦",
     "description": "Inventory, GRN, issue & return.", "is_open": False},
    {"slug": "technical-sourcing", "name": "Technical Sourcing", "icon": "🔎",
     "description": "Vendor discovery & technical evaluation.", "is_open": False},
    {"slug": "tool-room", "name": "Tool Room", "icon": "🧰",
     "description": "Dies, tooling & maintenance.", "is_open": False},
]

# Work portals inside the Purchase department. "live" tiles are wired to real
# endpoints; "soon" tiles are placeholders.
PURCHASE_PORTALS = [
    {"slug": "rm-requirement", "name": "RM Requirement", "icon": "🧮",
     "description": "What raw material to buy, based on stock vs reorder level.",
     "status": "live"},
    {"slug": "ebq", "name": "Economic Batch Qty", "icon": "📐",
     "description": "Optimal order/batch size for each raw material.",
     "status": "live"},
    {"slug": "purchase-planning", "name": "Purchase Planning", "icon": "🗂️",
     "description": "Upload the purchase planning file for the cycle.",
     "status": "live"},
    {"slug": "purchase-orders", "name": "Purchase Orders", "icon": "📄",
     "description": "Raise, approve & track POs.", "status": "soon"},
    {"slug": "supplier-master", "name": "Supplier Master", "icon": "🏭",
     "description": "Vendor list, rates, lead times, ratings.", "status": "soon"},
]

# "Management" isn't a department — it's the catch-all for accounts (the Super
# Admin) that aren't scoped to one. Kept separate so it never shows up as a
# tile on the Departments screen.
MANAGEMENT = "Management"

DEPARTMENT_NAMES = [d["name"] for d in DEPARTMENTS]


def get_department(slug):
    return next((d for d in DEPARTMENTS if d["slug"] == slug), None)


def get_purchase_portal(slug):
    return next((p for p in PURCHASE_PORTALS if p["slug"] == slug), None)
