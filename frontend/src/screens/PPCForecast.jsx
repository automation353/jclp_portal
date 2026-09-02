import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

/**
 * PPC Forecast — S&OP module. Simple upload widget + list of past uploads.
 * No parsing yet; that comes when the file structure is agreed. Each upload
 * is saved to disk and recorded in the DB so the audit trail is intact.
 */
export default function PPCForecast() {
  const navigate = useNavigate()
  const [uploads, setUploads] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(null)   // {kind, text}
  const [notes, setNotes] = useState('')
  const fileInputRef = useRef(null)

  async function refresh() {
    setLoading(true)
    try {
      setUploads(await api.ppcForecastUploads())
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
      const row = await api.ppcForecastUpload(file, notes)
      setUploadMsg({
        kind: 'success',
        text: `✅ ${row.original_filename} uploaded. Saved to the PPC Forecast archive.`,
      })
      setNotes('')
      await refresh()
    } catch (err) {
      setUploadMsg({ kind: 'error', text: `❌ ${err.message}` })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  return (
    <section className="screen">
      <TopBar subtitle="S&OP › PPC Forecast" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/s-and-op">S&amp;OP</Link> ›{' '}
          PPC Forecast
        </div>
        <button className="backbtn" onClick={() => navigate('/s-and-op')}>← Back to S&amp;OP</button>

        <div className="panel">
          <h3>PPC Forecast — File Upload</h3>
          <p className="note" style={{ marginBottom: 16 }}>
            Upload the PPC forecast file (.xlsx / .xls / .csv). Every upload is stored
            and listed below. Parsing and analytics can be wired in once the file
            structure is agreed.
          </p>

          <div style={{
            padding: 16, borderRadius: 10, background: '#eaf3fb',
            border: '1px dashed var(--accent)', marginBottom: 20,
          }}>
            <div style={{ marginBottom: 10 }}>
              <b>Choose forecast file:</b>{' '}
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xlsm,.xls,.csv"
                disabled={uploading}
                onChange={(e) => handleUpload(e.target.files?.[0])}
              />
            </div>
            <div className="field" style={{ marginBottom: 0 }}>
              <label htmlFor="ppc-notes" style={{ fontSize: 12, color: 'var(--muted)', fontWeight: 700 }}>
                Optional note for this upload
              </label>
              <input
                id="ppc-notes"
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. Aug forecast, revised — Rasika"
                disabled={uploading}
                style={{ width: '100%', padding: 8, marginTop: 4, border: '1px solid #cbd5e1', borderRadius: 6 }}
              />
            </div>
            {uploadMsg && (
              <div className={`upload-status ${uploadMsg.kind}`} style={{ marginTop: 12 }}>
                {uploadMsg.kind === 'loading' && <span className="spinner" />}
                {uploadMsg.text}
              </div>
            )}
          </div>

          <h3 style={{ fontSize: 16, marginTop: 24, marginBottom: 8 }}>Recent uploads</h3>
          {loading && <div className="loading">Loading uploads…</div>}
          {error && <div className="login-error">{error}</div>}
          {!loading && !error && uploads.length === 0 && (
            <p className="note">No PPC Forecast files uploaded yet.</p>
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
