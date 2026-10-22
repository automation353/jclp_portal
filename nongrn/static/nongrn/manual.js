/* Editable "Manual GRN" sheet. */
(function () {
  const M = window.MANUAL;
  let rows = M.rows.map(r => ({ invoice_no: r.invoice_no, grn_date: r.grn_date, meta: r }));
  let saved = JSON.stringify(rows.map(strip));
  let info = {};
  const tbody = document.querySelector('#manual tbody');
  const inr = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  function strip(r) { return { invoice_no: (r.invoice_no || '').trim(), grn_date: r.grn_date || '' }; }
  function esc(s) { return String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
  function isDirty() { return JSON.stringify(rows.map(strip)) !== saved; }
  function markDirty() { document.getElementById('dirty').classList.toggle('d-none', !isDirty()); }

  function toIso(s) {
    s = String(s || '').trim();
    if (!s) return '';
    let m;
    if ((m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/))) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`;
    if ((m = s.match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})$/))) {
      const y = m[3].length === 2 ? '20' + m[3] : m[3];
      return `${y}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
    }
    if (/^\d{5}(\.\d+)?$/.test(s)) {   // Excel serial
      const d = new Date(Date.UTC(1899, 11, 30) + Math.floor(+s) * 86400000);
      return d.toISOString().slice(0, 10);
    }
    const d = new Date(s);
    return isNaN(d) ? s : d.toISOString().slice(0, 10);
  }

  function ctxCells(inv) {
    const i = info[(inv || '').trim()];
    if (!inv) return '<td colspan="6"></td>';
    if (!i) return '<td colspan="6" class="text-danger small"><i class="bi bi-exclamation-triangle"></i> Invoice not found in Combine</td>';
    const warn = i.erp_grn ? ' <i class="bi bi-info-circle text-warning" title="ERP already has a GRN date – Manual GRN is ignored for this invoice"></i>' : '';
    return `<td>${esc(i.customer)}</td><td>${i.inv_date}</td><td class="text-end">${inr.format(i.amount)}</td>` +
      `<td>${i.erp_grn || ''}${warn}</td><td><span class="src-pill s${(i.source || '')[0]}">${esc(i.source)}</span></td>` +
      `<td class="text-end">${i.current ? inr.format(i.current) : '-'}</td>`;
  }

  function render() {
    const counts = {};
    rows.forEach(r => { const k = (r.invoice_no || '').trim(); if (k) counts[k] = (counts[k] || 0) + 1; });
    tbody.innerHTML = rows.map((r, idx) => {
      const dup = counts[(r.invoice_no || '').trim()] > 1;
      return `<tr data-idx="${idx}">
        <th class="rn">${idx + 2}</th>
        <td class="edit"><input class="form-control form-control-sm inv ${dup ? 'is-invalid' : ''}" value="${esc(r.invoice_no)}" placeholder="e.g. 2627H00123"></td>
        <td class="edit"><input type="date" class="form-control form-control-sm dt" value="${esc(r.grn_date)}"></td>
        ${ctxCells(r.invoice_no)}
        <td><button class="btn btn-sm btn-link text-danger del" title="Delete row"><i class="bi bi-trash"></i></button></td>
      </tr>`;
    }).join('') || '<tr><td colspan="10" class="text-center text-muted py-4">No Manual GRN rows yet – add rows, paste from Excel or pick invoices on the right.</td></tr>';
    markDirty();
  }

  tbody.addEventListener('input', e => {
    const tr = e.target.closest('tr'); if (!tr) return;
    const r = rows[+tr.dataset.idx];
    if (e.target.classList.contains('inv')) r.invoice_no = e.target.value;
    if (e.target.classList.contains('dt')) r.grn_date = e.target.value;
    markDirty();
  });
  tbody.addEventListener('change', e => { if (e.target.classList.contains('inv')) refreshInfo().then(render); });
  tbody.addEventListener('click', e => {
    const b = e.target.closest('.del'); if (!b) return;
    rows.splice(+b.closest('tr').dataset.idx, 1); render();
  });
  // Enter / arrow navigation like a sheet
  tbody.addEventListener('keydown', e => {
    if (!['Enter', 'ArrowDown', 'ArrowUp'].includes(e.key) || e.target.tagName !== 'INPUT') return;
    const td = e.target.closest('td'), tr = td.closest('tr');
    const col = [...tr.children].indexOf(td);
    const target = e.key === 'ArrowUp' ? tr.previousElementSibling : tr.nextElementSibling;
    if (target) { e.preventDefault(); target.children[col]?.querySelector('input')?.focus(); }
    else if (e.key === 'Enter') { e.preventDefault(); addRow(); }
  });

  function addRow(inv = '', date = '') {
    rows.push({ invoice_no: inv, grn_date: date });
    render();
    const last = tbody.querySelector('tr:last-child input.inv');
    if (last && !inv) last.focus();
  }
  document.getElementById('add-row').onclick = () => addRow();

  function mergeRows(newRows, replace) {
    if (replace) rows = [];
    newRows.forEach(n => {
      const inv = (n.invoice_no || '').trim();
      const ex = rows.find(r => (r.invoice_no || '').trim() === inv && inv);
      if (ex) ex.grn_date = toIso(n.grn_date); else rows.push({ invoice_no: inv, grn_date: toIso(n.grn_date) });
    });
    refreshInfo().then(render);
  }

  document.getElementById('paste-apply').onclick = () => {
    const text = document.getElementById('paste-text').value;
    const parsed = text.split(/\r?\n/).map(l => l.split(/\t|,(?=[^,]*$)/)).filter(p => p[0] && p[0].trim())
      .filter(p => !/^invoice/i.test(p[0].trim()))
      .map(p => ({ invoice_no: p[0].trim(), grn_date: (p[1] || '').trim() }));
    mergeRows(parsed, document.getElementById('paste-replace').checked);
    document.getElementById('paste-text').value = '';
  };

  document.getElementById('import-file').addEventListener('change', e => {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    fetch(M.importUrl, { method: 'POST', body: fd, headers: { 'X-CSRFToken': NONGRN.csrf } })
      .then(r => r.json()).then(d => {
        if (!d.ok) return showErrors(d.errors);
        mergeRows(d.rows, false);
      });
    e.target.value = '';
  });

  function showErrors(errs) {
    const box = document.getElementById('errors');
    if (!errs || !errs.length) { box.classList.add('d-none'); return; }
    box.innerHTML = errs.map(esc).join('<br>');
    box.classList.remove('d-none');
  }

  document.getElementById('save').onclick = () => {
    const btn = document.getElementById('save');
    btn.disabled = true;
    fetch(M.api, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': NONGRN.csrf },
      body: JSON.stringify({ rows: rows.map(strip) }),
    }).then(r => r.json()).then(d => {
      btn.disabled = false;
      if (!d.ok) return showErrors(d.errors);
      showErrors([]);
      rows = rows.filter(r => (r.invoice_no || '').trim() || r.grn_date);
      saved = JSON.stringify(rows.map(strip));
      refreshInfo().then(render);
      loadCandidates();
      flash(`Saved ${d.count} row(s). Combine, Report and Dashboard are recalculated.`);
    }).catch(err => { btn.disabled = false; showErrors([String(err)]); });
  };

  document.getElementById('discard').onclick = () => {
    if (!isDirty() || confirm('Discard unsaved changes?')) location.reload();
  };
  window.addEventListener('beforeunload', e => { if (isDirty()) { e.preventDefault(); e.returnValue = ''; } });

  function flash(msg) {
    const el = document.createElement('div');
    el.className = 'toast-msg'; el.textContent = msg;
    document.body.appendChild(el); setTimeout(() => el.remove(), 3500);
  }

  function post(url, body) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': NONGRN.csrf },
      body: JSON.stringify(body) }).then(r => r.json());
  }

  function refreshInfo() {
    const invs = rows.map(r => (r.invoice_no || '').trim()).filter(Boolean);
    return post(M.lookup, { invoices: invs, q: '__none__' }).then(d => { info = d.info || {}; });
  }

  let cq;
  function loadCandidates() {
    const q = document.getElementById('cand-q').value;
    post(M.lookup, { invoices: [], q }).then(d => {
      const list = document.getElementById('cand-list');
      const have = new Set(rows.map(r => (r.invoice_no || '').trim()));
      list.innerHTML = (d.candidates || []).map(c => `
        <div class="cand ${have.has(c.invoice_no) ? 'added' : ''}">
          <div><b>${esc(c.invoice_no)}</b> <span class="text-muted small">${c.inv_date} · ${c.age} days</span><br>
          <span class="small">${esc(c.customer)}</span></div>
          <div class="text-end"><div class="small">${inr.format(c.amount)}</div>
          <button class="btn btn-sm btn-outline-primary py-0 add-cand" data-inv="${esc(c.invoice_no)}" ${have.has(c.invoice_no) ? 'disabled' : ''}>+</button></div>
        </div>`).join('') || '<div class="text-muted small">No open invoices match.</div>';
    });
  }
  document.getElementById('cand-q').addEventListener('input', () => { clearTimeout(cq); cq = setTimeout(loadCandidates, 300); });
  document.getElementById('cand-list').addEventListener('click', e => {
    const b = e.target.closest('.add-cand'); if (!b) return;
    rows.push({ invoice_no: b.dataset.inv, grn_date: '' });
    b.disabled = true; b.closest('.cand').classList.add('added');
    refreshInfo().then(() => { render(); tbody.querySelector('tr:last-child input.dt')?.focus(); });
  });

  refreshInfo().then(render);
  loadCandidates();
})();
