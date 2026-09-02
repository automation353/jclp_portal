"""
LEGACY — the seven-department sidebar of the original server-rendered UI.

The real org structure now lives in ``portal/data.py`` (21 departments) and
drives both the React portal and ``User.department``. This list is kept only
so the server-rendered Team Accounts and Login Activity pages keep rendering
their sidebar until they are ported into the React portal, at which point this
module and the ``dashboard`` app's views/templates can be deleted outright.

Do not add departments here — add them to ``portal/data.py``.
"""

MODULES = [
    {
        "number": "01",
        "slug": "purchase",
        "name": "Purchase",
        "tagline": "Vendors, purchase orders and raw-material intake",
        "icon": "purchase",
        "columns": ["PO Number", "Vendor", "Item", "Quantity", "Status", "Date"],
    },
    {
        "number": "02",
        "slug": "hr",
        "name": "H/R",
        "tagline": "Employee records, attendance and payroll",
        "icon": "hr",
        "columns": ["Employee ID", "Name", "Department", "Designation", "Status"],
    },
    {
        "number": "03",
        "slug": "accounts",
        "name": "Accounts",
        "tagline": "Vouchers, ledgers and payment tracking",
        "icon": "accounts",
        "columns": ["Voucher No.", "Type", "Party", "Amount", "Status"],
    },
    {
        "number": "04",
        "slug": "sales",
        "name": "Sales",
        "tagline": "Customer orders, dispatch and revenue",
        "icon": "sales",
        "columns": ["Order No.", "Customer", "Product", "Quantity", "Value", "Status"],
    },
    {
        "number": "05",
        "slug": "operations",
        "name": "Operations",
        "tagline": "Shop-floor work orders and production stages",
        "icon": "operations",
        "columns": ["Work Order", "Line", "Product", "Stage", "Status"],
    },
    {
        "number": "06",
        "slug": "design-and-operation",
        "name": "Design and Operation",
        "tagline": "Drawings, revisions and engineering change requests",
        "icon": "design",
        "columns": ["Drawing No.", "Product", "Revision", "Stage", "Owner"],
    },
    {
        "number": "07",
        "slug": "sales-and-operation",
        "name": "Sales and Operation",
        "tagline": "S&OP planning — demand vs. production capacity",
        "icon": "sop",
        "columns": ["S&OP Cycle", "Product", "Forecast Qty", "Actual Qty", "Variance"],
    },
]


def get_module(slug):
    return next((m for m in MODULES if m["slug"] == slug), None)


def get_accessible_modules(user):
    """Super Admins see every department. Admins see only the single
    department their account is assigned to (matched against ``User.department``,
    case-insensitively — an unassigned or unrecognised department yields none)."""
    if not getattr(user, "is_authenticated", False):
        return []
    if user.is_super_admin:
        return MODULES
    dept = (user.department or "").strip().lower()
    if not dept:
        return []
    return [m for m in MODULES if m["name"].lower() == dept]
