# JCPL Enterprise Portal — Jolly Clamps Pvt. Ltd.

Internal enterprise portal for Jolly Clamps Pvt. Ltd.: a **Django REST API**
backend with a **React (Vite)** front end, built to the approved portal
prototype.

The Purchase department's two analytical modules (RM Requirement, Economic
Batch Quantity) are wired to real Django models and logic. The other 20
departments are placeholder tiles.

## Architecture

```
jcpl/
├─ portal/          API + domain: 21 departments, RawMaterial, EBQ logic
│  ├─ data.py       ← single source of truth for the org structure
│  ├─ models.py     RawMaterial (stock vs reorder policy)
│  ├─ services.py   EBQ formula
│  └─ api.py        JSON endpoints under /api/
├─ accounts/        custom User (Super Admin / Admin), login audit trail
├─ dashboard/       LEGACY server-rendered UI (see note below)
├─ frontend/        React SPA — the portal users actually see
│  └─ src/screens/  Landing, Login, Departments, Purchase, RMRequirement, EBQ
└─ templates/       LEGACY Django templates
```

**Why a proxy, not CORS:** the Vite dev server proxies `/api` to Django, so the
browser only ever sees one origin. The Django session cookie stays a plain
same-origin cookie — no CORS setup, no `SameSite=None`, no third-party-cookie
blocking to fight. Auth is sessions rather than JWT for the same reason: the
cookie stays `HttpOnly`, so there's no token sitting in `localStorage` for a
stray script to lift.

## Getting started

Two servers in development. **Both must be running.**

Terminal 1 — Django API on :8000

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_users          # demo logins (below)
python manage.py seed_raw_materials  # starter Purchase data
python manage.py runserver 127.0.0.1:8000
```

Terminal 2 — React front end on :5173

```bash
cd frontend
npm install
npm run dev
```

Then open **http://127.0.0.1:5173/** — that's the portal. (Hitting :8000
directly gets you the legacy server-rendered UI, not this.)

## Demo credentials

Seeded by `python manage.py seed_users` — change these before going live.

| Role        | Username     | Password         | Department |
|-------------|--------------|------------------|------------|
| Super Admin | `superadmin` | `JCPL@Super2026` | Management |
| Admin       | `admin`      | `JCPL@Admin2026` | Operations |

## API

All endpoints require an authenticated session except the three auth ones.

| Method | Endpoint                        | Purpose |
|--------|---------------------------------|---------|
| GET    | `/api/auth/csrf/`               | Seed the CSRF cookie (called once on app boot) |
| POST   | `/api/auth/login/`              | Sign in — `{username, password}` |
| POST   | `/api/auth/logout/`             | Sign out |
| GET    | `/api/auth/me/`                 | Current user; 403 when signed out |
| GET    | `/api/departments/`             | The 21 departments |
| GET    | `/api/purchase/portals/`        | Purchase work-portal tiles |
| GET    | `/api/purchase/raw-materials/`  | RM rows incl. derived `to_purchase` / `status` |
| POST   | `/api/purchase/ebq/`            | EBQ — `{annual_demand, ordering_cost, holding_cost}` |

### Business rules (server-side, single source of truth)

- **RM Requirement** — if `on_hand <= reorder_level`, buy `reorder_qty`;
  otherwise buy nothing. Derived in `RawMaterial.to_purchase`, never stored, so
  it can't drift from the stock figures.
- **EBQ** — `sqrt(2·D·S/H)`, with orders/year and the combined annual
  order+holding cost. All three inputs must be positive (`H = 0` would divide
  by zero and imply an infinite optimal order).

## Building for production

```bash
cd frontend && npm run build      # emits frontend/dist/
```

Serve `frontend/dist/` as static files from Django (or any web server) with
`/api/` routed to Django. In production, replace the dev-only cache-busting
`?v={% now 'U' %}` on the legacy templates' stylesheet with
`ManifestStaticFilesStorage`, and set `DEBUG = False` plus a real
`SECRET_KEY` and `ALLOWED_HOSTS`.

## Known state / next steps

- **Roles are not yet enforced in the React portal.** Every signed-in user sees
  all 21 department tiles. Per-user department scoping exists in the backend
  (`User.department`, and `dashboard.data.get_accessible_modules` for the legacy
  UI) but is deliberately not applied here yet — the prototype had no
  admin/Super-Admin concept, so that was left for the next pass.
- **Team Accounts and Login Activity are still server-rendered** Django pages at
  `/accounts/team/` and `/accounts/activity/` (Super Admin only). They have not
  been ported into React yet, which is why the `dashboard` app and
  `templates/` still exist.
- `dashboard/data.py` holds a stale 7-department list used *only* by those
  legacy pages' sidebar. `portal/data.py` is authoritative. Once the admin
  screens move into React, the `dashboard` app, `templates/`, and
  `static/css/style.css` can all be deleted.
- When live Purchase Orders / Supplier Master data arrives, filter querysets by
  department too — right now only the module *shell* would be gated, not
  individual records.
