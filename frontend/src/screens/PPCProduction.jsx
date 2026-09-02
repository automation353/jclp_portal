import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

/**
 * Screen 6d — L8 Production Entry, Adherence & Scorecard
 *
 * Features:
 *   - Daily production entry (item × date × section × shift)
 *   - Rejection entry with reason codes
 *   - Adherence view (plan vs actual by section / date / item)
 *   - PPC scorecard summary
 */
export default function PPCProduction() {
  const navigate = useNavigate()

  // Tabs
  const TABS = ['scorecard', 'entry', 'adherence', 'rejections']
  const TAB_LABELS = { scorecard: '📊 Scorecard', entry: '✏️ Production Entry', adherence: '📈 Adherence', rejections: '❌ Rejections' }
  const [tab, setTab] = useState('scorecard')

  // Scorecard
  const [scorecard, setScorecard] = useState(null)
  const [loadingScore, setLoadingScore] = useState(true)

  // Entry form
  const [entryForm, setEntryForm] = useState({ date: new Date().toISOString().slice(0, 10), item_code: '', section: '', produced_qty: '', shift: 'general', notes: '' })
  const [saving, setSaving] = useState(false)
  const [entryResult, setEntryResult] = useState(null)
  const [entryError, setEntryError] = useState('')

  // Entries list
  const [entries, setEntries] = useState(null)
  const [entriesFilter, setEntriesFilter] = useState({ date: new Date().toISOString().slice(0, 10) })
  const [loadingEntries, setLoadingEntries] = useState(false)

  // Adherence
  const [adherence, setAdherence] = useState(null)
  const [adhGroupBy, setAdhGroupBy] = useState('section')
  const [loadingAdh, setLoadingAdh] = useState(false)

  // Rejections
  const [rejForm, setRejForm] = useState({ date: new Date().toISOString().slice(0, 10), item_code: '', section: '', stage: '', rejected_qty: '', reason_code: '', reason_text: '' })
  const [rejSaving, setRejSaving] = useState(false)
  const [rejections, setRejections] = useState(null)
  const [loadingRej, setLoadingRej] = useState(false)

  function fetchScorecard() {
    setLoadingScore(true)
    api.ppcScorecard()
      .then(d => setScorecard(d))
      .catch(() => {})
      .finally(() => setLoadingScore(false))
  }

  function fetchEntries() {
    setLoadingEntries(true)
    api.ppcProductionEntries(entriesFilter)
      .then(d => setEntries(d))
      .catch(() => {})
      .finally(() => setLoadingEntries(false))
  }

  function fetchAdherence() {
    setLoadingAdh(true)
    api.ppcAdherence({ group_by: adhGroupBy })
      .then(d => setAdherence(d))
      .catch(() => {})
      .finally(() => setLoadingAdh(false))
  }

  function fetchRejections() {
    setLoadingRej(true)
    api.ppcRejections({ limit: '200' })
      .then(d => setRejections(d))
      .catch(() => {})
      .finally(() => setLoadingRej(false))
  }

  useEffect(() => { fetchScorecard() }, [])
  useEffect(() => { if (tab === 'adherence') fetchAdherence() }, [tab, adhGroupBy])
  useEffect(() => { if (tab === 'entry') fetchEntries() }, [tab])
  useEffect(() => { if (tab === 'rejections') fetchRejections() }, [tab])

  async function handleEntry(e) {
    e.preventDefault()
    setSaving(true); setEntryError(''); setEntryResult(null)
    try {
      const res = await api.ppcProductionEntry(entryForm)
      setEntryResult(res)
      setEntryForm(f => ({ ...f, item_code: '', produced_qty: '', notes: '' }))
      fetchEntries()
      fetchScorecard()
    } catch (err) {
      setEntryError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleRejection(e) {
    e.preventDefault()
    setRejSaving(true); setEntryError('')
    try {
      await api.ppcRejectionEntry(rejForm)
      setRejForm(f => ({ ...f, item_code: '', stage: '', rejected_qty: '', reason_code: '', reason_text: '' }))
      fetchRejections()
      fetchScorecard()
    } catch (err) {
      setEntryError(err.message)
    } finally {
      setRejSaving(false)
    }
  }

  const adh_pct_color = (pct) =>
    pct >= 95 ? 'var(--ok)' : pct >= 80 ? '#f39c12' : 'var(--bad)'

  return (
    <section className="screen">
      <TopBar subtitle="PPC Department" />
      <div className="wrap" style={{ maxWidth: 1000 }}>
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/ppc-data">PPC Data</Link> › Production & Feedback
        </div>
        <button className="backbtn" onClick={() => navigate('/ppc-data')}>← Back to PPC Data</button>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 6, marginBottom: 18 }}>
          {TABS.map(t => (
            <button key={t} onClick={() => setTab(t)}
              style={{
                padding: '8px 16px', borderRadius: 8, fontSize: 13, cursor: 'pointer',
                border: tab === t ? '2px solid var(--accent)' : '1px solid var(--line)',
                background: tab === t ? '#e8f4fd' : '#fff',
                fontWeight: tab === t ? 700 : 400,
              }}>
              {TAB_LABELS[t]}
            </button>
          ))}
        </div>

        {entryError && <div className="upload-status error" style={{ marginBottom: 12 }}>{entryError}</div>}

        {/* ── SCORECARD ── */}
        {tab === 'scorecard' && (
          <>
            {loadingScore && <div className="loading">Loading…</div>}
            {!loadingScore && !scorecard?.loaded && (
              <div className="panel"><p className="note">No active release. Create a release first.</p></div>
            )}
            {!loadingScore && scorecard?.loaded && (
              <>
                <div className="panel">
                  <h3 style={{ marginBottom: 12 }}>
                    PPC Scorecard — {scorecard.plan_month} (Release #{scorecard.release_number})
                  </h3>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: 10, marginBottom: 16 }}>
                    {[
                      { label: 'Planned', value: scorecard.overall.planned.toLocaleString(), color: 'var(--ink)' },
                      { label: 'Actual', value: scorecard.overall.actual.toLocaleString(), color: 'var(--accent)' },
                      { label: 'Adherence', value: `${scorecard.overall.adherence_pct}%`, color: adh_pct_color(scorecard.overall.adherence_pct) },
                      { label: 'Backlog', value: scorecard.overall.backlog.toLocaleString(), color: scorecard.overall.backlog > 0 ? '#e67e22' : 'var(--ok)' },
                      { label: 'Rejected', value: scorecard.overall.rejected.toLocaleString(), color: scorecard.overall.rejected > 0 ? 'var(--bad)' : 'var(--ok)' },
                      { label: 'Rejection %', value: `${scorecard.overall.rejection_pct}%`, color: scorecard.overall.rejection_pct > 2 ? 'var(--bad)' : 'var(--ok)' },
                    ].map(t => (
                      <div key={t.label} style={{ textAlign: 'center', padding: '12px 8px', borderRadius: 8, border: '1px solid var(--line)' }}>
                        <div style={{ fontSize: 22, fontWeight: 700, color: t.color, fontVariantNumeric: 'tabular-nums' }}>{t.value}</div>
                        <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.04em' }}>{t.label}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {scorecard.sections.length > 0 && (
                  <div className="panel">
                    <h3 style={{ marginBottom: 10 }}>Section Breakdown</h3>
                    <table style={{ fontSize: 12, width: '100%' }}>
                      <thead>
                        <tr>
                          <th>Section</th>
                          <th style={{ textAlign: 'right' }}>Planned</th>
                          <th style={{ textAlign: 'right' }}>Actual</th>
                          <th style={{ textAlign: 'right' }}>Adherence</th>
                          <th style={{ textAlign: 'right' }}>Gap</th>
                          <th>Bar</th>
                        </tr>
                      </thead>
                      <tbody>
                        {scorecard.sections.map(s => (
                          <tr key={s.section}>
                            <td style={{ fontWeight: 700 }}>{s.section}</td>
                            <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{s.planned.toLocaleString()}</td>
                            <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{s.actual.toLocaleString()}</td>
                            <td style={{ textAlign: 'right', fontWeight: 700, color: adh_pct_color(s.adherence_pct), fontVariantNumeric: 'tabular-nums' }}>
                              {s.adherence_pct}%
                            </td>
                            <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: s.gap > 0 ? '#e67e22' : 'var(--ok)' }}>
                              {s.gap.toLocaleString()}
                            </td>
                            <td style={{ width: 120 }}>
                              <div style={{ background: '#eee', borderRadius: 4, height: 14, overflow: 'hidden' }}>
                                <div style={{
                                  width: `${Math.min(100, s.adherence_pct)}%`,
                                  height: '100%',
                                  background: adh_pct_color(s.adherence_pct),
                                  borderRadius: 4,
                                  transition: 'width .3s',
                                }} />
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {/* ── PRODUCTION ENTRY ── */}
        {tab === 'entry' && (
          <>
            <div className="panel">
              <h3 style={{ marginBottom: 12 }}>Daily Production Entry</h3>
              <form onSubmit={handleEntry}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10, marginBottom: 12 }}>
                  <label style={{ fontSize: 12, fontWeight: 600 }}>
                    Date *
                    <input type="date" value={entryForm.date} onChange={e => setEntryForm(f => ({ ...f, date: e.target.value }))}
                      style={{ display: 'block', width: '100%', marginTop: 4, padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }} />
                  </label>
                  <label style={{ fontSize: 12, fontWeight: 600 }}>
                    Item Code *
                    <input type="text" value={entryForm.item_code} onChange={e => setEntryForm(f => ({ ...f, item_code: e.target.value }))}
                      placeholder="JC-001" style={{ display: 'block', width: '100%', marginTop: 4, padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }} />
                  </label>
                  <label style={{ fontSize: 12, fontWeight: 600 }}>
                    Section *
                    <input type="text" value={entryForm.section} onChange={e => setEntryForm(f => ({ ...f, section: e.target.value }))}
                      placeholder="SSWD" style={{ display: 'block', width: '100%', marginTop: 4, padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }} />
                  </label>
                  <label style={{ fontSize: 12, fontWeight: 600 }}>
                    Produced Qty *
                    <input type="number" value={entryForm.produced_qty} onChange={e => setEntryForm(f => ({ ...f, produced_qty: e.target.value }))}
                      placeholder="0" style={{ display: 'block', width: '100%', marginTop: 4, padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }} />
                  </label>
                  <label style={{ fontSize: 12, fontWeight: 600 }}>
                    Shift
                    <select value={entryForm.shift} onChange={e => setEntryForm(f => ({ ...f, shift: e.target.value }))}
                      style={{ display: 'block', width: '100%', marginTop: 4, padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }}>
                      <option value="general">General</option>
                      <option value="day">Day</option>
                      <option value="night">Night</option>
                    </select>
                  </label>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'end' }}>
                  <input type="text" value={entryForm.notes} onChange={e => setEntryForm(f => ({ ...f, notes: e.target.value }))}
                    placeholder="Notes (optional)" style={{ flex: 1, padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }} />
                  <button type="submit" className="btn-upload" disabled={saving}
                    style={{ padding: '8px 18px', fontSize: 13, whiteSpace: 'nowrap' }}>
                    {saving ? 'Saving…' : '💾 Save Entry'}
                  </button>
                </div>
              </form>
              {entryResult && (
                <div className="upload-status ok" style={{ marginTop: 10 }}>
                  ✅ {entryResult.created ? 'Created' : 'Updated'} — {entryResult.item_code} on {entryResult.date}: {entryResult.produced_qty} pcs
                </div>
              )}
            </div>

            {/* Today's entries */}
            <div className="panel">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <h3 style={{ margin: 0 }}>Entries for</h3>
                <input type="date" value={entriesFilter.date || ''} onChange={e => setEntriesFilter({ date: e.target.value })}
                  style={{ padding: '4px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }} />
                <button onClick={fetchEntries} className="btn-upload" style={{ padding: '5px 12px', fontSize: 12 }}>Refresh</button>
              </div>
              {loadingEntries && <div className="loading">Loading…</div>}
              {!loadingEntries && entries?.entries?.length === 0 && (
                <p className="note">No entries for this date.</p>
              )}
              {!loadingEntries && entries?.entries?.length > 0 && (
                <table style={{ fontSize: 12, width: '100%' }}>
                  <thead>
                    <tr><th>Item</th><th>Section</th><th>Shift</th><th style={{ textAlign: 'right' }}>Qty</th><th>By</th><th>Notes</th></tr>
                  </thead>
                  <tbody>
                    {entries.entries.map(e => (
                      <tr key={e.id}>
                        <td style={{ fontFamily: 'monospace', fontWeight: 600 }}>{e.item_code}</td>
                        <td>{e.section}</td>
                        <td>{e.shift}</td>
                        <td style={{ textAlign: 'right', fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{e.produced_qty.toLocaleString()}</td>
                        <td style={{ fontSize: 11, color: 'var(--muted)' }}>{e.entered_by}</td>
                        <td style={{ fontSize: 11, color: 'var(--muted)', maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.notes || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}

        {/* ── ADHERENCE ── */}
        {tab === 'adherence' && (
          <div className="panel">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>Plan vs Actual Adherence</h3>
              <div style={{ display: 'flex', gap: 6 }}>
                {['section', 'date', 'item'].map(g => (
                  <button key={g} onClick={() => setAdhGroupBy(g)}
                    style={{
                      padding: '5px 12px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
                      border: adhGroupBy === g ? '2px solid var(--accent)' : '1px solid var(--line)',
                      background: adhGroupBy === g ? '#e8f4fd' : '#fff',
                      fontWeight: adhGroupBy === g ? 700 : 400,
                    }}>
                    By {g}
                  </button>
                ))}
              </div>
            </div>

            {loadingAdh && <div className="loading">Loading…</div>}

            {!loadingAdh && adherence && (
              <>
                <div style={{
                  padding: '10px 16px', marginBottom: 12, borderRadius: 6,
                  background: adh_pct_color(adherence.overall.adherence_pct) + '15',
                  borderLeft: `4px solid ${adh_pct_color(adherence.overall.adherence_pct)}`,
                }}>
                  <span style={{ fontWeight: 700, fontSize: 18, color: adh_pct_color(adherence.overall.adherence_pct) }}>
                    {adherence.overall.adherence_pct}%
                  </span>
                  <span style={{ fontSize: 13, color: 'var(--muted)', marginLeft: 12 }}>
                    overall adherence · {adherence.overall.actual.toLocaleString()} of {adherence.overall.planned.toLocaleString()} planned
                  </span>
                </div>

                {adherence.rows.length > 0 && (
                  <div className="table-scroll" style={{ maxHeight: '50vh', overflowY: 'auto' }}>
                    <table style={{ fontSize: 12 }}>
                      <thead>
                        <tr>
                          <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>
                            {adhGroupBy === 'section' ? 'Section' : adhGroupBy === 'date' ? 'Date' : 'Item'}
                          </th>
                          <th style={{ position: 'sticky', top: 0, background: '#f0f4f8', textAlign: 'right' }}>Planned</th>
                          <th style={{ position: 'sticky', top: 0, background: '#f0f4f8', textAlign: 'right' }}>Actual</th>
                          <th style={{ position: 'sticky', top: 0, background: '#f0f4f8', textAlign: 'right' }}>Adherence</th>
                          <th style={{ position: 'sticky', top: 0, background: '#f0f4f8', textAlign: 'right' }}>Gap</th>
                          <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>Bar</th>
                        </tr>
                      </thead>
                      <tbody>
                        {adherence.rows.map((r, i) => (
                          <tr key={i}>
                            <td style={{ fontWeight: 600 }}>{r.section || r.date || r.item_code}</td>
                            <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{r.planned.toLocaleString()}</td>
                            <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{r.actual.toLocaleString()}</td>
                            <td style={{ textAlign: 'right', fontWeight: 700, color: adh_pct_color(r.adherence_pct), fontVariantNumeric: 'tabular-nums' }}>
                              {r.adherence_pct}%
                            </td>
                            <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: r.gap > 0 ? '#e67e22' : 'var(--ok)' }}>
                              {r.gap.toLocaleString()}
                            </td>
                            <td style={{ width: 100 }}>
                              <div style={{ background: '#eee', borderRadius: 4, height: 12, overflow: 'hidden' }}>
                                <div style={{
                                  width: `${Math.min(100, r.adherence_pct)}%`, height: '100%',
                                  background: adh_pct_color(r.adherence_pct), borderRadius: 4,
                                }} />
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ── REJECTIONS ── */}
        {tab === 'rejections' && (
          <>
            <div className="panel">
              <h3 style={{ marginBottom: 12 }}>Rejection Entry</h3>
              <form onSubmit={handleRejection}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10, marginBottom: 12 }}>
                  <label style={{ fontSize: 12, fontWeight: 600 }}>
                    Date *
                    <input type="date" value={rejForm.date} onChange={e => setRejForm(f => ({ ...f, date: e.target.value }))}
                      style={{ display: 'block', width: '100%', marginTop: 4, padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }} />
                  </label>
                  <label style={{ fontSize: 12, fontWeight: 600 }}>
                    Item Code *
                    <input type="text" value={rejForm.item_code} onChange={e => setRejForm(f => ({ ...f, item_code: e.target.value }))}
                      style={{ display: 'block', width: '100%', marginTop: 4, padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }} />
                  </label>
                  <label style={{ fontSize: 12, fontWeight: 600 }}>
                    Section *
                    <input type="text" value={rejForm.section} onChange={e => setRejForm(f => ({ ...f, section: e.target.value }))}
                      style={{ display: 'block', width: '100%', marginTop: 4, padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }} />
                  </label>
                  <label style={{ fontSize: 12, fontWeight: 600 }}>
                    Stage *
                    <input type="text" value={rejForm.stage} onChange={e => setRejForm(f => ({ ...f, stage: e.target.value }))}
                      placeholder="e.g. Welding" style={{ display: 'block', width: '100%', marginTop: 4, padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }} />
                  </label>
                  <label style={{ fontSize: 12, fontWeight: 600 }}>
                    Rejected Qty *
                    <input type="number" value={rejForm.rejected_qty} onChange={e => setRejForm(f => ({ ...f, rejected_qty: e.target.value }))}
                      style={{ display: 'block', width: '100%', marginTop: 4, padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }} />
                  </label>
                  <label style={{ fontSize: 12, fontWeight: 600 }}>
                    Reason Code *
                    <select value={rejForm.reason_code} onChange={e => setRejForm(f => ({ ...f, reason_code: e.target.value }))}
                      style={{ display: 'block', width: '100%', marginTop: 4, padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }}>
                      <option value="">Select…</option>
                      <option value="material_defect">Material defect</option>
                      <option value="machine_error">Machine error</option>
                      <option value="tool_wear">Tool wear</option>
                      <option value="operator_error">Operator error</option>
                      <option value="design_issue">Design / drawing issue</option>
                      <option value="quality_spec">Quality spec failure</option>
                      <option value="other">Other</option>
                    </select>
                  </label>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'end' }}>
                  <input type="text" value={rejForm.reason_text} onChange={e => setRejForm(f => ({ ...f, reason_text: e.target.value }))}
                    placeholder="Explanation (optional)" style={{ flex: 1, padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }} />
                  <button type="submit" className="btn-upload" disabled={rejSaving}
                    style={{ padding: '8px 18px', fontSize: 13, background: '#c0392b', borderColor: '#c0392b', whiteSpace: 'nowrap' }}>
                    {rejSaving ? 'Saving…' : '❌ Log Rejection'}
                  </button>
                </div>
              </form>
            </div>

            <div className="panel">
              <h3 style={{ marginBottom: 10 }}>Recent Rejections</h3>
              {loadingRej && <div className="loading">Loading…</div>}
              {!loadingRej && rejections?.entries?.length === 0 && (
                <p className="note">No rejections recorded yet.</p>
              )}
              {!loadingRej && rejections?.entries?.length > 0 && (
                <div className="table-scroll" style={{ maxHeight: '40vh', overflowY: 'auto' }}>
                  <table style={{ fontSize: 12 }}>
                    <thead>
                      <tr>
                        <th>Date</th><th>Item</th><th>Section</th><th>Stage</th>
                        <th style={{ textAlign: 'right' }}>Qty</th><th>Reason</th><th>By</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rejections.entries.map(r => (
                        <tr key={r.id}>
                          <td style={{ fontFamily: 'monospace' }}>{r.date}</td>
                          <td style={{ fontWeight: 600 }}>{r.item_code}</td>
                          <td>{r.section}</td>
                          <td>{r.stage}</td>
                          <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--bad)', fontVariantNumeric: 'tabular-nums' }}>{r.rejected_qty}</td>
                          <td>{r.reason_code}{r.reason_text ? ` — ${r.reason_text}` : ''}</td>
                          <td style={{ fontSize: 11, color: 'var(--muted)' }}>{r.entered_by}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  )
}
