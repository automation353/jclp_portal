import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

// Combined tab embed — available as its own sidebar entry so users still
// have raw-sheet access without leaving the portal.
const SHEET_ID = '1euJuqvIv7wHvwPejgCMOztJNGwU0eyTvPUioYLZZ4fg'
const COMBINED_GID = '1942899352'
const SHEET_EMBED_URL =
  `https://docs.google.com/spreadsheets/d/${SHEET_ID}/preview?gid=${COMBINED_GID}&single=true`
const SHEET_OPEN_URL =
  `https://docs.google.com/spreadsheets/d/${SHEET_ID}/edit?usp=sharing&gid=${COMBINED_GID}#gid=${COMBINED_GID}`


// ── Plain-English mode ───────────────────────────────────────────────────────
// Two audiences read these boards. A CA or an auditor needs the technical
// wording — the exact sheet column and the exact test — so a number can be
// traced. A stakeholder or business partner needs to know what the number
// MEANS. Rather than pick one and lose the other, every tile ships both: the
// backend sends `label`/`sub` (technical) and `plain_label`/`plain_sub`
// (plain English) side by side, and this switch decides which is shown.
//
// Plain is the DEFAULT, because the board is read far more often than it is
// audited. The choice is remembered per browser.
//
// Nothing here changes a value, a count, a row list or an order — only the
// words around them.

const PLAIN_PREF_KEY = 'jcpl.purchaseDash.plainLanguage'
const PlainCtx = createContext(true)
const usePlain = () => useContext(PlainCtx)

// Board wording that lives in the frontend (names, subtitles, menu entries).
// Tile wording comes from the backend — see jcpl/portal/plain_language.py.
function pickName(meta, plain) {
  return (plain && meta.plainName) || meta.name
}
function pickShort(meta, plain) {
  return (plain && meta.plainShort) || meta.short
}
function pickSubtitle(meta, plain) {
  return (plain && meta.plainSubtitle) || meta.subtitle
}
// GROUPS is declared further down the module; this is only ever called during
// render, so the reference resolves fine.
function groupPlainLabel(key) {
  return GROUPS.find((g) => g.key === key)?.plainLabel ?? `Group ${key}`
}


// ── Shared cell / value formatters ───────────────────────────────────────────

function formatCell(v) {
  if (v == null) return <span className="muted">—</span>
  if (typeof v === 'number') {
    return Number.isInteger(v)
      ? v.toLocaleString('en-IN')
      : v.toLocaleString('en-IN', { maximumFractionDigits: 2 })
  }
  return String(v)
}

function formatRupees(n) {
  if (n == null) return <span className="muted">—</span>
  const val = Number(n)
  if (val >= 1e7) return `₹${(val / 1e7).toFixed(2)} Cr`
  if (val >= 1e5) return `₹${(val / 1e5).toFixed(2)} L`
  return `₹${val.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

function StatusPill({ status }) {
  const cls =
    status === 'STOCK-OUT' ? 'dash-pill-stockout' :
    status === 'CRITICAL'  ? 'dash-pill-critical' :
    'dash-pill-watch'
  return <span className={`dash-pill ${cls}`}>{status}</span>
}

// The Seven Controls speak in verdicts, not the three Group-A statuses —
// a wider vocabulary gets its own pill mapping rather than overloading the
// one above with meanings it wasn't named for.
function VerdictPill({ status }) {
  const s = String(status || '')
  const cls =
    /STOP|UNRESOLVABLE|ALREADY OUT|CRITICAL/.test(s) ? 'dash-pill-stockout' :
    /CHALLENGE|SEVERELY EXPOSED|WILL RUN SHORT|PLACEHOLDER|DUPLICATE|UNCONFIRMED/.test(s) ? 'dash-pill-critical' :
    /CLEAR|COVERED|CONFIRMED|VALID|GENUINE RUN-DOWN/.test(s) ? 'dash-pill-ok' :
    'dash-pill-neutral'
  return <span className={`dash-pill ${cls}`}>{s}</span>
}


// ── Presentational pieces ────────────────────────────────────────────────────

// A tile is a button when it has rows behind it, and inert when it's a pure
// aggregate (a ratio, a two-sided comparison). Only drillable tiles get the
// "▸ N rows" affordance, the pointer cursor and keyboard focus.
function Tile({ tile, tileKey, active, onSelect }) {
  const plain = usePlain()
  const kind = tile.kind || 'info'
  const drillable = !!tile.drillable
  const cls = [
    'dash-tile', `dash-tile-${kind}`,
    drillable ? 'is-drillable' : '',
    active ? 'is-active' : '',
  ].filter(Boolean).join(' ')

  const body = (
    <>
      <div className="dash-tile-label">
        {(plain && tile.plain_label) || tile.label}
      </div>
      <div className="dash-tile-value">{tile.value}</div>
      {(plain ? (tile.plain_sub || tile.sub) : tile.sub) && (
        <div className="dash-tile-sub">
          {plain ? (tile.plain_sub || tile.sub) : tile.sub}
        </div>
      )}
      {tile.explain && <div className="dash-tile-explain">{tile.explain}</div>}
      {tile.indicative && (
        <div className="dash-tile-indicative">
          {plain
            ? 'Price is our own estimate, not a supplier bill'
            : 'Rate: indicative — manual estimate'}
        </div>
      )}
      {drillable && (
        <div className="dash-tile-drill">
          {active ? '▾ showing below' : `▸ ${(tile.row_count ?? 0).toLocaleString('en-IN')} rows`}
        </div>
      )}
    </>
  )

  if (!drillable) return <div className={cls}>{body}</div>

  return (
    <button
      type="button"
      className={cls}
      onClick={() => onSelect(tileKey)}
      aria-pressed={active}
      title={`Show the ${tile.row_count ?? 0} rows behind this number`}
    >
      {body}
    </button>
  )
}


// ── Per-column filtering for drill-through tables ────────────────────────────
// A funnel button sits beside every column name (as in Google Sheets). It
// opens a panel with a search box and a tick-list of that column's distinct
// values. Filters from different columns combine with AND, the row count in
// the header reflects what's filtered, and the CSV export always matches
// what's on screen.
//
// The panel is positioned with fixed coordinates taken from its button,
// because the table sits inside an overflow:auto scroller that would clip an
// absolutely-positioned dropdown.

const BLANK = '(blank)'

function cellText(v) {
  if (v == null || v === '') return BLANK
  return String(v)
}

function rowPasses(row, columns, filters) {
  for (const c of columns) {
    const f = filters[c.key]
    if (!f) continue
    const text = cellText(row[c.key])
    if (f.q && f.q.trim() && !text.toLowerCase().includes(f.q.trim().toLowerCase())) return false
    if (f.picked && !f.picked.has(text)) return false
  }
  return true
}

function FilterPanel({ col, options, filter, onApply, onClose, anchor }) {
  const [q, setQ] = useState('')
  const picked = filter?.picked ?? null
  const needle = q.trim().toLowerCase()
  const shown = needle ? options.filter((o) => o.toLowerCase().includes(needle)) : options
  const CAP = 300
  const capped = shown.slice(0, CAP)

  function toggle(val) {
    const next = new Set(picked ?? options)
    if (next.has(val)) next.delete(val)
    else next.add(val)
    onApply({ ...filter, picked: next.size === options.length ? null : next })
  }

  return (
    <>
      <div className="dash-filter-backdrop" onClick={onClose} aria-hidden="true" />
      <div
        className="dash-filter-panel"
        style={{ left: anchor?.left ?? 0, top: anchor?.top ?? 0 }}
        role="dialog"
        aria-label={`Filter ${col.label}`}
      >
        <div className="dash-filter-title">{col.label}</div>
        <input
          className="dash-filter-search"
          type="text"
          placeholder="Search values…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          autoFocus
        />
        <div className="dash-filter-bulk">
          <button type="button" onClick={() => onApply({ ...filter, picked: null })}>Select all</button>
          <button type="button" onClick={() => onApply({ ...filter, picked: new Set() })}>Clear</button>
          {needle && (
            <button
              type="button"
              onClick={() => onApply({ ...filter, picked: new Set(shown) })}
            >Only matches</button>
          )}
        </div>
        <div className="dash-filter-list">
          {capped.length === 0 && <div className="dash-filter-none">No matching values</div>}
          {capped.map((o) => (
            <label key={o} className="dash-filter-opt">
              <input
                type="checkbox"
                checked={picked ? picked.has(o) : true}
                onChange={() => toggle(o)}
              />
              <span className={o === BLANK ? 'muted' : ''}>{o}</span>
            </label>
          ))}
          {shown.length > CAP && (
            <div className="dash-filter-none">
              +{(shown.length - CAP).toLocaleString('en-IN')} more — narrow with search
            </div>
          )}
        </div>
        <div className="dash-filter-foot">
          <button type="button" className="dash-filter-done" onClick={onClose}>Done</button>
        </div>
      </div>
    </>
  )
}


function TileTable({ state, onClear }) {
  // Hooks must run before any early return, so they sit above the
  // loading/error/empty branches below.
  const plain = usePlain()
  const [filters, setFilters] = useState({})
  const [openKey, setOpenKey] = useState(null)
  const [anchor, setAnchor] = useState(null)

  const data = state.data
  const label = (plain && data?.plain_label) || data?.label
  const rawColumns = data?.columns ?? []
  const rawRows = data?.rows ?? []

  // Swapping the heading on the column spec itself means the header, the
  // filter panel title and the CSV export all follow automatically — there is
  // no second place that has to know about plain mode.
  const columns = useMemo(
    () => (plain
      ? rawColumns.map((c) => ({ ...c, label: c.plain_label || c.label }))
      : rawColumns),
    [rawColumns, plain],
  )

  // Verdict pills are translated in the ROW DATA, not at render time, so the
  // filter tick-lists and the CSV show exactly the words on screen.
  const verdictPlain = data?.verdict_plain
  const pillKeys = useMemo(
    () => rawColumns.filter((c) => c.pill).map((c) => c.key),
    [rawColumns],
  )
  const rows = useMemo(() => {
    if (!plain || !verdictPlain || pillKeys.length === 0) return rawRows
    return rawRows.map((r) => {
      const next = { ...r }
      for (const k of pillKeys) {
        const v = r[k]
        if (v != null && verdictPlain[String(v)]) next[k] = verdictPlain[String(v)]
      }
      return next
    })
  }, [rawRows, plain, verdictPlain, pillKeys])

  // Switching tile (or board) clears any filters left over from the last one.
  useEffect(() => {
    setFilters({})
    setOpenKey(null)
  }, [data?.tile_key, data?.dashboard_key, data?.control_key])

  const distinct = useMemo(() => {
    const out = {}
    for (const c of columns) {
      const seen = new Set()
      for (const r of rows) seen.add(cellText(r[c.key]))
      out[c.key] = Array.from(seen).sort((a, b) => {
        if (a === BLANK) return 1
        if (b === BLANK) return -1
        const na = Number(a), nb = Number(b)
        if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb
        return a.localeCompare(b)
      })
    }
    return out
  }, [columns, rows])

  const shownRows = useMemo(
    () => rows.filter((r) => rowPasses(r, columns, filters)),
    [rows, columns, filters],
  )

  const activeCount = Object.values(filters).filter(
    (f) => f && (f.picked || (f.q && f.q.trim())),
  ).length

  if (state.loading) {
    return (
      <div className="dash-drill">
        <div className="dash-drill-head">
          <span className="spinner" /> Loading rows…
        </div>
      </div>
    )
  }
  if (state.error) {
    return (
      <div className="dash-drill">
        <div className="dash-drill-head">Could not load rows</div>
        <p className="note" style={{ margin: 0 }}>{state.error}</p>
      </div>
    )
  }
  if (!data) {
    return (
      <div className="dash-drill dash-drill-empty">
        <p className="note" style={{ margin: 0 }}>
          Click any card above to see the rows behind its number.
        </p>
      </div>
    )
  }

  const { row_count, truncated } = data

  if (!rows.length) {
    return (
      <div className="dash-drill">
        <div className="dash-drill-head">
          {label} <span className="muted">· 0 rows</span>
          <button type="button" className="dash-drill-clear" onClick={onClear}>× clear</button>
        </div>
        <p className="note" style={{ margin: 0 }}>
          {plain
            ? 'Nothing on this list right now — which is itself the answer.'
            : 'Nothing in this list on the current snapshot — which is the finding.'}
        </p>
      </div>
    )
  }

  function openFilter(e, key) {
    if (openKey === key) { setOpenKey(null); return }
    const r = e.currentTarget.getBoundingClientRect()
    // Keep the panel on screen when the column is near the right edge.
    const left = Math.min(r.left, window.innerWidth - 272)
    setAnchor({ left: Math.max(8, left), top: r.bottom + 4 })
    setOpenKey(key)
  }

  const openCol = columns.find((c) => c.key === openKey)

  return (
    <div className="dash-drill">
      <div className="dash-drill-head">
        {label}{' '}
        <span className="muted">
          · {activeCount > 0
              ? `${shownRows.length.toLocaleString('en-IN')} of ${rows.length.toLocaleString('en-IN')} shown — ${activeCount} filter${activeCount > 1 ? 's' : ''} on`
              : truncated
                ? `showing ${rows.length.toLocaleString('en-IN')} of ${row_count.toLocaleString('en-IN')} rows`
                : `${row_count.toLocaleString('en-IN')} rows`}
        </span>
        <span className="dash-drill-actions">
          {activeCount > 0 && (
            <button
              type="button"
              className="dash-drill-clear"
              onClick={() => { setFilters({}); setOpenKey(null) }}
            >⌫ clear filters</button>
          )}
          <button
            type="button"
            className="dash-drill-clear"
            onClick={() => downloadCsv(label, columns, shownRows)}
          >↓ CSV</button>
          <button type="button" className="dash-drill-clear" onClick={onClear}>× clear</button>
        </span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>{columns.map((c) => {
              const f = filters[c.key]
              const on = !!(f && (f.picked || (f.q && f.q.trim())))
              return (
                <th key={c.key} className={c.numeric ? 'num' : ''}>
                  <span className="dash-th">
                    <span className="dash-th-label">{c.label}</span>
                    <button
                      type="button"
                      className={`dash-th-filter ${on ? 'on' : ''} ${openKey === c.key ? 'open' : ''}`}
                      onClick={(e) => openFilter(e, c.key)}
                      title={on ? `Filtered by ${c.label} — click to change` : `Filter by ${c.label}`}
                      aria-label={`Filter by ${c.label}`}
                    >
                      <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
                        <path d="M1 2h10L7 6.5V11L5 9.5V6.5z" fill="currentColor" />
                      </svg>
                    </button>
                  </span>
                </th>
              )
            })}</tr>
          </thead>
          <tbody>
            {shownRows.map((r, i) => (
              <tr key={i}>
                {columns.map((c) => (
                  <td key={c.key} className={c.numeric ? 'num' : ''}>
                    {c.pill === 'verdict' ? <VerdictPill status={r[c.key]} />
                     : c.pill   ? <StatusPill status={r[c.key]} />
                     : c.rupees ? formatRupees(r[c.key])
                     : formatCell(r[c.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          {data?.subtotals && shownRows.length > 1 && (
            <tfoot>
              <tr className="subtotal-row">
                {columns.map((c, ci) => (
                  <td key={c.key} className={c.numeric ? 'num' : ''}>
                    {ci === 0
                      ? 'TOTAL'
                      : data.subtotals[c.key] != null
                        ? (c.rupees ? formatRupees(data.subtotals[c.key]) : formatCell(data.subtotals[c.key]))
                        : ''}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
        {shownRows.length === 0 && (
          <p className="note dash-filter-empty">
            No rows match the current filters.{' '}
            <button type="button" className="linklike" onClick={() => setFilters({})}>
              Clear filters
            </button>
          </p>
        )}
      </div>
      {openCol && (
        <FilterPanel
          col={openCol}
          options={distinct[openCol.key] ?? []}
          filter={filters[openCol.key]}
          anchor={anchor}
          onApply={(next) => setFilters((prev) => ({ ...prev, [openCol.key]: next }))}
          onClose={() => setOpenKey(null)}
        />
      )}
    </div>
  )
}


function downloadCsv(label, columns, rows) {
  const esc = (v) => {
    if (v == null) return ''
    const s = String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [
    columns.map((c) => esc(c.label)).join(','),
    ...rows.map((r) => columns.map((c) => esc(r[c.key])).join(',')),
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${label.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}


// ── Dashboard registry ───────────────────────────────────────────────────────
// One entry per board. `drill` describes the drill-through table so both the
// sidebar and the detail pane are driven by a single source of truth.
//
// `name` / `short` / `subtitle` are the technical wording. `plainName` /
// `plainShort` / `plainSubtitle` are what a stakeholder or business partner
// reads — same board, no jargon. The Simple/Detailed switch picks between
// them; neither affects any number.

const DASHBOARDS = [
  {
    key: 'd8', group: 'C', num: 8,
    name: 'Data Trust & Integrity',
    short: 'Data Trust',
    plainName: 'Can We Trust This Sheet?',
    plainShort: 'Can We Trust It?',
    icon: '🛡',
    audience: 'MD · Audit',
    subtitle: 'A standing measurement of how much of the RM sheet can be relied on, expressed as counts of specific, nameable defects. Every other board rests on this one.',
    plainSubtitle: 'A plain count of what is missing or broken in the source sheet. Every other board in this portal rests on this one, so a weak score here weakens everything else.',
    headline: (t) => t?.trust_score?.value,  },
  {
    key: 'd9', group: 'C', num: 9,
    name: 'Signal Conflict',
    short: 'Signal Conflict',
    plainName: 'Where The Sheet Contradicts Itself',
    plainShort: 'Contradictions',
    icon: '⚔',
    audience: 'MD · Audit · Buyer',
    subtitle: 'Every place where two live columns give contradictory instructions about the same item. Both values are shown side by side — nothing is resolved here on purpose.',
    plainSubtitle: 'Every place where two columns give opposite instructions about the same material. Both are shown side by side and nothing is decided here on purpose — somebody has to choose which one is right.',
    headline: (t) => t?.two_order_qty_disagree?.value,  },
  {
    key: 'd1', group: 'A', num: 1,
    name: 'Procurement Action Board',
    short: 'Procurement Action',
    plainName: 'What To Buy Today',
    plainShort: 'What To Buy Today',
    icon: '📋',
    audience: 'Buyer',
    subtitle: 'Which raw-material lines must the buyer act on before this shift ends, and what is the rupee consequence of not acting. Rupee tiles carry the rate-indicative caveat until Decision 5 is closed.',
    plainSubtitle: 'The materials the buyer has to act on before today ends, and what it costs the company if nobody acts. Money figures use our own manual price estimate, not a supplier bill.',
    headline: (t) => t?.items_needing_order?.value,  },
  {
    key: 'd2', group: 'A', num: 2,
    name: 'Stock-Out & Cover Risk',
    short: 'Stock-Out Risk',
    plainName: 'Will We Run Out?',
    plainShort: 'Will We Run Out?',
    icon: '⏳',
    audience: 'Buyer · Plant Head',
    subtitle: 'Lines whose days-of-cover is shorter than supplier lead time will run out before replenishment lands — even a same-day PO cannot save these. The measurable-lines tile is the honest denominator.',
    plainSubtitle: 'Materials that will finish before a fresh delivery can reach us. For these, even ordering today does not stop production from stopping — so they need a different answer, not a faster purchase order.',
    headline: (t) => t?.cover_short?.value,  },
  {
    key: 'd3', group: 'A', num: 3,
    name: 'Reorder Level (RAG)',
    short: 'Reorder RAG',
    plainName: 'Stock Level Traffic Light',
    plainShort: 'Traffic Light',
    icon: '🚦',
    audience: 'Buyer · Operations',
    subtitle: "Current stock against JCPL's own Red / Yellow / Green / Blue levels. Recomputed fresh — the sheet's own RL/YL/GL/BL counters are shown alongside so any divergence is visible rather than resolved.",
    plainSubtitle: "Every material's stock measured against the minimum, warning and healthy levels we set for ourselves. Where the sheet's own count differs from ours, both are shown rather than quietly corrected.",
    headline: (t) => t?.red?.value,  },
  {
    key: 'd4', group: 'B', num: 4,
    name: 'Inventory On Hand & Valuation',
    short: 'Valuation',
    plainName: 'What Our Stock Is Worth',
    plainShort: 'What Stock Is Worth',
    icon: '💵',
    audience: 'CFO · Plant Head',
    subtitle: 'A single defensible inventory figure, cut by material group. Every rupee here is Rate: indicative (Decision 5) — the manual estimate is not a purchase-register rate.',
    plainSubtitle: 'One value for everything lying in the store, split by material group. Every rupee uses a manual price estimate, so treat it as a good working figure rather than an audited one.',
    headline: (t) => t?.total_value?.value,  },
  {
    key: 'd5', group: 'B', num: 5,
    name: 'Slow & Non-Moving Stock',
    short: 'Slow / Non-Moving',
    plainName: "Stock That Isn't Moving",
    plainShort: 'Not Moving',
    icon: '🧊',
    audience: 'CFO · MD',
    subtitle: 'The share of the item master that has stopped being an asset. Whether that reflects genuine dead stock or a stale classification is itself the finding (Decision 6). Per-line ageing needs a HISTORY tab and is not available yet.',
    plainSubtitle: 'How much of the store has stopped earning. Whether that is genuinely dead material or just an out-of-date classification is itself the question this board raises.',
    headline: (t) => t?.dead_holding_stock?.value,  },
  {
    key: 'd6', group: 'B', num: 6,
    name: 'Buffer Capital',
    short: 'Buffer Capital',
    plainName: 'Cash Held As Safety Stock',
    plainShort: 'Safety Stock Cash',
    icon: '🏦',
    audience: 'CFO',
    subtitle: "How much cash JCPL's own safety-stock policy commits before a single purchase order is raised. The 500 kg threshold on Green Level (Decision 7) is why some MTS lines carry no buffer at all.",
    plainSubtitle: "How much cash our own rule of always keeping a minimum quantity in the store ties up, before a single purchase order is raised.",
    headline: (t) => t?.buffer_committed?.value,  },
  {
    key: 'd7', group: 'B', num: 7,
    name: 'Inventory Coverage Ageing',
    short: 'Coverage Ageing',
    plainName: 'How Long Our Stock Will Last',
    plainShort: 'Days Of Stock',
    icon: '📆',
    audience: 'Operations · CFO',
    subtitle: 'The "0 to 15" band is deliberately split into "genuinely short" and "not measurable" so the board cannot be read wrongly. Zero-consumption lines land in the tightest band by arithmetic, not by shortage.',
    plainSubtitle: 'Materials grouped by how many days of stock they have left. The lowest group is deliberately split into genuinely short and cannot-be-judged, so the board cannot be read the wrong way round.',
    headline: (t) => t?.genuinely_short?.value,  },
]

// The card each board opens on, so you always land on its most actionable
// list rather than an empty table.
const PRIMARY_TILE = {
  d8: 'silent_zero',
  d9: 'two_order_qty_disagree',
  d1: 'items_needing_order',
  d2: 'cover_short',
  d3: 'red',
  d4: 'group_breakdown',
  d5: 'dead_holding_stock',
  d6: 'mts_no_buffer',
  d7: 'not_measurable',
}

// Display order is A → B → C → D → E. (The brief's *build* order put C first
// because everything rests on it; that stays true and is noted on the group,
// but the menu reads in the natural group order.)
const GROUPS = [
  { key: 'A', label: 'Group A — Act today',
    note: 'Buyer · Operations · hourly',
    plainLabel: 'Act Today',
    plainNote: 'For the buyer and operations · refreshed every hour' },
  { key: 'B', label: 'Group B — Capital locked in inventory',
    note: 'CFO · Plant Head · daily / weekly',
    plainLabel: 'Money Tied Up In Stock',
    plainNote: 'For finance and the plant head · daily to weekly' },
  { key: 'C', label: 'Group C — Can we trust this sheet',
    note: 'MD · Audit · built first, everything rests on it',
    plainLabel: 'Can We Trust The Data?',
    plainNote: 'For the MD and audit · everything else rests on these two' },
  { key: 'D', label: 'Group D — Source & awaiting data',
    note: 'Raw sheet · Tally-blocked board',
    plainLabel: 'Source Data',
    plainNote: 'The raw sheet, and one board still waiting on data' },
  { key: 'E', label: 'Group E — The Seven Purchase Controls',
    note: 'Rajeev Joshi spec · verdicts, not tiles · 3, 4, 6, 7 buildable today',
    plainLabel: 'The Seven Purchase Checks',
    plainNote: 'Each one answers a single yes-or-no question before we buy' },
]

// ── Control registry (The Seven Purchase Controls) ──────────────────────────
// A separate, additive registry from DASHBOARDS above — same shape, its own
// backend app and endpoints (purchase_controls), so nothing here touches the
// nine dashboards' data or behaviour. All seven are live; 1, 2 and 5 joined
// once the PO register was wired in.
//
// `jcplWording` is the specification's own phrasing and quotes sheet columns
// by letter, so it shows in the Detailed view only — the Simple view gets
// `plainSubtitle` instead.
const CONTROLS = [
  {
    key: 'c1', group: 'E', num: 1,
    name: 'Is it already on order?',
    short: 'Already on order?',
    plainName: 'Have We Already Ordered It?',
    plainShort: "Already ordered?",
    icon: '\u{1F4E6}',
    audience: 'Buyer',
    jcplWording: 'Column X says we need this item. Now look at the open PO list. Is this same item already ordered and not yet delivered?',
    subtitle: 'Nets each requirement against what is already open with the supplier. Coverage counts LIVE pending only \u2014 an overdue PO is a chase item, not protection \u2014 and pending quantity is split pro-rata where one item code sits on several requirement lines.',
    plainSubtitle: "Before raising a new order, this checks what is already open with the supplier. Only orders still expected on time count as cover — one the supplier has already missed is something to chase, not protection.",
    headline: (t) => t?.not_on_order?.value,
  },
  {
    key: 'c2', group: 'E', num: 2,
    name: 'Did anyone actually order it?',
    short: 'Did anyone order it?',
    plainName: 'Did Anyone Actually Order It?',
    plainShort: "Did anyone order it?",
    icon: '\u{23F1}',
    audience: 'Buyer \u00b7 Plant Head',
    jcplWording: 'Column X says we need this item. Now check: is there a PO? Is there a delivery date in column Z?',
    subtitle: 'The mirror of Control 1 \u2014 Control 1 stops JCPL buying twice, this one stops a stoppage. It puts a clock on every unactioned requirement using a first-seen register that never resets, because a three-day-old requirement is a queue and a thirty-day-old one is a failure.',
    plainSubtitle: "The other half of the check above. That one stops us buying twice; this one stops production stopping. It puts a clock on every material still waiting to be ordered, because three days of waiting is a queue and thirty days is a failure.",
    headline: (t) => t?.not_ordered?.value,
  },
  {
    key: 'c3', group: 'E', num: 3,
    name: 'Are we buying what we’re drowning in?',
    short: 'Dead-stock challenge',
    plainName: 'Are We Buying What We Already Have Too Much Of?',
    plainShort: "Already overstocked?",
    icon: '⛔',
    audience: 'Buyer · CFO',
    jcplWording: 'Column X says order more. But column V says HIGH INVENTORY, or the item is marked Slow / Non Moving.',
    subtitle: 'Buildable now, in full, from the RM sheet alone. Every requirement line already flagged Non/Slow Moving or over-stocked must carry a recorded reason before it’s raised — the control challenges, it doesn’t silently block.',
    plainSubtitle: "Every material on the buy list that is already sitting in the store in quantity, or simply not selling. The check asks for a reason to be written down before the order goes out — it does not block the order.",
    headline: (t) => t?.flagged_union?.value,
  },
  {
    key: 'c4', group: 'E', num: 4,
    name: 'Will we run out before delivery?',
    short: 'Cover vs. lead time',
    plainName: 'Will It Arrive Before We Run Out?',
    plainShort: "Arrive in time?",
    icon: '⏳',
    audience: 'Buyer · Plant Head',
    jcplWording: 'Compare days of stock left (column U) against the supplier’s lead time (column I). Is the stock going to finish first?',
    subtitle: 'Buildable now from RM; sharper once the TCS iON PO feed lands. A shortage that ordering can still fix is a different problem from one arithmetic has already decided — this separates them, and flags the ones nobody has even raised a PO for yet.',
    plainSubtitle: "A shortage that ordering can still fix is a different problem from one the calendar has already decided. This separates the two, and points out the materials nobody has even asked to be ordered yet.",
    headline: (t) => t?.cover_short?.value,
  },
  {
    key: 'c5', group: 'E', num: 5,
    name: 'Advance paid \u2014 did material arrive?',
    short: 'Advance recovery',
    plainName: 'We Paid In Advance — Did The Material Come?',
    plainShort: "Advance paid?",
    icon: '\u{1F4B8}',
    audience: 'CFO \u00b7 Accounts',
    jcplWording: 'Look at money paid to a vendor in advance. Has the lead time passed? Has any material been received against it?',
    subtitle: 'PARTIAL by design. Advance payment TERMS are identifiable from the PO register, so exposure can be sized and aged per vendor \u2014 but no vendor ledger exists, so actual payment cannot be confirmed. Every figure is exposure at risk, never confirmed unrecovered cash.',
    plainSubtitle: "Partly answerable today. We can see which orders required paying the supplier up front, so the risk can be sized and aged — but with no accounts ledger connected we cannot confirm the money actually left. Everything here is money at risk, never confirmed loss.",
    headline: (t) => t?.exposure_at_risk?.value,
  },
  {
    key: 'c6', group: 'E', num: 6,
    name: 'Is this a real item in our books?',
    short: 'Item-code validity',
    plainName: 'Is This A Real Item In Our Books?',
    plainShort: "Real item code?",
    icon: '🔑',
    audience: 'MD · Master data owner',
    jcplWording: 'Take the item code on the row. Does it actually exist in the Tally item master?',
    subtitle: 'The foundation the other six controls stand on. Half is buildable today — absent, zero, placeholder and duplicated codes — the other half (existence, active flag, UOM/group match) needs the TCS iON item master and reports NOT YET CHECKABLE, never a silent pass.',
    plainSubtitle: "The foundation the other six checks stand on. Missing, blank and duplicated codes can be caught today. Whether a code truly exists in the books needs the official item list, and until that arrives it is reported as unknown rather than quietly passed.",
    headline: (t) => t?.join_readiness?.value,
  },
  {
    key: 'c7', group: 'E', num: 7,
    name: 'Is that zero a real zero, or a failed search?',
    short: 'Real zero vs. failed lookup',
    plainName: 'Is That Zero Real, Or Did The Search Fail?',
    plainShort: "Real zero?",
    icon: '❓',
    audience: 'MD · Audit',
    jcplWording: 'When the sheet shows 0 stock, ask: is stock genuinely nil, or did the lookup simply not find the code?',
    subtitle: 'The control that decides whether any of the other six can be believed. Every quad-zero row stays UNCONFIRMED until the TCS iON stock summary feed exists — reporting one as a verified real zero today would be exactly the failure this control exists to catch.',
    plainSubtitle: "The check that decides whether the other six can be believed. A row showing zero everywhere stays unconfirmed until a real stock report proves it, because calling it a genuine zero today is exactly the mistake this check exists to catch.",
    headline: (t) => t?.quad_zero?.value,
  },
]

const CONTROL_PRIMARY_TILE = {
  c1: 'not_on_order',
  c2: 'not_ordered',
  c3: 'flagged_union',
  c4: 'cover_short',
  c5: 'exposure_at_risk',
  c6: 'join_readiness',
  c7: 'quad_zero',
}

// Group D's entries aren't computed boards — the raw sheet embed and the
// spec-only Dashboard 10. Shaped like the others so the menu is uniform.
const EXTRA_VIEWS = [
  { key: 'SHEET', group: 'D', icon: '📄', short: 'Combined sheet',
    plainShort: 'The source sheet',
    name: 'Combined sheet — raw view',
    plainName: 'The Sheet Everything Comes From',
    audience: 'Source data' },
  { key: 'D10', group: 'D', icon: '🔒', short: 'Advance Payment',
    plainShort: 'Advance Payments',
    name: 'Dashboard 10 — Advance Payment (spec only)',
    plainName: 'Advance Payments (not built yet)',
    audience: 'CFO · Accounts' },
]


// ── Detail panes ─────────────────────────────────────────────────────────────

function DashboardPane({ meta, result, snapshot, activeTile, onSelectTile, tableState, onClear }) {
  const plain = usePlain()
  if (!result) {
    return (
      <div className="dash-card">
        <div className="dash-card-head">
          <h4>{meta.icon} Dashboard {meta.num} — {pickName(meta, plain)}</h4>
          <div className="dash-card-sub">
            No computed result for this board on the current snapshot. Run{' '}
            <code>manage.py compute_purchase_dashboards</code> on the server.
          </div>
        </div>
      </div>
    )
  }
  return (
    <>
      <div className="dash-card">
        <div className="dash-card-head">
          <h4>{meta.icon} Dashboard {meta.num} — {pickName(meta, plain)}</h4>
          <div className="dash-detail-meta">
            <span className="dash-chip">
              {plain ? groupPlainLabel(meta.group) : `Group ${meta.group}`}
            </span>
            <span className="dash-chip">{meta.audience}</span>
            <span className="dash-chip">
              {(snapshot?.row_count ?? '—')} {plain ? 'materials on the sheet' : 'rows in snapshot'}
            </span>
          </div>
          <div className="dash-card-sub">{pickSubtitle(meta, plain)}</div>
        </div>
        <div className="dash-tile-grid">
          {Object.entries(result.tiles).map(([k, t]) => (
            <Tile
              key={k}
              tileKey={k}
              tile={t}
              active={activeTile === k}
              onSelect={onSelectTile}
            />
          ))}
        </div>
      </div>
      <TileTable state={tableState} onClear={onClear} />
    </>
  )
}

function SheetPane() {
  const plain = usePlain()
  return (
    <div className="dash-card">
      <div className="dash-card-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div>
          <h4>📄 {plain ? 'The sheet everything comes from' : 'Combined tab — raw sheet view'}</h4>
          <div className="dash-card-sub">
            {plain
              ? <>A read-only view of the working sheet. Every number on every other board is calculated from this one place.</>
              : <>Read-only mirror of the <b>combined</b> tab. This is the source every tile on the other boards is computed from.</>}
          </div>
        </div>
        <a
          className="btn-upload"
          href={SHEET_OPEN_URL}
          target="_blank"
          rel="noopener noreferrer"
          style={{ background: 'var(--steel)', flexShrink: 0 }}
        >
          ↗ Open in Google Sheets
        </a>
      </div>
      <div className="sheet-embed" style={{ marginTop: 10 }}>
        <iframe src={SHEET_EMBED_URL} title="Combined Purchase sheet" loading="lazy" />
      </div>
    </div>
  )
}

function SpecPane() {
  const plain = usePlain()
  const blocked = plain ? [
    ['Money Paid Up Front, Still Open', 'Everything we have paid suppliers before delivery'],
    ['Paid, And The Delivery Time Has Passed', 'We paid, the agreed time is over, and nothing has arrived'],
    ['Paid With No Order Behind It', 'Money that left with no purchase order to justify it'],
    ['Paid Up Front For Idle Material', 'Cash committed forward for material that is not selling'],
    ['Supplier Owes Us And We Owe Them', 'The same supplier sits on both sides of the books'],
    ['Time To Get The Money Back', 'Paid over 60 days ago with nothing received'],
  ] : [
    ['Advances outstanding', 'Total vendor debit balances'],
    ['Advances aged beyond lead time', 'Advances where lead time has passed with no receipt'],
    ['Advance without a PO', 'Payments made with no purchase order behind them'],
    ['Advance on a non-moving item', 'Cash paid forward for material that is not turning'],
    ['Vendor both owed and advanced', 'Payable + receivable on the same vendor'],
    ['Recovery risk', 'Advances over 60 days with no goods receipt'],
  ]
  return (
    <div className="dash-card">
      <div className="dash-card-head">
        <h4>🔒 Dashboard 10 — Advance Payment &amp; Vendor Exposure</h4>
        <div className="dash-card-sub">
          {plain ? (
            <>
              This board is designed but deliberately not built, because it cannot
              honestly be answered from the stock sheet alone. It needs the
              accounts system to send us what each supplier owes and what we have
              paid them. Showing estimates here would be guesswork dressed as fact.
            </>
          ) : (
            <>
              Specified but deliberately not built — it cannot be computed from the RM
              sheet at any level of effort. Requires the Tally vendor ledger, PO
              outstanding and GRN feeds. See the feed specification in{' '}
              <code>jcpl/docs/DASHBOARD-10-TALLY-FEED-SPEC.docx</code>.
            </>
          )}
        </div>
      </div>
      <div className="dash-tile-grid">
        {blocked.map(([label, sub]) => (
          <div key={label} className="dash-tile dash-tile-blocked">
            <div className="dash-tile-label">{label}</div>
            <div className="dash-tile-value">—</div>
            <div className="dash-tile-sub">{sub}</div>
            <div className="dash-tile-explain">
              {plain
                ? 'Cannot be built until the accounts system is connected.'
                : 'Blocked — requires Tally feed.'}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}


// Mirrors DashboardPane, kept as its own component rather than branching
// inside that one — controls speak in verdicts and carry the mockup's own
// wording, dashboards don't, and neither file should have to know about the
// other's shape.
function ControlPane({ meta, result, snapshot, activeTile, onSelectTile, tableState, onClear }) {
  const plain = usePlain()
  if (!result) {
    return (
      <div className="dash-card">
        <div className="dash-card-head">
          <h4>{meta.icon} Control {meta.num} — {pickName(meta, plain)}</h4>
          <div className="dash-card-sub">
            No computed result for this control on the current snapshot. Run{' '}
            <code>manage.py compute_purchase_controls</code> on the server.
          </div>
        </div>
      </div>
    )
  }
  return (
    <>
      <div className="dash-card">
        <div className="dash-card-head">
          <h4>{meta.icon} Check {meta.num} of 7 — {pickName(meta, plain)}</h4>
          <div className="dash-detail-meta">
            <span className="dash-chip">
              {plain ? groupPlainLabel(meta.group) : `Group ${meta.group}`}
            </span>
            <span className="dash-chip">{meta.audience}</span>
            <span className="dash-chip">
              {(snapshot?.row_count ?? '—')} {plain ? 'materials on the sheet' : 'rows in snapshot'}
            </span>
          </div>
          {/* The specification's own phrasing quotes sheet columns by letter,
              so it belongs to the Detailed view. */}
          {!plain && (
            <div className="dash-card-sub" style={{ fontStyle: 'italic' }}>
              “{meta.jcplWording}”
            </div>
          )}
          <div className="dash-card-sub">{pickSubtitle(meta, plain)}</div>
        </div>
        <div className="dash-tile-grid">
          {Object.entries(result.tiles).map(([k, t]) => (
            <Tile
              key={k}
              tileKey={k}
              tile={t}
              active={activeTile === k}
              onSelect={onSelectTile}
            />
          ))}
        </div>
      </div>
      <TileTable state={tableState} onClear={onClear} />
    </>
  )
}


// ── Main screen ──────────────────────────────────────────────────────────────

const NAV_PREF_KEY = 'jcpl.purchaseDash.navOpen'

export default function PurchaseDashboard() {
  const navigate = useNavigate()
  // Land on the first board of the first group (Group A → Procurement Action).
  const [selected, setSelected] = useState('d1')
  const [summary, setSummary] = useState(null)
  // The Seven Controls' own summary — a separate fetch against a separate
  // endpoint (purchase_controls), so a failure or slow load there can never
  // affect the nine dashboards above.
  const [controlsSummary, setControlsSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // Sidebar open/closed, remembered between visits.
  const [navOpen, setNavOpen] = useState(
    () => localStorage.getItem(NAV_PREF_KEY) !== 'closed'
  )
  // Which card's rows are showing, and the fetched table for it.
  const [activeTile, setActiveTile] = useState(null)
  const [tableState, setTableState] = useState({ loading: false, error: '', data: null })
  // Which group dropdowns are open. Group A starts open; the rest collapse
  // so the menu opens short rather than as one long list.
  const [openGroups, setOpenGroups] = useState(() => new Set(['A']))
  // #5: Detail view dropped — always plain English.
  const plain = true

  function toggleGroup(key) {
    setOpenGroups((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  // Control keys ('c3'…) and dashboard keys ('d1'…) never collide, so the
  // leading letter alone picks the right endpoint.
  const isControlKey = (key) => key?.[0] === 'c'

  async function loadTile(itemKey, tileKey) {
    setActiveTile(tileKey)
    setTableState({ loading: true, error: '', data: null })
    try {
      const data = isControlKey(itemKey)
        ? await api.purchaseControlTileRows(itemKey, tileKey)
        : await api.purchaseDashboardTileRows(itemKey, tileKey)
      setTableState({ loading: false, error: '', data })
    } catch (err) {
      setTableState({ loading: false, error: err.message, data: null })
    }
  }

  function clearTile() {
    setActiveTile(null)
    setTableState({ loading: false, error: '', data: null })
  }

  function toggleNav() {
    setNavOpen((open) => {
      localStorage.setItem(NAV_PREF_KEY, open ? 'closed' : 'open')
      return !open
    })
  }

  // Picking a board swaps the pane behind the drawer and slides the drawer
  // shut, so the dashboard is what you're left looking at.
  function selectBoard(key) {
    setSelected(key)
    setNavOpen(false)
    localStorage.setItem(NAV_PREF_KEY, 'closed')
    // Switching boards resets the table — the next effect auto-opens that
    // board's primary card so you always land on something useful.
    clearTile()
    // Keep the chosen board's group open so reopening the menu shows where
    // you are rather than a collapsed list.
    const grp = DASHBOARDS.find((d) => d.key === key)?.group
      ?? CONTROLS.find((c) => c.key === key)?.group
      ?? EXTRA_VIEWS.find((v) => v.key === key)?.group
    if (grp) setOpenGroups((prev) => new Set(prev).add(grp))
  }

  async function refresh() {
    setLoading(true)
    try {
      const [dashboards, controls] = await Promise.all([
        api.purchaseDashboardsSummary(),
        // Controls are additive — if that endpoint isn't up yet on some
        // deploy, the nine dashboards must still load normally.
        api.purchaseControlsSummary().catch(() => null),
      ])
      setSummary(dashboards)
      setControlsSummary(controls)
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { refresh() }, [])

  const snap = summary?.snapshot
  const resultFor = (key) =>
    summary?.results?.find((r) => r.dashboard_key === key)
    ?? controlsSummary?.results?.find((r) => r.control_key === key)
  const meta = DASHBOARDS.find((d) => d.key === selected) ?? CONTROLS.find((c) => c.key === selected)
  const isControl = CONTROLS.some((c) => c.key === selected)
  const ageMs = snap ? Date.now() - new Date(snap.fetched_at).getTime() : null

  // Auto-open the board's primary card once its tiles are known and nothing
  // is selected yet.
  useEffect(() => {
    if (!meta || activeTile) return
    const res = resultFor(meta.key)
    if (!res) return
    const want = PRIMARY_TILE[meta.key] ?? CONTROL_PRIMARY_TILE[meta.key]
    const key = res.tiles[want]?.drillable
      ? want
      : Object.keys(res.tiles).find((k) => res.tiles[k].drillable)
    if (key) loadTile(meta.key, key)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta?.key, summary, controlsSummary, activeTile])

  return (
    <section className="screen">
      <TopBar subtitle="Purchase › Control Dashboards" />
      <div className="wrap wrap-wide">
        <div className="crumbs">
          <Link to="/departments">Home</Link> › <Link to="/purchase">Purchase</Link> › Dashboards
        </div>
        <button className="backbtn" onClick={() => navigate('/purchase')}>← Back to Purchase</button>

        <div className="panel">
          <div className="page-head">
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, flex: 1, minWidth: 0 }}>
              <button
                type="button"
                className="dash-nav-toggle"
                onClick={toggleNav}
                title={navOpen ? 'Close the board list' : 'Open the board list'}
                aria-expanded={navOpen}
              >
                ☰
              </button>
              <div style={{ minWidth: 0 }}>
                <h3>📊 Purchase Control Dashboards</h3>
                <p className="note" style={{ margin: 0 }}>
                  {meta
                    ? <>Viewing <b>{isControl ? (plain ? 'Check' : 'Control') : 'Dashboard'} {meta.num} — {pickName(meta, plain)}</b>. Use ☰ to switch boards.</>
                    : 'Nine boards and the seven purchase checks, all computed from one sheet. Use ☰ to switch boards.'}
                </p>
              </div>
            </div>
            <div className="dash-head-actions">
              <button
                type="button"
                className="btn-upload"
                onClick={refresh}
                disabled={loading}
                style={{ background: 'var(--steel)' }}
              >
                {loading ? 'Loading…' : '⟳ Refresh'}
              </button>
            </div>
          </div>

          {snap && (
            <div className="dash-meta">
              <span>Last snapshot: <b>{new Date(snap.fetched_at).toLocaleString()}</b></span>
              <span>·</span>
              <span>Rows: <b>{snap.row_count}</b></span>
              {ageMs > 3600_000 && (
                <span className="stale-warn">⚠ &gt; 1 hour old — check the fetch timer</span>
              )}
            </div>
          )}
          {!snap && !loading && !error && (
            <div className="upload-status error" style={{ marginTop: 14 }}>
              No snapshot yet. Run <code>manage.py fetch_combined_sheet</code> on the server
              (or wait for the hourly timer).
            </div>
          )}
          {error && <div className="upload-status error" style={{ marginTop: 14 }}>{error}</div>}

          <PlainCtx.Provider value={plain}>
          <div className="dash-layout">
            {/* Backdrop — click anywhere off the drawer to close it. */}
            {navOpen && (
              <div
                className="dash-nav-backdrop"
                onClick={() => toggleNav()}
                aria-hidden="true"
              />
            )}

            {/* ── slide-over board menu ────────────────────────────────── */}
            <nav
              className={`dash-nav ${navOpen ? 'open' : ''}`}
              aria-label="Dashboards"
              aria-hidden={!navOpen}
            >
              <div className="dash-nav-head">
                <span>Boards</span>
                <button
                  type="button"
                  className="dash-nav-close"
                  onClick={toggleNav}
                  title="Close the board list"
                >×</button>
              </div>
              {GROUPS.map((g) => {
                // Group D holds the raw sheet + spec-only board; A/B/C hold
                // computed dashboards; E holds the Seven Controls. All three
                // shapes render the same way.
                const boards   = DASHBOARDS.filter((d) => d.group === g.key)
                const controls = CONTROLS.filter((c) => c.group === g.key)
                const views    = EXTRA_VIEWS.filter((v) => v.group === g.key)
                const items    = [...boards, ...controls, ...views]
                const isOpen = openGroups.has(g.key)
                const holdsSelected = items.some((i) => i.key === selected)

                return (
                  <div key={g.key} className="dash-nav-group">
                    <button
                      type="button"
                      className={`dash-nav-grouphead ${isOpen ? 'open' : ''} ${holdsSelected ? 'has-current' : ''}`}
                      onClick={() => toggleGroup(g.key)}
                      aria-expanded={isOpen}
                    >
                      <span className="dash-nav-grouptext">
                        <span className="dash-nav-grouplabel">
                          {(plain && g.plainLabel) || g.label}
                        </span>
                        <span className="dash-nav-groupnote">
                          {(plain && g.plainNote) || g.note}
                        </span>
                      </span>
                      <span className="dash-nav-groupcount">{items.length}</span>
                      <span className={`dash-nav-groupchev ${isOpen ? 'open' : ''}`}>›</span>
                    </button>

                    {isOpen && (
                      <div className="dash-nav-items">
                        {items.map((it) => {
                          const res = 'num' in it ? resultFor(it.key) : null
                          const badge = res ? it.headline(res.tiles) : null
                          return (
                            <button
                              key={it.key}
                              type="button"
                              className={`dash-nav-item ${selected === it.key ? 'active' : ''}`}
                              onClick={() => selectBoard(it.key)}
                              aria-current={selected === it.key}
                            >
                              <span className="dash-nav-icon">{it.icon}</span>
                              <span className="dash-nav-text">
                                <span className="dash-nav-name">
                                  {'num' in it
                                    ? `${it.num}. ${pickShort(it, plain)}`
                                    : pickShort(it, plain)}
                                </span>
                                <span className="dash-nav-aud">{it.audience}</span>
                              </span>
                              {badge != null && badge !== '' && (
                                <span className="dash-nav-badge">{badge}</span>
                              )}
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </nav>

            {/* ── right detail ─────────────────────────────────────────── */}
            <div className="dash-detail">
              {loading && !summary && <div className="loading">Loading dashboards…</div>}
              {selected === 'SHEET' && <SheetPane />}
              {selected === 'D10' && <SpecPane />}
              {meta && (isControl ? (
                <ControlPane
                  meta={meta}
                  result={resultFor(meta.key)}
                  snapshot={snap}
                  activeTile={activeTile}
                  onSelectTile={(tileKey) => loadTile(meta.key, tileKey)}
                  tableState={tableState}
                  onClear={clearTile}
                />
              ) : (
                <DashboardPane
                  meta={meta}
                  result={resultFor(meta.key)}
                  snapshot={snap}
                  activeTile={activeTile}
                  onSelectTile={(tileKey) => loadTile(meta.key, tileKey)}
                  tableState={tableState}
                  onClear={clearTile}
                />
              ))}
            </div>
          </div>
          </PlainCtx.Provider>
        </div>
      </div>
    </section>
  )
}
