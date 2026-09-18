import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

/**
 * Master tables and their expected filenames — drives the reference table
 * shown below the upload zone, and helps the user know what to upload.
 */
/**
 * R3SS-essential master tables only.
 * Non-essential masters (route_master, operation_stage_map, capacity_ppp,
 * machine_master, customer_part, rate_asp) are needed for L5-L8 phases
 * and will be added back when those phases are built.
 */
const MASTER_TABLES = [
  { key: 'item_master',         ref: 'W1.1',  file: 'Product Group Mapping.xlsx',      label: 'Item Master',           rows: '~4,822',  source: 'ERP' },
  { key: 'family_hierarchy',    ref: 'W1.2',  file: 'Monitoring.xlsx (Family Group)',   label: 'Family Hierarchy',      rows: '~4,000',  source: 'File' },
  { key: 'stock_policy',        ref: 'W1.14', file: 'Green Level RM/CP/Packing.xlsx',  label: 'Stock Policy (Green)',  rows: '~1,500',  source: 'File' },
  { key: 'batch_ebq',           ref: 'W1.8',  file: 'Monitoring.xlsx (EBQ / Batch)',   label: 'Batch / EBQ',           rows: '~80',     source: 'File' },
  { key: 'lead_time',           ref: 'W1.9',  file: 'Lead Time Data.xlsx',             label: 'Lead Time',             rows: '~1,684',  source: 'File' },
  { key: 'part_engineering',    ref: 'W1.12', file: 'T-Bolt BOM master.xlsx',          label: 'Part Engineering',      rows: '~500',    source: 'File' },
  { key: 'bom_master',          ref: 'W1.11', file: 'BOM_Item_Template.xlsx',          label: 'BOM Master',            rows: '~37,149', source: 'ERP' },
]

// Tables managed via UI forms (no file upload)
const FORM_TABLES = [
  { key: 'working_calendar',   ref: 'W1.10', label: 'Working Calendar',       note: 'maintain 1 year ahead' },
]

/**
 * R3SS source files — uploaded monthly (or as data refreshes).
 * These feed directly into compute_r3ss.py when Recompute is triggered.
 */
const R3SS_SOURCE_TABLES = [
  { key: 'fg_stock_statement', ref: 'S1', file: 'FG.xlsx',                   label: 'FG Stock Statement',    freq: 'Monthly', note: 'Opening Balance, FG (closing qty)' },
  { key: 'dpr_production',     ref: 'S2', file: 'DPR all Plant.xlsx',        label: 'DPR Production',        freq: 'Monthly', note: 'Pack (FG produced qty)' },
  { key: 'fg_dispatch',        ref: 'S3', file: 'FG Issue qty .xlsx',        label: 'FG Dispatch',           freq: 'Monthly', note: 'Disp (sales/dispatch qty)' },
  { key: 'mps_schedule_form',  ref: 'S4', file: 'MpsSS.xlsm',               label: 'MPS Schedule Form',     freq: 'Monthly', note: 'W1-W5 weeks, Additional Demand' },
  { key: 'demand_freeze',      ref: 'S5', file: 'August forecast 2026.xlsx', label: 'Demand Freeze',         freq: 'Monthly', note: 'Initial Demand (also via Demand Freeze page)' },
]

/**
 * R3SS-essential ERP reports only.
 * Other ERP reports (CP/RM/PM stock, consumables, pending PO/PR, etc.)
 * will be added for L5-L8 phases.
 */
const ERP_TABLES = [
  { key: 'erp_fg_stock',      ref: 'E3',  label: 'FG Stock Report',        freq: 'Daily',  note: 'Opening + Receipt + Issued + Closing' },
  { key: 'erp_sales_orders',  ref: 'E12', label: 'Sales Orders (SO)',      freq: 'Daily',  note: 'SO Tracking Master — recheck' },
]

export default function PPCDataUpload() {
  const navigate = useNavigate()
  const fileInputRef = useRef(null)
  const [uploads, setUploads] = useState([])
  const [parsers, setParsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(null)
  const [notes, setNotes] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [manualKey, setManualKey] = useState('')

  async function refresh() {
    setLoading(true)
    try {
      const data = await api.ppcDataUploads()
      setUploads(data.uploads || [])
      setParsers(data.available_parsers || [])
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { refresh() }, [])

  async function handleUpload(file) {
    if (!file) return
    setUploading(true)
    setUploadMsg({ kind: 'loading', text: `Uploading and parsing ${file.name}…`, step: 1 })
    try {
      const timer = setTimeout(() => {
        setUploadMsg(prev => prev?.step === 1
          ? { kind: 'loading', text: `Syncing ${file.name} to Google Sheet…`, step: 2 }
          : prev)
      }, 3000)
      const result = await api.ppcDataUpload(file, notes, manualKey || undefined)
      clearTimeout(timer)
      const rows = result.row_count || 0
      const table = result.table_key || '?'
      const syncOk = result.sheet_sync?.ok
      const syncMsg = syncOk === true
        ? ' Data synced to Google Sheet.'
        : syncOk === false
          ? ' (Sheet sync failed — data saved locally)'
          : ''
      setUploadMsg({
        kind: result.parse_error ? 'error' : 'success',
        text: result.parse_error
          ? `Parse failed for ${result.original_filename}: ${result.parse_error}`
          : `${result.original_filename} → ${table} — ${rows.toLocaleString()} rows parsed.${syncMsg}`,
      })
      setNotes('')
      setManualKey('')
      await refresh()
    } catch (err) {
      setUploadMsg({ kind: 'error', text: err.message })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  function onDrop(e) {
    e.preventDefault()
    setDragOver(false)
    if (uploading) return
    const f = e.dataTransfer?.files?.[0]
    if (f) handleUpload(f)
  }

  // Group uploads by table_key for the status board
  const loadedTables = {}
  uploads.forEach((u) => {
    if (u.is_current && u.row_count > 0) loadedTables[u.table_key] = u
  })

  return (
    <section className="screen">
      <TopBar subtitle="PPC Department" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/ppc-data">PPC Data</Link> › Data Upload
        </div>
        <button className="backbtn" onClick={() => navigate('/ppc-data')}>← Back to PPC Data</button>

        <div className="panel">
          <h3>PPC Data Upload</h3>
          <p className="note" style={{ marginBottom: 8 }}>
            Drop any master or ERP Excel file below. The portal auto-detects
            which table it belongs to from the filename and parses it into the database.
          </p>
          <p className="note" style={{ marginBottom: 16, fontSize: 12, color: 'var(--muted)' }}>
            Supported: .xlsx and .xlsm files · {MASTER_TABLES.length} masters + {R3SS_SOURCE_TABLES.length} R3SS sources + {ERP_TABLES.length} ERP · See reference tables below
          </p>

          {/* Drop zone */}
          <div
            className={`dropzone ${dragOver ? 'dragover' : ''}`}
            onClick={() => !uploading && fileInputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); if (!uploading) setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            style={{ marginBottom: 12 }}
          >
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="1.5" aria-hidden="true">
              <path d="M12 16V4M12 4l-4 4M12 4l4 4" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <div>
              {uploading
                ? 'Parsing…'
                : <>Drag &amp; drop the master file here, or <b>click to browse</b></>}
            </div>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xlsm,.xls"
            style={{ display: 'none' }}
            disabled={uploading}
            onChange={(e) => handleUpload(e.target.files?.[0])}
          />

          {/* Manual table key override + notes */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
            <div className="field" style={{ flex: 1, minWidth: 200 }}>
              <label htmlFor="ppc-manual-key" style={{ fontSize: 12, color: 'var(--muted)', fontWeight: 700 }}>
                Override table type (optional — auto-detected from filename)
              </label>
              <select
                id="ppc-manual-key"
                value={manualKey}
                onChange={(e) => setManualKey(e.target.value)}
                disabled={uploading}
                style={{ width: '100%', padding: 8, marginTop: 4, border: '1px solid #cbd5e1', borderRadius: 6, background: '#fff' }}
              >
                <option value="">Auto-detect from filename</option>
                {[...MASTER_TABLES.map(t => t.key), ...R3SS_SOURCE_TABLES.map(t => t.key), ...ERP_TABLES.map(t => t.key)].map((k) => (
                  <option key={k} value={k}>{k}</option>
                ))}
              </select>
            </div>
            <div className="field" style={{ flex: 1, minWidth: 200 }}>
              <label htmlFor="ppc-notes" style={{ fontSize: 12, color: 'var(--muted)', fontWeight: 700 }}>
                Optional note
              </label>
              <input
                id="ppc-notes"
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. Aug 2026 BOM refresh"
                disabled={uploading}
                style={{ width: '100%', padding: 8, marginTop: 4, border: '1px solid #cbd5e1', borderRadius: 6 }}
              />
            </div>
          </div>

          {uploadMsg && (
            <div className={`upload-status ${uploadMsg.kind}`}>
              {uploadMsg.kind === 'loading' && <span className="spinner" />}
              {uploadMsg.text}
            </div>
          )}
        </div>

        {/* Status board — which tables are loaded */}
        <div className="panel">
          <h3 style={{ marginBottom: 12 }}>📊 Foundation Tables — Load Status</h3>
          <p className="note" style={{ marginBottom: 16 }}>
            {MASTER_TABLES.filter(t => loadedTables[t.key]).length} of {MASTER_TABLES.length} master tables loaded.
            Green = has current data. Grey = not yet uploaded.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Ref</th>
                  <th>Table</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>Last upload</th>
                  <th>File</th>
                  <th>Expected file</th>
                </tr>
              </thead>
              <tbody>
                {MASTER_TABLES.map((t) => {
                  const loaded = loadedTables[t.key]
                  return (
                    <tr key={t.key}>
                      <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{t.ref}</td>
                      <td>
                        {loaded
                          ? <Link to={`/ppc-data/browse?table=${t.key}`} style={{ fontWeight: 600 }}>{t.label}</Link>
                          : <span>{t.label}</span>}
                      </td>
                      <td>
                        {loaded
                          ? <span style={{ color: 'var(--ok)', fontWeight: 700, fontSize: 12 }}>● Loaded</span>
                          : <span style={{ color: 'var(--muted)', fontSize: 12 }}>○ Empty</span>}
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}>
                        {loaded ? loaded.row_count.toLocaleString() : '—'}
                      </td>
                      <td className="muted" style={{ fontSize: 12 }}>
                        {loaded ? new Date(loaded.uploaded_at).toLocaleString() : '—'}
                      </td>
                      <td style={{ fontSize: 12 }}>
                        {loaded ? loaded.original_filename : '—'}
                      </td>
                      <td className="muted" style={{ fontSize: 12 }}>{t.file}</td>
                    </tr>
                  )
                })}
                {FORM_TABLES.map((t) => {
                  const loaded = loadedTables[t.key]
                  return (
                    <tr key={t.key} style={{ opacity: 0.6 }}>
                      <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{t.ref}</td>
                      <td>{t.label}</td>
                      <td>
                        {loaded
                          ? <span style={{ color: 'var(--ok)', fontWeight: 700, fontSize: 12 }}>● Loaded</span>
                          : <span style={{ color: 'var(--muted)', fontSize: 12 }}>○ UI form</span>}
                      </td>
                      <td style={{ textAlign: 'right' }}>{loaded ? loaded.row_count.toLocaleString() : '—'}</td>
                      <td className="muted" style={{ fontSize: 12 }}>
                        {loaded ? new Date(loaded.uploaded_at).toLocaleString() : '—'}
                      </td>
                      <td colSpan={2} className="muted" style={{ fontSize: 12, fontStyle: 'italic' }}>{t.note}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* R3SS Source Files status */}
        <div className="panel">
          <h3 style={{ marginBottom: 12 }}>📊 R3SS Source Files — Load Status</h3>
          <p className="note" style={{ marginBottom: 16 }}>
            {R3SS_SOURCE_TABLES.filter(t => loadedTables[t.key]).length} of {R3SS_SOURCE_TABLES.length} R3SS source files loaded.
            Upload these monthly before running Recompute on the R3SS Plan page.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Ref</th>
                  <th>Table</th>
                  <th>Frequency</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>Last upload</th>
                  <th>File</th>
                  <th>Expected file</th>
                </tr>
              </thead>
              <tbody>
                {R3SS_SOURCE_TABLES.map((t) => {
                  const loaded = loadedTables[t.key]
                  return (
                    <tr key={t.key}>
                      <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{t.ref}</td>
                      <td>
                        {loaded
                          ? <Link to={`/ppc-data/browse?table=${t.key}`} style={{ fontWeight: 600 }}>{t.label}</Link>
                          : <span>{t.label}</span>}
                      </td>
                      <td className="muted" style={{ fontSize: 12 }}>{t.freq}</td>
                      <td>
                        {loaded
                          ? <span style={{ color: 'var(--ok)', fontWeight: 700, fontSize: 12 }}>● Loaded</span>
                          : <span style={{ color: 'var(--muted)', fontSize: 12 }}>○ Empty</span>}
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}>
                        {loaded ? loaded.row_count.toLocaleString() : '—'}
                      </td>
                      <td className="muted" style={{ fontSize: 12 }}>
                        {loaded ? new Date(loaded.uploaded_at).toLocaleString() : '—'}
                      </td>
                      <td style={{ fontSize: 12 }}>
                        {loaded ? loaded.original_filename : '—'}
                      </td>
                      <td className="muted" style={{ fontSize: 12 }}>{t.file}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* ERP Tables status */}
        <div className="panel">
          <h3 style={{ marginBottom: 12 }}>📡 ERP Reports — Load Status</h3>
          <p className="note" style={{ marginBottom: 16 }}>
            {ERP_TABLES.filter(t => loadedTables[t.key]).length} of {ERP_TABLES.length} ERP reports loaded.
            Upload FG Stock Report daily. SO Tracking as needed.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Ref</th>
                  <th>Table</th>
                  <th>Frequency</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>Last upload</th>
                  <th>File</th>
                </tr>
              </thead>
              <tbody>
                {ERP_TABLES.map((t) => {
                  const loaded = loadedTables[t.key]
                  return (
                    <tr key={t.key}>
                      <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{t.ref}</td>
                      <td>
                        {loaded
                          ? <Link to={`/ppc-data/browse?table=${t.key}`} style={{ fontWeight: 600 }}>{t.label}</Link>
                          : <span>{t.label}</span>}
                      </td>
                      <td className="muted" style={{ fontSize: 12 }}>{t.freq}</td>
                      <td>
                        {loaded
                          ? <span style={{ color: 'var(--ok)', fontWeight: 700, fontSize: 12 }}>● Loaded</span>
                          : <span style={{ color: 'var(--muted)', fontSize: 12 }}>○ Empty</span>}
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}>
                        {loaded ? loaded.row_count.toLocaleString() : '—'}
                      </td>
                      <td className="muted" style={{ fontSize: 12 }}>
                        {loaded ? new Date(loaded.uploaded_at).toLocaleString() : '—'}
                      </td>
                      <td style={{ fontSize: 12 }}>
                        {loaded ? loaded.original_filename : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent upload history */}
        <div className="panel">
          <h3 style={{ marginBottom: 12 }}>Recent uploads</h3>
          {loading && <div className="loading">Loading…</div>}
          {error && <div className="login-error">{error}</div>}
          {!loading && !error && uploads.length === 0 && (
            <p className="note">No PPC data files uploaded yet.</p>
          )}
          {!loading && !error && uploads.length > 0 && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>File</th>
                    <th>Table</th>
                    <th>Rows</th>
                    <th>Current</th>
                    <th>Uploaded by</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {uploads.map((u) => (
                    <tr key={u.id} style={u.parse_error ? { background: '#fef2f2' } : undefined}>
                      <td className="muted" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                        {new Date(u.uploaded_at).toLocaleString()}
                      </td>
                      <td><b>{u.original_filename}</b></td>
                      <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{u.table_key}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}>
                        {u.row_count.toLocaleString()}
                      </td>
                      <td>
                        {u.is_current
                          ? <span style={{ color: 'var(--ok)', fontWeight: 700 }}>✓</span>
                          : <span className="muted">—</span>}
                      </td>
                      <td>{u.uploader || <span className="muted">system</span>}</td>
                      <td>
                        {u.parse_error
                          ? <span style={{ color: 'var(--bad)', fontSize: 12 }}>❌ {u.parse_error.slice(0, 80)}</span>
                          : (u.notes || <span className="muted">—</span>)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
