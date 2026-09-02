import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

// Lowered from 15 s → 5 s so pop-ups feel responsive when Ops/Sales are
// reviewing the sheet at the same time. Still very cheap in aggregate.
const POLL_MS = 5000
const TOAST_MS = 7000

// Any unread notification less than this old still pops as a toast on the
// very first fetch after sign-in — so a user who logs in seconds after a
// change was made still sees the pop, not just the bell badge.
const FIRST_FETCH_RECENT_MS = 5 * 60 * 1000

const FIELD_LABEL = {
  current_month_status: 'Current month status',
  sales_status: 'Sales status',
  sales_reason: 'Sales reason',
  ops_status: 'Operations status',
  ops_reason: 'Operations reason',
}

function timeAgo(iso) {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

/**
 * Poll-based notification bell for MTO/MTS changes.
 *
 * We use polling rather than WebSockets because the process is monthly-cadence
 * and the operational cost of a 15-second poll is negligible; adding WS would
 * mean daphne/channels for very little gain at Phase 1.
 */
export default function NotificationBell() {
  const [unread, setUnread] = useState(0)
  const [items, setItems] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [toasts, setToasts] = useState([])       // {key, change} entries currently on screen
  const navigate = useNavigate()
  const wrapRef = useRef(null)

  // Track ids we've already surfaced as a toast — refs so we never stale-close
  // over the state inside setInterval.
  const seenIdsRef = useRef(new Set())
  const isFirstFetchRef = useRef(true)
  const seenUploadIdRef = useRef(null)

  function popToast(notif) {
    const key = `change-${notif.id}`
    setToasts((prev) => [...prev, { key, kind: 'change', change: notif.change }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.key !== key))
    }, TOAST_MS)
  }

  function popUploadToast(upload) {
    const key = `upload-${upload.id}`
    setToasts((prev) => [...prev, { key, kind: 'upload', upload }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.key !== key))
    }, TOAST_MS)
  }

  function dismissToast(key) {
    setToasts((prev) => prev.filter((t) => t.key !== key))
  }

  async function fetchOnce() {
    try {
      const data = await api.mtoMtsNotifications()
      setUnread(data.unread_count || 0)
      const list = data.items || []
      setItems(list)

      const latestUpload = data.latest_active_upload || null

      if (isFirstFetchRef.current) {
        // First poll after sign-in: seed the "seen" set so old notifications
        // don't spam the screen, BUT still pop very recent unread ones so a
        // user who joined seconds after a change was made doesn't miss it.
        const now = Date.now()
        for (const n of list) {
          seenIdsRef.current.add(n.id)
          const age = now - new Date(n.created_at).getTime()
          if (!n.seen_at && age >= 0 && age < FIRST_FETCH_RECENT_MS) {
            popToast(n)
          }
        }
        // Same recency rule for the "new upload" toast — anyone who logs in
        // within the FIRST_FETCH_RECENT_MS window after an upload still gets
        // told about it.
        seenUploadIdRef.current = latestUpload ? latestUpload.id : null
        if (latestUpload) {
          const age = now - new Date(latestUpload.uploaded_at).getTime()
          if (age >= 0 && age < FIRST_FETCH_RECENT_MS) popUploadToast(latestUpload)
        }
        isFirstFetchRef.current = false
        return
      }

      // Subsequent polls: anything new since the last one → pop.
      for (const n of list) {
        if (!seenIdsRef.current.has(n.id)) {
          seenIdsRef.current.add(n.id)
          popToast(n)
        }
      }
      // Change instruction 3 — when a fresh upload becomes ACTIVE, notify
      // BOTH teams (including the uploader themselves — they wanted this).
      if (latestUpload && latestUpload.id !== seenUploadIdRef.current) {
        seenUploadIdRef.current = latestUpload.id
        popUploadToast(latestUpload)
      }
    } catch {
      // Silent — the user is likely signed out; the poller picks back up
      // after the next login without spamming the console.
    }
  }

  useEffect(() => {
    fetchOnce()
    const id = setInterval(fetchOnce, POLL_MS)
    return () => clearInterval(id)
  }, [])

  // click-outside closes the dropdown
  useEffect(() => {
    if (!open) return
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  async function toggle() {
    const next = !open
    setOpen(next)
    if (next && unread > 0) {
      setLoading(true)
      try {
        await api.mtoMtsMarkNotificationsSeen()
        setUnread(0)
      } finally {
        setLoading(false)
      }
    }
  }

  function openChange(row) {
    setOpen(false)
    navigate('/mto-mts')
  }

  return (
    <>
      <div className="bell-wrap" ref={wrapRef}>
        <button className="bell-btn" onClick={toggle} title="MTO/MTS notifications">
          🔔
          {unread > 0 && <span className="bell-badge">{unread > 99 ? '99+' : unread}</span>}
        </button>
        {open && (
          <div className="bell-panel">
            <div className="bell-head">
              Recent MTO/MTS changes {loading && <span className="muted">· syncing…</span>}
            </div>
            {items.length === 0 && (
              <div className="bell-empty">No notifications yet.</div>
            )}
            {items.map((n) => {
              const c = n.change
              const label = FIELD_LABEL[c.field] || c.field
              return (
                <button
                  key={n.id}
                  className={`bell-row ${n.seen_at ? '' : 'unseen'}`}
                  onClick={() => openChange(c)}
                >
                  <div className="bell-row-main">
                    <b>{c.item_code}</b>{' '}
                    <span className="muted">— {label} changed</span>{' '}
                    <span className="muted">from</span> <b>{c.old_value || '—'}</b>{' '}
                    <span className="muted">to</span> <b>{c.new_value || '—'}</b>
                  </div>
                  <div className="bell-row-sub">
                    by <b>{c.changed_by_username}</b>
                    {c.department && <span className="muted"> · {c.department}</span>}
                    {' · '}
                    <span className="muted">{timeAgo(c.changed_at)}</span>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Live-pop toasts — one per new notification, stacked bottom-right. */}
      <div className="toast-container">
        {toasts.map((t) => {
          if (t.kind === 'upload') {
            const u = t.upload
            return (
              <div
                key={t.key}
                className="toast toast-upload"
                role="alert"
                onClick={() => { dismissToast(t.key); navigate('/mto-mts') }}
                title="Click to open the MTO / MTS working file"
              >
                <button
                  className="toast-close"
                  aria-label="Dismiss"
                  onClick={(e) => { e.stopPropagation(); dismissToast(t.key) }}
                >×</button>
                <div className="toast-title">📄 New MTO / MTS file published</div>
                <div className="toast-body">
                  <b>{u.original_filename}</b>
                  {u.month_label && <span className="muted"> · {u.month_label}</span>}
                  <div className="toast-meta">
                    uploaded by <b>{u.uploader_username || '—'}</b>
                  </div>
                </div>
                <div className="toast-cta">👉 Click to open the working file</div>
              </div>
            )
          }
          const c = t.change
          const label = FIELD_LABEL[c.field] || c.field
          return (
            <div
              key={t.key}
              className="toast"
              role="alert"
              onClick={() => { dismissToast(t.key); navigate('/mto-mts/changes') }}
              title="Click to open the Change Log"
            >
              <button
                className="toast-close"
                aria-label="Dismiss"
                onClick={(e) => { e.stopPropagation(); dismissToast(t.key) }}
              >×</button>
              <div className="toast-title">🔔 New MTO / MTS change</div>
              <div className="toast-body">
                <b>{c.item_code}</b> <span className="muted">— {label}</span>
                <div className="toast-diff">
                  <span className="muted">{c.old_value || '—'}</span>
                  {' → '}
                  <b>{c.new_value || '—'}</b>
                </div>
                <div className="toast-meta">
                  by <b>{c.changed_by_username}</b>
                  {c.department && <span className="muted"> · {c.department}</span>}
                  {c.comment && <span className="muted"> · “{c.comment}”</span>}
                </div>
              </div>
              <div className="toast-cta">📜 Click to open the Change Log</div>
            </div>
          )
        })}
      </div>
    </>
  )
}
