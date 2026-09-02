import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import TopBar from '../components/TopBar'

const STATUS_OPTIONS = ['', 'MTS', 'MTO']

// Fixed order the meeting agreed on for the segment slicer buttons.
// Segments in the file that aren't in this list are still rendered, tacked
// on after the known ones so nothing is dropped.
const SEGMENT_ORDER = ['OEM', 'Aftermarket', 'Export', 'Jaiswal']

export default function MtoMts() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const canUpload = user && (user.department === 'Operations' || user.role === 'super_admin')

  const [payload, setPayload] = useState(null) // {upload, month_labels, items, current_month_missing}
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(null) // {kind, text}
  const [savingIds, setSavingIds] = useState({})   // {itemId: 'saving' | 'saved' | 'error'}
  const [uploads, setUploads] = useState([])       // month picker options (Change 5 + 7)
  const [selectedUploadId, setSelectedUploadId] = useState(null)
  const [segmentFilter, setSegmentFilter] = useState('')  // '' = show all
  const [accountFilter, setAccountFilter] = useState('')  // '' = show all
  const fileInputRef = useRef(null)

  const uploadStatus = payload?.upload?.status || null
  const isProcessing = uploadStatus === 'processing'
  const isFailed = uploadStatus === 'failed'
  const isLocked = uploadStatus === 'locked'
  const isReadOnly = uploadStatus !== 'active'        // any non-active view is read-only
  const currentMonthMissing = !!payload?.current_month_missing

  async function refresh() {
    try {
      const data = await api.mtoMtsCurrent()
      setPayload(data)
      setSelectedUploadId(data.upload?.id ?? null)
      setLoadError('')
    } catch (err) {
      if (err.status === 404) setPayload(null)
      else setLoadError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function refreshUploadsList() {
    try {
      setUploads(await api.mtoMtsUploads())
    } catch { /* silent — the picker will just be empty */ }
  }

  async function selectUpload(uploadId) {
    if (!uploadId || uploadId === selectedUploadId) return
    setLoading(true)
    try {
      const data = await api.mtoMtsUploadDetail(uploadId)
      setPayload(data)
      setSelectedUploadId(uploadId)
    } catch (err) {
      setLoadError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { setLoading(true); refresh(); refreshUploadsList() }, [])

  // Poll while the backend subprocess is still parsing an upload.
  useEffect(() => {
    if (!isProcessing) return
    const id = setInterval(refresh, 2000)
    return () => clearInterval(id)
  }, [isProcessing])

  async function handleUpload(file) {
    if (!file) return
    setUploading(true)
    setUploadMsg({ kind: 'loading', text: `Uploading ${file.name}…` })
    try {
      await api.mtoMtsUpload(file)
      setUploadMsg({ kind: 'success', text: `✅ ${file.name} received — parsing in the background. Both departments will see it as soon as it's ready.` })
      await refresh()   // pulls status=processing; the poll effect takes over from here
      await refreshUploadsList()
    } catch (err) {
      setUploadMsg({ kind: 'error', text: `❌ ${err.message}` })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  function flashSave(itemId, kind) {
    setSavingIds((s) => ({ ...s, [itemId]: kind }))
    if (kind !== 'saving') {
      setTimeout(() => {
        setSavingIds((s) => {
          const next = { ...s }
          delete next[itemId]
          return next
        })
      }, 1500)
    }
  }

  async function patchField(item, field, newValue, extras = {}) {
    const oldValue = item[field] || ''
    if (oldValue === newValue) return

    // optimistic local update
    setPayload((p) => ({
      ...p,
      items: p.items.map((it) => it.id === item.id ? { ...it, [field]: newValue } : it),
    }))
    flashSave(item.id, 'saving')

    try {
      const updated = await api.mtoMtsEditItem(item.id, { [field]: newValue, ...extras })
      setPayload((p) => ({
        ...p,
        items: p.items.map((it) => it.id === item.id ? updated : it),
      }))
      flashSave(item.id, 'saved')
    } catch (err) {
      // revert
      setPayload((p) => ({
        ...p,
        items: p.items.map((it) => it.id === item.id ? { ...it, [field]: oldValue } : it),
      }))
      flashSave(item.id, 'error')
      window.alert(`Could not save: ${err.message}`)
    }
  }

  // Change instruction 8 — when the current-month status flips, ask the
  // reviewer for a short reason at the moment of change. The reason lands
  // on the MtoMtsChange row (so it shows up in the log's "Comment" column)
  // and gets carried in the notification email + toast.
  async function handleCurrentMonthChange(item, newValue) {
    const oldShown = item.current_month_status || itemSheetValue(item) || '—'
    const reason = window.prompt(
      `Change ${item.item_code}\n` +
      `Current-month status: ${oldShown}  →  ${newValue || '—'}\n\n` +
      `Please add a short reason for this change (optional):`,
      ''
    )
    if (reason === null) return   // user hit Cancel — leave the value as-is
    await patchField(item, 'current_month_status', newValue, { comment: reason })
  }

  // Pluck the sheet's own value at the current-month column for a given item.
  // Used when we need to show the "before" value or the fallback when
  // current_month_status is blank.
  function itemSheetValue(item) {
    // The current-month index is computed once at render time (see the IIFE
    // below); we stash it on window so this helper can read it without
    // threading it through every call.
    const idx = window.__mtoCurrentMonthIndex
    if (idx == null) return ''
    const cell = item.cells?.[idx]
    return cell?.value || ''
  }

  return (
    <section className="screen">
      <TopBar subtitle="MTO / MTS Monthly Status" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          {user?.department === 'OEM Sales'
            ? <Link to="/oem-sales">OEM Sales</Link>
            : <Link to="/operations">Operations</Link>} ›{' '}
          MTO / MTS
        </div>
        <button className="backbtn" onClick={() => navigate(-1)}>← Back</button>

        <div className="panel">
          <div className="page-head">
            <div style={{ flex: 1, minWidth: 0 }}>
              <h3>MTO / MTS Monthly Status</h3>
              {payload && payload.upload ? (
                <div className={`upload-banner ${currentMonthMissing ? 'upload-banner-stale' : ''}`}>
                  {currentMonthMissing && (
                    <div className="upload-banner-alert">
                      📭 Operations has not yet uploaded the current month's file.
                      Showing the most recent available data below.
                    </div>
                  )}
                  <div className="upload-banner-line1">
                    📄 <b>{payload.upload.original_filename}</b>
                    {' — '}
                    uploaded <b>{new Date(payload.upload.uploaded_at).toLocaleString()}</b>
                    {' '}by <b>{payload.upload.uploader_username}</b>
                    {payload.upload.month_label && (
                      <> · month <b>{payload.upload.month_label}</b></>
                    )}
                  </div>
                  {!isReadOnly && (
                    <div className="upload-banner-cta">
                      📝 Please validate this. Changes save automatically — there is no Save button.
                    </div>
                  )}
                  {isLocked && (
                    <div className="upload-banner-alert" style={{ background: '#eceff1', borderColor: '#455a64' }}>
                      🔒 Final file post changes is as below. This cycle is closed — no further edits.
                    </div>
                  )}

                  {uploads.length > 0 && (
                    <div className="month-picker">
                      <label htmlFor="month-picker">📅 View another month:</label>
                      <select
                        id="month-picker"
                        value={selectedUploadId || ''}
                        onChange={(e) => selectUpload(Number(e.target.value))}
                      >
                        {uploads.map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.month_label || `Upload #${u.id}`}
                            {' — '}{new Date(u.uploaded_at).toLocaleDateString()}
                            {' ('}{u.status}{')'}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
              ) : (
                <p className="note" style={{ margin: 0 }}>No file uploaded yet.</p>
              )}
            </div>
            <Link className="btn-upload" to="/mto-mts/changes" style={{ background: 'var(--steel)' }}>
              📜 Change Log
            </Link>
          </div>

          {canUpload && (
            <div style={{ marginTop: 18, padding: 14, borderRadius: 8, background: '#eaf3fb',
                          border: '1px dashed var(--accent)' }}>
              <b>Operations upload:</b>{' '}
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xlsm"
                disabled={uploading || isProcessing}
                onChange={(e) => handleUpload(e.target.files?.[0])}
              />
              {' '}<span className="note" style={{ marginLeft: 8 }}>
                (Any previous upload becomes read-only; the new one is the active working file.)
              </span>
              {uploadMsg && (
                <div className={`upload-status ${uploadMsg.kind}`} style={{ marginTop: 10 }}>
                  {uploadMsg.text}
                </div>
              )}
            </div>
          )}

          {!canUpload && (
            <div className="upload-status loading" style={{ marginTop: 14 }}>
              🔒 Only <b>Operations</b> can upload the monthly xlsx.
              OEM Sales sees the file after Operations publishes it and can
              review it in the table below — no upload control on this side.
            </div>
          )}

          {isProcessing && (
            <div className="upload-status loading" style={{ marginTop: 14 }}>
              <span className="spinner" />
              Parsing the uploaded file in the background — this page will refresh
              automatically when it's ready (usually a couple of seconds).
            </div>
          )}
          {isFailed && (
            <div className="upload-status error" style={{ marginTop: 14 }}>
              ❌ The last upload could not be parsed.{' '}
              {canUpload
                ? 'Check the warnings below, fix the file, and re-upload.'
                : 'Ask Operations to check the file.'}
              {payload.upload.validation_notes && (
                <pre style={{ whiteSpace: 'pre-wrap', marginTop: 8, fontSize: 12 }}>
                  {payload.upload.validation_notes}
                </pre>
              )}
            </div>
          )}

          {loading && <div className="loading">Loading current MTO/MTS file…</div>}
          {loadError && <div className="login-error">{loadError}</div>}

          {!loading && !loadError && !payload && (
            <div className="empty-file-notice">
              <div className="empty-file-notice-title">
                📭 Operations has not yet uploaded the file.
              </div>
              <p className="note" style={{ marginTop: 6 }}>
                {canUpload
                  ? 'Use the upload box above to publish the first one.'
                  : 'When Operations publishes the monthly working file, it will appear here for review.'}
              </p>
            </div>
          )}

          {payload && payload.items.length > 0 && (() => {
            // Category dropdown — driven by the "Revised Segment" column
            // (which the V2 template gives us as 4 broad buckets: OEM,
            // After Marekt, Export, Jayaswal). Fallback: any segment values
            // present are surfaced verbatim so future template tweaks work
            // without a code change. Biggest bucket appears first.
            const categoryCounts = new Map()
            for (const it of payload.items) {
              if (!it.segment) continue
              categoryCounts.set(
                it.segment,
                (categoryCounts.get(it.segment) || 0) + 1,
              )
            }
            const availableCategories = [...categoryCounts.entries()]
              .sort((a, b) => b[1] - a[1])

            const visibleItems = payload.items.filter((i) => {
              if (accountFilter && i.segment !== accountFilter) return false
              return true
            })
            // The editable column is the LAST month that already has data in
            // the uploaded sheet — Aug 2026 in the sample file, since Sep
            // onwards is blank. Reviewers edit right in that cell; the sheet's
            // value shows as the default and any change is treated as an
            // override for the current month. Earlier months and later blank
            // months stay read-only.
            let currentMonthIndex = -1
            for (const item of payload.items) {
              for (let i = item.cells.length - 1; i >= 0; i--) {
                if (item.cells[i].value) {
                  if (i > currentMonthIndex) currentMonthIndex = i
                  break
                }
              }
            }
            if (currentMonthIndex === -1) {
              currentMonthIndex = (payload.items[0]?.cells.length || 1) - 1
            }
            const currentMonthLabel = payload.month_labels[currentMonthIndex] || ''
            // Stashed for helpers outside the render IIFE (e.g. the reason-
            // prompt helper needs the sheet's original value at this cell).
            window.__mtoCurrentMonthIndex = currentMonthIndex

            return (
              <>
              {availableCategories.length > 0 && (
                <div className="filter-row">
                  <div className="filter-block">
                    <label htmlFor="account-filter" className="filter-label">
                      Category:
                    </label>
                    <select
                      id="account-filter"
                      className="account-select"
                      value={accountFilter}
                      onChange={(e) => setAccountFilter(e.target.value)}
                    >
                      <option value="">All categories ({payload.items.length})</option>
                      {availableCategories.map(([cat, count]) => (
                        <option key={cat} value={cat}>{cat} ({count})</option>
                      ))}
                    </select>
                    {accountFilter && (
                      <button
                        type="button"
                        className="filter-clear"
                        onClick={() => setAccountFilter('')}
                        title="Clear category filter"
                      >
                        ×
                      </button>
                    )}
                  </div>
                  {accountFilter && (
                    <div className="filter-summary">
                      showing <b>{visibleItems.length}</b> of {payload.items.length}
                    </div>
                  )}
                </div>
              )}
              <div className="mto-table-scroll">
                <table className="mto-table">
                  <thead>
                    <tr>
                      <th className="sticky-col">Item Group</th>
                      <th className="sticky-col2">Item Code</th>
                      <th>System Suggested</th>
                      <th>Trend</th>
                      {payload.month_labels.map((label, idx) => (
                        <th
                          key={label}
                          className={`month-col ${idx === currentMonthIndex ? 'current-month-col' : ''}`}
                        >
                          {label}
                          {idx === currentMonthIndex && <div className="current-month-badge">EDIT HERE</div>}
                        </th>
                      ))}
                      <th>Sales Reason</th>
                      <th>Ops Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleItems.map((item) => {
                      const flash = savingIds[item.id]
                      return (
                        <tr key={item.id} className={flash ? `row-${flash}` : ''}>
                          <td className="sticky-col">{item.item_group}</td>
                          <td className="sticky-col2"><b>{item.item_code}</b></td>
                          <td className="muted">{item.system_suggested || '—'}</td>
                          <td className="muted">{item.trend_tag || '—'}</td>
                          {item.cells.map((c) => {
                            if (c.month_index === currentMonthIndex) {
                              // Editable current-month cell. Default is the
                              // sheet's own value; if the user overrides,
                              // current_month_status is written. On any real
                              // change we ask for a short reason (Change 8)
                              // and colour the cell + append (S) or (O) so
                              // both teams see at a glance who edited what
                              // (Changes 11 + 12).
                              const shown = item.current_month_status || c.value || ''
                              const dept = item.last_edited_by_dept || ''
                              const deptTag =
                                dept === 'OEM Sales' ? 'S' :
                                dept === 'Operations' ? 'O' : ''
                              const deptClass =
                                dept === 'OEM Sales' ? 'edited-sales' :
                                dept === 'Operations' ? 'edited-ops' : ''
                              return (
                                <td
                                  key={c.month_index}
                                  className={`cell-editable ${deptClass}`}
                                  title={dept ? `Last edited by ${dept}` : ''}
                                >
                                  <select
                                    className={`cell-select ${shown ? `is-${shown.toLowerCase()}` : ''}`}
                                    value={shown}
                                    disabled={isReadOnly}
                                    onChange={(e) => handleCurrentMonthChange(item, e.target.value)}
                                  >
                                    {STATUS_OPTIONS.map((o) => <option key={o} value={o}>{o || '—'}</option>)}
                                  </select>
                                  {deptTag && (
                                    <span className={`dept-tag dept-tag-${deptTag.toLowerCase()}`}>
                                      ({deptTag})
                                    </span>
                                  )}
                                </td>
                              )
                            }
                            return (
                              <td key={c.month_index} className={c.value ? `cell-${c.value.toLowerCase()}` : 'muted'}>
                                {c.value || '·'}
                              </td>
                            )
                          })}
                          <td>
                            <input
                              type="text"
                              className="reason-input"
                              placeholder="Sales note"
                              defaultValue={item.sales_reason || ''}
                              onBlur={(e) => patchField(item, 'sales_reason', e.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              type="text"
                              className="reason-input"
                              placeholder="Ops note"
                              defaultValue={item.ops_reason || ''}
                              onBlur={(e) => patchField(item, 'ops_reason', e.target.value)}
                            />
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                <p className="note" style={{ marginTop: 10 }}>
                  Editable column: <b>{currentMonthLabel || '(current month)'}</b> — the last
                  month with data in the uploaded sheet. Earlier months are read-only. Every
                  change is logged and both departments get notified.
                </p>
              </div>
              </>
            )
          })()}

          {payload && payload.upload.validation_notes && (
            <details style={{ marginTop: 14 }}>
              <summary className="note" style={{ cursor: 'pointer' }}>
                {payload.upload.validation_notes.split('\n').length} parser warning(s) — click to view
              </summary>
              <pre className="note" style={{ background: '#f7f9fc', padding: 10, borderRadius: 6, whiteSpace: 'pre-wrap' }}>
                {payload.upload.validation_notes}
              </pre>
            </details>
          )}
        </div>
      </div>
    </section>
  )
}
