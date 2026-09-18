const API_BASE = '/api'

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'))
  return match ? decodeURIComponent(match[1]) : null
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request(path, { method = 'GET', body, formData } = {}) {
  const headers = {}
  // JSON bodies get Content-Type; multipart bodies (formData) MUST NOT — the
  // browser sets its own boundary header.
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  // Django rejects unsafe methods without a matching CSRF header. The token
  // comes from the cookie that /auth/csrf/ sets on app start.
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const token = getCookie('csrftoken')
    if (token) headers['X-CSRFToken'] = token
  }

  let payload
  if (formData !== undefined) payload = formData
  else if (body !== undefined) payload = JSON.stringify(body)

  const response = await fetch(API_BASE + path, {
    method,
    headers,
    credentials: 'same-origin',
    body: payload,
  })

  // A 500 renders Django's HTML debug page, not JSON — parsing defensively
  // keeps that surfacing as a readable error instead of a SyntaxError.
  const raw = await response.text()
  let data = null
  if (raw) {
    try {
      data = JSON.parse(raw)
    } catch {
      data = null
    }
  }

  if (!response.ok) {
    // DRF returns {"detail": "..."} for permission/auth errors, but field-level
    // validation errors come as {"field": ["msg", ...], ...}.  Flatten both into
    // a single readable string.
    let message = ''
    if (data) {
      if (typeof data.detail === 'string') {
        message = data.detail
      } else if (typeof data === 'object') {
        const parts = []
        for (const [key, val] of Object.entries(data)) {
          const msgs = Array.isArray(val) ? val.join(', ') : String(val)
          parts.push(key === 'non_field_errors' ? msgs : `${key}: ${msgs}`)
        }
        message = parts.join(' · ')
      }
    }
    throw new ApiError(message || `Request failed (${response.status})`, response.status)
  }
  return data
}

export const api = {
  ensureCsrf: () => request('/auth/csrf/'),
  login: (username, password) => request('/auth/login/', { method: 'POST', body: { username, password } }),
  logout: () => request('/auth/logout/', { method: 'POST' }),
  me: () => request('/auth/me/'),
  departments: () => request('/departments/'),
  purchasePortals: () => request('/purchase/portals/'),
  rawMaterials: () => request('/purchase/raw-materials/'),
  ebq: ({ annualDemand, orderingCost, holdingCost }) =>
    request('/purchase/ebq/', {
      method: 'POST',
      body: {
        annual_demand: annualDemand,
        ordering_cost: orderingCost,
        holding_cost: holdingCost,
      },
    }),
  // ---------------- MTO / MTS ----------------
  mtoMtsCurrent: () => request('/mto-mts/uploads/current/'),
  mtoMtsUploads: () => request('/mto-mts/uploads/'),
  mtoMtsUploadDetail: (uploadId) => request(`/mto-mts/uploads/${uploadId}/`),
  mtoMtsUpload: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/mto-mts/uploads/new/', { method: 'POST', formData: form })
  },
  mtoMtsEditItem: (itemId, patch) =>
    request(`/mto-mts/items/${itemId}/`, { method: 'PATCH', body: patch }),
  mtoMtsChanges: () => request('/mto-mts/changes/'),
  mtoMtsNotifications: () => request('/mto-mts/notifications/'),
  mtoMtsMarkNotificationsSeen: () =>
    request('/mto-mts/notifications/mark-seen/', { method: 'POST' }),

  // ---------------- PPC Forecast (S&OP) ----------------
  ppcForecastUploads: () => request('/ppc-forecast/uploads/'),
  ppcForecastUpload: (file, notes) => {
    const form = new FormData()
    form.append('file', file)
    if (notes) form.append('notes', notes)
    return request('/ppc-forecast/uploads/new/', { method: 'POST', formData: form })
  },

  // ---------------- Purchase Planning ----------------
  purchasePlanningUploads: () => request('/purchase-planning/uploads/'),
  purchasePlanningUpload: (file, notes) => {
    const form = new FormData()
    form.append('file', file)
    if (notes) form.append('notes', notes)
    return request('/purchase-planning/uploads/new/', { method: 'POST', formData: form })
  },

  // ---------------- Purchase Control Dashboards ----------------
  purchaseDashboardsSummary: () => request('/purchase-dashboards/'),
  purchaseDashboardDetail: (key) => request(`/purchase-dashboards/${key}/`),
  purchaseDashboardTileRows: (dashKey, tileKey, limit = 2000) =>
    request(`/purchase-dashboards/${dashKey}/tiles/${tileKey}/?limit=${limit}`),

  // ---------------- PPC (Production Planning & Control) ----------------
  ppcUploads: () => request('/ppc/uploads/'),
  ppcUpload: (file, notes) => {
    const form = new FormData()
    form.append('file', file)
    if (notes) form.append('notes', notes)
    return request('/ppc/uploads/new/', { method: 'POST', formData: form })
  },

  // ---------------- The Seven Purchase Controls ----------------
  purchaseControlsSummary: () => request('/purchase-controls/'),
  purchaseControlTileRows: (controlKey, tileKey, limit = 2000) =>
    request(`/purchase-controls/${controlKey}/tiles/${tileKey}/?limit=${limit}`),

  // ---------------- PPC Data Pipeline ----------------
  ppcDataUploads: (tableKey) =>
    request(`/ppc-data/uploads/${tableKey ? `?table_key=${tableKey}` : ''}`),
  ppcDataUpload: (file, notes, tableKey) => {
    const form = new FormData()
    form.append('file', file)
    if (notes) form.append('notes', notes)
    if (tableKey) form.append('table_key', tableKey)
    return request('/ppc-data/upload/', { method: 'POST', formData: form })
  },
  ppcDataTable: (tableKey, limit = 200, search = '') =>
    request(`/ppc-data/table/${tableKey}/?limit=${limit}${search ? `&search=${encodeURIComponent(search)}` : ''}`),
  ppcDataFeedStatus: () => request('/ppc-data/feed-status/'),

  // ---------------- PPC Demand Freeze (L2) ----------------
  ppcDemandFreeze: (file, month, notes) => {
    const form = new FormData()
    form.append('file', file)
    form.append('month', month)
    if (notes) form.append('notes', notes)
    return request('/ppc-data/demand/freeze/', { method: 'POST', formData: form })
  },
  ppcDemandTransaction: (file, month, notes) => {
    const form = new FormData()
    form.append('file', file)
    form.append('month', month)
    if (notes) form.append('notes', notes)
    return request('/ppc-data/demand/transaction/', { method: 'POST', formData: form })
  },
  ppcDemandCurrent: (month, limit = 500, search = '') =>
    request(`/ppc-data/demand/current/?month=${month || ''}&limit=${limit}${search ? `&search=${encodeURIComponent(search)}` : ''}`),
  ppcDemandMonths: () => request('/ppc-data/demand/months/'),

  // ---------------- PPC MPS (L3) ----------------
  ppcMpsUpload: (file, tableKey, notes) => {
    const form = new FormData()
    form.append('file', file)
    if (tableKey) form.append('table_key', tableKey)
    if (notes) form.append('notes', notes)
    return request('/ppc-data/mps/upload/', { method: 'POST', formData: form })
  },
  ppcMpsCurrent: (limit = 500, search = '') =>
    request(`/ppc-data/mps/current/?limit=${limit}${search ? `&search=${encodeURIComponent(search)}` : ''}`),
  ppcMpsSummary: () => request('/ppc-data/mps/summary/'),

  // ---------------- PPC R3SS Plan (L4) ----------------
  ppcR3ssUpload: (file, notes) => {
    const form = new FormData()
    form.append('file', file)
    if (notes) form.append('notes', notes)
    return request('/ppc-data/r3ss/upload/', { method: 'POST', formData: form })
  },
  ppcR3ssCurrent: (limit = 500, search = '', fields = '') =>
    request(`/ppc-data/r3ss/current/?limit=${limit}${search ? `&search=${encodeURIComponent(search)}` : ''}${fields ? `&fields=${fields}` : ''}`),
  ppcR3ssFromSheet: (search = '') =>
    request(`/ppc-data/r3ss/from-sheet/${search ? `?search=${encodeURIComponent(search)}` : ''}`),
  ppcR3ssRecomputeSheet: () =>
    request('/ppc-data/r3ss/recompute-sheet/', { method: 'POST', body: {} }),
  ppcR3ssSummary: () => request('/ppc-data/r3ss/summary/'),
  ppcR3ssCompute: (month) =>
    request('/ppc-data/r3ss/compute/', { method: 'POST', body: { month } }),
  ppcR3ssControl: () => request('/ppc-data/r3ss/control/'),
  ppcR3ssDay: (date, section = '', limit = 500) =>
    request(`/ppc-data/r3ss/day/${date}/?limit=${limit}${section ? `&section=${encodeURIComponent(section)}` : ''}`),

  // ---------------- PPC Feasibility (L5) ----------------
  ppcFeasibilityRun: () => request('/ppc-data/feasibility/run/', { method: 'POST' }),
  ppcFeasibilityStatus: (planMonth = '') =>
    request(`/ppc-data/feasibility/status/${planMonth ? `?plan_month=${planMonth}` : ''}`),
  ppcFeasibilityResolve: (flagId, reasonCode, reasonText = '') =>
    request('/ppc-data/feasibility/resolve/', { method: 'POST', body: { flag_id: flagId, reason_code: reasonCode, reason_text: reasonText } }),
  ppcFeasibilityApprove: (runId) =>
    request('/ppc-data/feasibility/approve/', { method: 'POST', body: { run_id: runId } }),

  // ---------------- PPC Release (L6) ----------------
  ppcReleaseCreate: (runId) =>
    request('/ppc-data/release/create/', { method: 'POST', body: { run_id: runId } }),
  ppcReleaseList: (planMonth = '') =>
    request(`/ppc-data/release/list/${planMonth ? `?plan_month=${planMonth}` : ''}`),
  ppcReleaseDetail: (releaseId, limit = 500, search = '') =>
    request(`/ppc-data/release/${releaseId}/?limit=${limit}${search ? `&search=${encodeURIComponent(search)}` : ''}`),
  ppcReleaseRecall: (releaseId, reason) =>
    request(`/ppc-data/release/${releaseId}/recall/`, { method: 'POST', body: { reason } }),

  // ---------------- PPC Material (L7) ----------------
  ppcMaterialExplode: (releaseId) =>
    request('/ppc-data/material/explode/', { method: 'POST', body: { release_id: releaseId } }),
  ppcMaterialAllocate: (releaseId) =>
    request('/ppc-data/material/allocate/', { method: 'POST', body: { release_id: releaseId } }),
  ppcMaterialStatus: (releaseId = '') =>
    request(`/ppc-data/material/status/${releaseId ? `?release_id=${releaseId}` : ''}`),
  ppcMaterialShortages: (releaseId = '', type = '', limit = 500, search = '') =>
    request(`/ppc-data/material/shortages/?limit=${limit}${releaseId ? `&release_id=${releaseId}` : ''}${type ? `&type=${type}` : ''}${search ? `&search=${encodeURIComponent(search)}` : ''}`),
  ppcMaterialSheetSync: (releaseId = '') =>
    request('/ppc-data/material/sheet-sync/', { method: 'POST', body: releaseId ? { release_id: releaseId } : {} }),

  // ---------------- PPC Production (L8) ----------------
  ppcProductionEntry: (data) =>
    request('/ppc-data/production/entry/', { method: 'POST', body: data }),
  ppcProductionBulk: (entries) =>
    request('/ppc-data/production/bulk/', { method: 'POST', body: { entries } }),
  ppcProductionEntries: (params = {}) => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) { if (v) qs.append(k, v) }
    return request(`/ppc-data/production/entries/?${qs}`)
  },
  ppcAdherence: (params = {}) => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) { if (v) qs.append(k, v) }
    return request(`/ppc-data/production/adherence/?${qs}`)
  },
  ppcRejectionEntry: (data) =>
    request('/ppc-data/production/rejection/', { method: 'POST', body: data }),
  ppcRejections: (params = {}) => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) { if (v) qs.append(k, v) }
    return request(`/ppc-data/production/rejections/?${qs}`)
  },
  ppcScorecard: (planMonth = '') =>
    request(`/ppc-data/production/scorecard/${planMonth ? `?plan_month=${planMonth}` : ''}`),

  // ---------------- S&OP Module ----------------
  sopDemandSupply: (month = '') =>
    request(`/sop/demand-supply/${month ? `?month=${month}` : ''}`),
  sopRefresh: () =>
    request('/sop/refresh/', { method: 'POST' }),
  sopUpload: (file, tableKey, notes) => {
    const form = new FormData()
    form.append('file', file)
    if (tableKey) form.append('table_key', tableKey)
    if (notes) form.append('notes', notes)
    return request('/sop/upload/', { method: 'POST', formData: form })
  },
  sopUploads: (tableKey) =>
    request(`/sop/uploads/${tableKey ? `?table_key=${tableKey}` : ''}`),
  sopTableData: (tableKey, limit = 200, search = '') =>
    request(`/sop/data/${tableKey}/?limit=${limit}${search ? `&search=${encodeURIComponent(search)}` : ''}`),
  sopSnapshots: () =>
    request('/sop/snapshots/'),
  sopDashboardExcelUrl: (month = '') =>
    `/api/sop/dashboard-excel/${month ? `?month=${month}` : ''}`,
  // Append1 is computed by Apps Script — triggered by n8n after each source sync.

  // ---------------- Super Admin Panel ----------------
  adminStats: () => request('/admin-panel/stats/'),
  adminModules: () => request('/admin-panel/modules/'),
  adminUsers: () => request('/admin-panel/users/'),
  adminUserCreate: (data) => request('/admin-panel/users/', { method: 'POST', body: data }),
  adminUserDetail: (id) => request(`/admin-panel/users/${id}/`),
  adminUserUpdate: (id, data) => request(`/admin-panel/users/${id}/`, { method: 'PUT', body: data }),
  adminUserToggle: (id) => request(`/admin-panel/users/${id}/toggle/`, { method: 'POST' }),
  adminActivity: (user = '') =>
    request(`/admin-panel/activity/${user ? `?user=${encodeURIComponent(user)}` : ''}`),
}
