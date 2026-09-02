import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

/**
 * All tables that can be browsed. Matches the field_maps registry.
 */
const ALL_TABLES = [
  { key: 'item_master',         label: 'Item Master',           ref: 'W1.1' },
  { key: 'family_hierarchy',    label: 'Family Hierarchy',      ref: 'W1.2' },
  { key: 'site_plant_section',  label: 'Site / Plant / Section',ref: 'W1.3' },
  { key: 'route_master',        label: 'Route Master',          ref: 'W1.4' },
  { key: 'operation_stage_map', label: 'Operation Stage Map',   ref: 'W1.5' },
  { key: 'capacity_ppp',        label: 'Capacity / PPP',        ref: 'W1.6' },
  { key: 'machine_master',      label: 'Machine Master',        ref: 'W1.7' },
  { key: 'batch_ebq',           label: 'Batch / EBQ',           ref: 'W1.8' },
  { key: 'lead_time',           label: 'Lead Time',             ref: 'W1.9' },
  { key: 'working_calendar',    label: 'Working Calendar',      ref: 'W1.10' },
  { key: 'bom_master',          label: 'BOM Master',            ref: 'W1.11' },
  { key: 'part_engineering',    label: 'Part Engineering',      ref: 'W1.12' },
  { key: 'customer_part',       label: 'Customer-Part',         ref: 'W1.13' },
  { key: 'stock_policy',        label: 'Stock Policy (Green)',  ref: 'W1.14' },
  { key: 'packing_spec',        label: 'Packing Spec',          ref: 'W1.15' },
  { key: 'rate_asp',            label: 'Rate / ASP',            ref: 'W1.16' },
  { key: 'reason_codes',        label: 'Reason Codes',          ref: 'W1.17' },
  // ERP feeds (L1)
  { key: 'erp_item_master',    label: 'ERP Item Master',       ref: '#1' },
  { key: 'erp_bom',            label: 'ERP BOM',               ref: '#2' },
  { key: 'erp_fg_stock',       label: 'ERP FG Stock',          ref: '#3' },
  { key: 'erp_cp_stock',       label: 'ERP CP Stock',          ref: '#4' },
  { key: 'erp_rm_stock',       label: 'ERP RM Stock',          ref: '#5' },
  { key: 'erp_pm_stock',       label: 'ERP PM Stock',          ref: '#6' },
  { key: 'erp_consumables',    label: 'ERP Consumables',       ref: '#7' },
  { key: 'erp_prod_fg',        label: 'ERP Production FG',     ref: '#8' },
  { key: 'erp_prod_semi',      label: 'ERP Production Semi',   ref: '#9' },
  { key: 'erp_dispatch',       label: 'ERP Dispatch',          ref: '#10' },
  { key: 'erp_forecast',       label: 'ERP Forecast',          ref: '#11' },
  { key: 'erp_sales_orders',   label: 'ERP Sales Orders',      ref: '#12' },
  { key: 'erp_pending_po',     label: 'ERP Pending POs',       ref: '#13' },
  { key: 'erp_pending_pr',     label: 'ERP Pending PRs',       ref: '#14' },
  { key: 'erp_material_issue', label: 'ERP Material Issue',    ref: '#15' },
  { key: 'erp_item_cost',      label: 'ERP Item Cost',         ref: '#16' },
  { key: 'erp_fg_ageing',      label: 'ERP FG Ageing',         ref: '#17' },
  // L2 Demand
  { key: 'demand_freeze',      label: 'Demand Freeze',          ref: 'L2' },
  { key: 'demand_transaction', label: 'Demand Transactions',    ref: 'L2' },
  { key: 'demand_history',     label: 'Demand History',         ref: 'L2' },
  // L3 MPS
  { key: 'mps_schedule',       label: 'MPS Schedule',           ref: 'L3' },
  { key: 'mps_history',        label: 'MPS History',            ref: 'L3' },
  { key: 'planning_calendar',  label: 'Planning Calendar',      ref: 'L3' },
  // L4 R3SS
  { key: 'r3ss_plan',          label: 'R3SS Plan',              ref: 'L4' },
  { key: 'r3ss_summary',       label: 'R3SS Summary',           ref: 'L4' },
  // L6 Release
  { key: 'release_rows',       label: 'Release Snapshot',       ref: 'L6' },
  // L7 Material
  { key: 'bom_requirement',    label: 'BOM Requirement',        ref: 'L7' },
  { key: 'material_shortage',  label: 'Material Shortages',     ref: 'L7' },
]

export default function PPCDataBrowse() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedTable = searchParams.get('table') || ''
  const [search, setSearch] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  function selectTable(key) {
    setSearchParams(key ? { table: key } : {})
    setSearch('')
    setData(null)
    setError('')
  }

  async function fetchData(tableKey, searchTerm) {
    if (!tableKey) return
    setLoading(true)
    setError('')
    try {
      const result = await api.ppcDataTable(tableKey, 500, searchTerm)
      setData(result)
    } catch (err) {
      if (err.status === 404) {
        setData(null)
        setError(`No data loaded for "${tableKey}" yet. Upload the master file first.`)
      } else {
        setError(err.message)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (selectedTable) fetchData(selectedTable, '')
  }, [selectedTable])

  function handleSearch(e) {
    e.preventDefault()
    fetchData(selectedTable, search)
  }

  // Collect all column keys from the data
  const allKeys = []
  if (data?.rows?.length) {
    const keySet = new Set()
    data.rows.forEach((r) => {
      Object.keys(r.data).forEach((k) => keySet.add(k))
    })
    allKeys.push(...Array.from(keySet).sort())
  }

  const tableMeta = ALL_TABLES.find((t) => t.key === selectedTable)

  return (
    <section className="screen">
      <TopBar subtitle="PPC Department" />
      <div className="wrap" style={selectedTable && data ? { maxWidth: 'none', padding: '22px 26px' } : undefined}>
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/ppc-data">PPC Data</Link> › Data Browser
        </div>
        <button className="backbtn" onClick={() => navigate('/ppc-data')}>← Back to PPC Data</button>

        {/* Table selector */}
        <div className="panel">
          <h3 style={{ marginBottom: 12 }}>Select a table</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 4 }}>
            {ALL_TABLES.map((t) => (
              <button
                key={t.key}
                onClick={() => selectTable(t.key)}
                style={{
                  padding: '6px 12px',
                  borderRadius: 6,
                  border: selectedTable === t.key ? '2px solid var(--accent)' : '1px solid var(--line)',
                  background: selectedTable === t.key ? '#e8f4fd' : '#fff',
                  color: selectedTable === t.key ? 'var(--accent)' : 'var(--ink)',
                  fontWeight: selectedTable === t.key ? 700 : 400,
                  fontSize: 13,
                  cursor: 'pointer',
                  transition: 'all .12s',
                }}
              >
                <span style={{ fontFamily: 'monospace', fontSize: 10, opacity: 0.6, marginRight: 4 }}>
                  {t.ref}
                </span>
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Data display */}
        {selectedTable && (
          <div className="panel">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>
                {tableMeta?.label || selectedTable}
                {data && (
                  <span style={{ fontWeight: 400, fontSize: 13, color: 'var(--muted)', marginLeft: 8 }}>
                    {data.row_count.toLocaleString()} rows
                    {data.truncated && <> (showing first {data.rows.length})</>}
                    {data.uploader && <> · uploaded by {data.uploader}</>}
                    {data.uploaded_at && <> · {new Date(data.uploaded_at).toLocaleDateString()}</>}
                  </span>
                )}
              </h3>
              <form onSubmit={handleSearch} style={{ display: 'flex', gap: 6 }}>
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search…"
                  style={{ padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13, width: 200 }}
                />
                <button type="submit" className="btn-upload" style={{ padding: '6px 14px', fontSize: 13 }}>
                  Search
                </button>
                {search && (
                  <button
                    type="button"
                    onClick={() => { setSearch(''); fetchData(selectedTable, '') }}
                    style={{ padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, background: '#fff', cursor: 'pointer', fontSize: 12 }}
                  >
                    Clear
                  </button>
                )}
              </form>
            </div>

            {loading && <div className="loading">Loading…</div>}
            {error && <div className="upload-status error">{error}</div>}

            {!loading && !error && data && data.rows.length === 0 && (
              <p className="note">No rows match the search.</p>
            )}

            {!loading && !error && data && data.rows.length > 0 && (
              <div className="table-scroll" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
                <table style={{ fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8' }}>#</th>
                      {allKeys.map((k) => (
                        <th key={k} style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8', whiteSpace: 'nowrap' }}>
                          {k}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((row) => (
                      <tr key={row.sr_no}>
                        <td className="muted">{row.sr_no}</td>
                        {allKeys.map((k) => (
                          <td key={k} style={{ whiteSpace: 'nowrap', maxWidth: 250, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {row.data[k] != null ? String(row.data[k]) : <span className="muted">—</span>}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
