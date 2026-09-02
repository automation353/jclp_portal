import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

// Live view of the target Google Sheet the n8n workflow writes into.
// `/preview` renders the sheet read-only with the tab bar visible so users
// can flip between CP Req / RM Req / Quantity Sheet.
const SHEET_ID = '1jg4EFvWaRjwJ4l8tt0FqBM0Fy3sHT-0y6LrWhYizMQ0'
const SHEET_EMBED_URL = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/preview`
const SHEET_OPEN_URL = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/edit?usp=sharing`

/**
 * PPC (Production Planning & Control) — file upload + archive.
 *
 * File flow:
 *   Frontend (drag-and-drop or click-to-browse) → Django (audit + archive)
 *   → configured webhook → Google Sheet.
 *
 * The Django endpoint returns a `sheet_sync` block indicating whether the
 * forward to the sheet succeeded, was skipped, or errored. We surface that
 * to the user immediately so there's no ambiguity about where the file
 * ended up.
 */
export default function PPC() {
  const navigate = useNavigate()
  const [payload, setPayload] = useState({ uploads: [], target_sheet_url: '', webhook_configured: false })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(null)
  const [notes, setNotes] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [sheetRefreshKey, setSheetRefreshKey] = useState(0)
  const fileInputRef = useRef(null)

  async function refresh() {
    setLoading(true)
    try {
      setPayload(await api.ppcUploads())
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
    setUploadMsg({ kind: 'loading', text: `Uploading ${file.name}…` })
    try {
      const row = await api.ppcUpload(file, notes)
      const sync = row.sheet_sync || {}

      let extra = ''
      if (!sync.attempted) {
        extra = '  ·  Sheet sync skipped (webhook not configured)'
      } else if (sync.ok) {
        extra = '  ·  ✅ Also pushed to the linked Google Sheet.'
      } else {
        const why = sync.error || `HTTP ${sync.http_status}`
        extra = `  ·  ⚠ Sheet sync failed: ${why}`
      }

      setUploadMsg({
        kind: sync.attempted && !sync.ok ? 'warn' : 'success',
        text: `✅ ${row.original_filename} archived.${extra}`,
      })
      setNotes('')
      await refresh()
      // Give n8n a few seconds to finish writing to the sheet, then reload
      // the iframe so the newly-pushed rows show up.
      if (sync.attempted && sync.ok) {
        setTimeout(() => setSheetRefreshKey((k) => k + 1), 4000)
      }
    } catch (err) {
      setUploadMsg({ kind: 'error', text: `❌ ${err.message}` })
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

  const uploads = payload.uploads || []

  return (
    <section className="screen">
      <TopBar subtitle="PPC Department" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> › PPC
        </div>
        <button className="backbtn" onClick={() => navigate('/departments')}>← Back to Departments</button>

        <div style={{ background: '#e8f4fd', border: '1px solid #b3d9f2', borderRadius: 8, padding: '10px 16px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 18 }}>🏭</span>
          <span style={{ fontSize: 13, flex: 1 }}>
            <b>New:</b> The PPC Data Pipeline is live — upload all master files, browse loaded tables.
          </span>
          <Link to="/ppc-data" className="btn-upload" style={{ padding: '6px 14px', fontSize: 12 }}>
            Open PPC Data →
          </Link>
        </div>

        <div className="panel">
          <h3>PPC — File Upload</h3>
          <p className="note" style={{ marginBottom: 8 }}>
            Upload production-planning &amp; control files (.xlsx / .xls / .csv).
            Every upload is archived here <b>and</b> pushed into the linked
            Google Sheet.
          </p>
          {payload.target_sheet_url && (
            <p className="note" style={{ marginBottom: 16 }}>
              📊 Data flows to:{' '}
              <a href={payload.target_sheet_url} target="_blank" rel="noopener noreferrer">
                open target Google Sheet ↗
              </a>
              {!payload.webhook_configured && (
                <span style={{ color: '#b45309', marginLeft: 8 }}>
                  ⚠ Sheet sync not yet configured — set <code>JCLP_PPC_SHEET_WEBHOOK</code> in <code>/root/.env</code>.
                </span>
              )}
            </p>
          )}

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
                ? 'Uploading…'
                : <>Drag &amp; drop the PPC file here, or <b>click to browse</b></>}
            </div>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xlsm,.xls,.csv"
            style={{ display: 'none' }}
            disabled={uploading}
            onChange={(e) => handleUpload(e.target.files?.[0])}
          />

          <div className="field" style={{ marginBottom: 16 }}>
            <label htmlFor="ppc-notes" style={{ fontSize: 12, color: 'var(--muted)', fontWeight: 700 }}>
              Optional note for this upload
            </label>
            <input
              id="ppc-notes"
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Aug production schedule v2"
              disabled={uploading}
              style={{ width: '100%', padding: 8, marginTop: 4, border: '1px solid #cbd5e1', borderRadius: 6 }}
            />
          </div>

          {uploadMsg && (
            <div className={`upload-status ${uploadMsg.kind}`}>
              {uploadMsg.kind === 'loading' && <span className="spinner" />}
              {uploadMsg.text}
            </div>
          )}

          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: 24, marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
            <h3 style={{ fontSize: 16, margin: 0 }}>📊 Live data — CP Req · RM Req · Quantity Sheet</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                className="btn-upload"
                style={{ background: 'var(--steel)', padding: '6px 12px', fontSize: 12 }}
                onClick={() => setSheetRefreshKey((k) => k + 1)}
              >
                ⟳ Refresh
              </button>
              <a
                className="btn-upload"
                href={SHEET_OPEN_URL}
                target="_blank"
                rel="noopener noreferrer"
                style={{ background: 'var(--steel)', padding: '6px 12px', fontSize: 12 }}
              >
                ↗ Open in Google Sheets
              </a>
            </div>
          </div>
          <p className="note" style={{ marginBottom: 10 }}>
            The three tabs below are the live target sheet — n8n writes into them right after each upload. Use the tab bar at the bottom of the embed to flip between sheets.
          </p>
          <div className="sheet-embed">
            <iframe
              key={sheetRefreshKey}
              src={SHEET_EMBED_URL}
              title="PPC target Google Sheet"
              loading="lazy"
            />
          </div>

          <h3 style={{ fontSize: 16, marginTop: 24, marginBottom: 8 }}>Recent uploads</h3>
          {loading && <div className="loading">Loading uploads…</div>}
          {error && <div className="login-error">{error}</div>}
          {!loading && !error && uploads.length === 0 && (
            <p className="note">No PPC files uploaded yet.</p>
          )}
          {!loading && !error && uploads.length > 0 && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>File</th>
                    <th>Uploaded by</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {uploads.map((u) => (
                    <tr key={u.id}>
                      <td className="muted">{new Date(u.uploaded_at).toLocaleString()}</td>
                      <td><b>{u.original_filename}</b></td>
                      <td>
                        {u.uploader_username}
                        {u.uploader_department && (
                          <span className="muted"> · {u.uploader_department}</span>
                        )}
                      </td>
                      <td>{u.notes || <span className="muted">—</span>}</td>
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
