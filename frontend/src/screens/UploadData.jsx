import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import TopBar from '../components/TopBar'

/**
 * The set of daily-upload reports and where each one is POSTed on n8n.
 * Kept as a single data table — adding another report type is one entry
 * (label + icon + webhook path). Mirrors
 * ``protal_for_datadumping/portal/index.html`` in the docs folder.
 */
const REPORTS = [
  {
    key: 'dpr',
    icon: '📊',
    short: 'DPR',
    label: 'DPR Report',
    webhook: 'https://jollyclamps.app.n8n.cloud/webhook/excel-upload',
  },
  {
    key: 'po',
    icon: '📦',
    short: 'Purchase Order',
    label: 'Purchase Order',
    webhook: 'https://jollyclamps.app.n8n.cloud/webhook/purchase-order-upload',
  },
  {
    key: 'rmc',
    icon: '⚙',
    short: 'RM Consumption',
    label: 'RM Consumption',
    webhook: 'https://jollyclamps.app.n8n.cloud/webhook/rm-consumption',
  },
  {
    key: 'rgl',
    icon: '🏷',
    short: 'RM Green Level',
    label: 'RM Green Level',
    webhook: 'https://jollyclamps.app.n8n.cloud/webhook/rm-green-level',
  },
  {
    key: 'mps',
    icon: '📈',
    short: 'MPS Demand',
    label: 'MPS Demand',
    webhook: 'https://jollyclamps.app.n8n.cloud/webhook/mps-demand',
  },
]

const STORAGE_KEY = 'jcpl.upload.report_type'
const DEFAULT_KEY = REPORTS[0].key

function reportFor(key) {
  return REPORTS.find((r) => r.key === key) || REPORTS[0]
}

export default function UploadData() {
  const navigate = useNavigate()
  const fileInputRef = useRef(null)

  // Remember the last-picked report type between visits, same as the original
  // standalone page did. Fall back to DPR if the stored key is no longer in
  // the REPORTS list (e.g. a report was removed).
  const [reportType, setReportType] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return REPORTS.some((r) => r.key === stored) ? stored : DEFAULT_KEY
  })
  const [file, setFile] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [status, setStatus] = useState(null) // {kind: 'success'|'error'|'loading', message}
  const [uploading, setUploading] = useState(false)

  function pickReport(key) {
    setReportType(key)
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

  async function upload() {
    if (!file) {
      setStatus({ kind: 'error', message: 'Please choose a file first.' })
      return
    }
    const report = reportFor(reportType)
    if (!report.webhook) {
      setStatus({ kind: 'error', message: `Unknown report type: ${reportType}` })
      return
    }

    const body = new FormData()
    body.append('file', file)

    setUploading(true)
    setStatus({ kind: 'loading', message: `Uploading ${report.label}…` })

    try {
      const res = await fetch(report.webhook, { method: 'POST', body })
      if (res.ok) {
        setStatus({
          kind: 'success',
          message:
            '✅ Upload received — n8n is refreshing your Google Sheet in the background. Large files can take a few minutes; check the sheet (or n8n\'s Executions tab) shortly to confirm it finished.',
        })
        setFile(null)
        if (fileInputRef.current) fileInputRef.current.value = ''
      } else {
        const text = await res.text()
        setStatus({ kind: 'error', message: `❌ Upload failed: ${text || res.statusText}` })
      }
    } catch (err) {
      setStatus({
        kind: 'error',
        message: `❌ Could not reach n8n. Check the webhook URL and CORS settings. (${err.message})`,
      })
    } finally {
      setUploading(false)
    }
  }

  return (
    <section className="screen">
      <TopBar subtitle="Purchase › Upload Data" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> › <Link to="/purchase">Purchase</Link> › Upload Data
        </div>
        <button className="backbtn" onClick={() => navigate('/purchase')}>← Back to Purchase</button>

        <div className="panel">
          <h3>📊 Daily Data Upload</h3>
          <p className="note" style={{ marginBottom: 20 }}>
            Pick the report type, then upload today's Excel file. It will replace whatever is
            currently in the connected Google Sheet tab.
          </p>

          <div className="report-picker" role="tablist" aria-label="Report type">
            {REPORTS.map((r) => (
              <button
                key={r.key}
                type="button"
                className={`pill-tab ${reportType === r.key ? 'active' : ''}`}
                onClick={() => pickReport(r.key)}
                role="tab"
                aria-selected={reportType === r.key}
              >
                {r.icon} {r.short}
              </button>
            ))}
          </div>

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
            accept=".xlsx,.xls,.csv"
            style={{ display: 'none' }}
            onChange={(e) => handleFile(e.target.files?.[0])}
          />

          <button
            className="btn-primary"
            style={{ marginTop: 20 }}
            onClick={upload}
            disabled={uploading || !file}
          >
            {uploading ? 'Uploading…' : 'Upload & Refresh Sheet'}
          </button>

          {status && (
            <div className={`upload-status ${status.kind}`}>
              {status.kind === 'loading' && <span className="spinner" />}
              {status.message}
            </div>
          )}

          <p className="note" style={{ marginTop: 20 }}>
            Uploads go to <code>jollyclamps.app.n8n.cloud</code> — the exact path depends on the
            report type selected above.
          </p>
        </div>
      </div>
    </section>
  )
}
