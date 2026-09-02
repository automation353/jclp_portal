import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

/**
 * The 5 S&OP data files — drives the pill picker and status table.
 */
const SOP_TABLES = [
  { key: 'sop_dpr',            icon: '📦', short: 'DPR',            label: 'DPR — Stock Ledger Report',      file: 'Stock_Ledger_Report_*.xlsx' },
  { key: 'sop_forecast',       icon: '📈', short: 'Forecast',       label: 'Forecast vs Sales Report',       file: 'Forecast_VS_Sales_Report_*.xlsx' },
  { key: 'sop_opening_stock',  icon: '🏭', short: 'Opening Stock',  label: 'Opening Stock — Valuation',      file: 'Stock_Statement_Valuation_Report_*.xlsx' },
  { key: 'sop_green_level',    icon: '🟢', short: 'Green Level',    label: 'PPC Green Level Quantities',     file: 'Green Level Quantities Sheet_*.xlsx' },
  { key: 'sop_sales_register', icon: '🧾', short: 'Sales Register', label: 'Sales Register — Invoice',       file: 'Sales_Invoice_Register_Report_*.xlsx' },
]

const STORAGE_KEY = 'jcpl.sop.upload_type'
const DEFAULT_KEY = SOP_TABLES[0].key

function tableFor(key) {
  return SOP_TABLES.find((t) => t.key === key) || SOP_TABLES[0]
}

export default function SopUpload() {
  const navigate = useNavigate()
  const fileInputRef = useRef(null)

  const [tableKey, setTableKey] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return SOP_TABLES.some((t) => t.key === stored) ? stored : DEFAULT_KEY
  })
  const [file, setFile] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [status, setStatus] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [uploads, setUploads] = useState([])
  const [loading, setLoading] = useState(true)


  function pickTable(key) {
    setTableKey(key)
    localStorage.setItem(STORAGE_KEY, key)
  }

  function handleFile(f) {
    if (!f) return
    setFile(f)
    setStatus(null)
  }

  function onDrop(e) {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0])
  }

  async function refresh() {
    setLoading(true)
    try {
      const data = await api.sopUploads()
      setUploads(data.uploads || [])
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }
  useEffect(() => { refresh() }, [])

  async function upload() {
    if (!file) {
      setStatus({ kind: 'error', message: 'Please choose a file first.' })
      return
    }
    setUploading(true)
    setStatus({ kind: 'loading', message: `Uploading ${file.name}…` })

    try {
      const result = await api.sopUpload(file, tableKey)
      if (result.parse_error) {
        setStatus({
          kind: 'error',
          message: `❌ Parse failed for ${result.original_filename}: ${result.parse_error}`,
        })
      } else {
        const syncNote = result.sheet_sync === 'triggered'
          ? '  Sheet sync triggered — Append1 will auto-update.'
          : ''
        setStatus({
          kind: 'success',
          message: `✅ ${result.original_filename} → ${tableFor(result.table_key).short} — ${(result.row_count || 0).toLocaleString()} rows parsed and stored.${syncNote}`,
        })
        setFile(null)
        if (fileInputRef.current) fileInputRef.current.value = ''
        refresh()
      }
    } catch (err) {
      setStatus({ kind: 'error', message: `❌ ${err.message}` })
    } finally {
      setUploading(false)
    }
  }

  // Group current uploads by table_key
  const loadedTables = {}
  uploads.forEach((u) => {
    if (u.is_current && u.row_count > 0) loadedTables[u.table_key] = u
  })

  return (
    <section className="screen">
      <TopBar subtitle="S&OP › Upload Data" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/s-and-op">S&amp;OP</Link> ›{' '}
          <Link to="/s-and-op/demand-supply">Demand &amp; Supply</Link> › Upload
        </div>
        <button className="backbtn" onClick={() => navigate('/s-and-op/demand-supply')}>
          ← Back to Dashboard
        </button>

        <div className="panel">
          <h3>📤 S&amp;OP Data Upload</h3>
          <p className="note" style={{ marginBottom: 20 }}>
            Pick the data type, then upload the Excel file. It will parse the data into the portal
            database and sync to the connected Google Sheet tab.
          </p>

          {/* ── Pill picker ── */}
          <div className="report-picker" role="tablist" aria-label="Data type">
            {SOP_TABLES.map((t) => (
              <button
                key={t.key}
                type="button"
                className={`pill-tab ${tableKey === t.key ? 'active' : ''}`}
                onClick={() => pickTable(t.key)}
                role="tab"
                aria-selected={tableKey === t.key}
              >
                {t.icon} {t.short}
              </button>
            ))}
          </div>

          {/* ── Drop zone ── */}
          <div
            className={`dropzone ${dragOver ? 'dragover' : ''}`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
          >
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="1.5" aria-hidden="true">
              <path d="M12 16V4M12 4l-4 4M12 4l4 4" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <div>Drag &amp; drop your .xlsx file here, or click to browse</div>
            {file && <div className="file-name">{file.name}</div>}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xlsm,.xls"
            style={{ display: 'none' }}
            onChange={(e) => handleFile(e.target.files?.[0])}
          />

          {/* ── Upload button ── */}
          <button
            className="btn-primary"
            style={{ marginTop: 20 }}
            onClick={upload}
            disabled={uploading || !file}
          >
            {uploading ? 'Uploading…' : 'Upload & Refresh Sheet'}
          </button>

          {/* ── Status banner ── */}
          {status && (
            <div className={`upload-status ${status.kind}`}>
              {status.kind === 'loading' && <span className="spinner" />}
              {status.message}
            </div>
          )}

          <p className="note" style={{ marginTop: 20 }}>
            Uploads are parsed by the portal and synced to <code>jollyclamps.app.n8n.cloud</code> →
            Google Sheet. The data type determines which sheet tab is refreshed.
          </p>
        </div>

        {/* ── Data files status board ── */}
        <div className="panel">
          <h3 style={{ marginBottom: 12 }}>📊 S&amp;OP Data Files — Load Status</h3>
          <p className="note" style={{ marginBottom: 16 }}>
            <b>{SOP_TABLES.filter((t) => loadedTables[t.key]).length}</b> of <b>5</b> files loaded.
            All 5 are needed for the full Demand &amp; Supply Dashboard.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 36 }}></th>
                  <th>Data Type</th>
                  <th>Status</th>
                  <th style={{ textAlign: 'right' }}>Rows</th>
                  <th>Last Upload</th>
                  <th>Expected File</th>
                </tr>
              </thead>
              <tbody>
                {SOP_TABLES.map((t) => {
                  const loaded = loadedTables[t.key]
                  return (
                    <tr key={t.key}>
                      <td style={{ fontSize: 18, textAlign: 'center' }}>{t.icon}</td>
                      <td style={{ fontWeight: 600 }}>{t.short}</td>
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
                      <td className="muted" style={{ fontSize: 12 }}>{t.file}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* ── Recent upload history ── */}
        {uploads.length > 0 && (
          <div className="panel">
            <h3 style={{ marginBottom: 12 }}>Recent Uploads</h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>File</th>
                    <th>Table</th>
                    <th style={{ textAlign: 'right' }}>Rows</th>
                    <th>Current</th>
                    <th>Uploaded by</th>
                  </tr>
                </thead>
                <tbody>
                  {uploads.map((u) => (
                    <tr key={u.id} style={u.parse_error ? { background: '#fef2f2' } : undefined}>
                      <td className="muted" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                        {new Date(u.uploaded_at).toLocaleString()}
                      </td>
                      <td><b>{u.original_filename}</b></td>
                      <td style={{ fontFamily: 'monospace', fontSize: 12 }}>
                        {tableFor(u.table_key).short}
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}>
                        {u.row_count.toLocaleString()}
                      </td>
                      <td>
                        {u.is_current
                          ? <span style={{ color: 'var(--ok)', fontWeight: 700 }}>✓</span>
                          : <span className="muted">—</span>}
                      </td>
                      <td>{u.uploader || <span className="muted">system</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
