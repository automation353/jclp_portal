/* Server-side paged sheet grid (Combine / SR / MDA sheets). */
(function () {
  const G = window.GRID;
  const cols = G.columns;
  const state = { page: 1, size: 100, q: '', sort: null, desc: false, filters: {}, total: 0 };
  const table = document.getElementById('grid');
  const fmtNum = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtAuto = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 6, useGrouping: false });
  const hasSnap = cols.some(c => c.snap);

  // ---- column presets (Combine): which columns are drawn
  const KEY_SOURCE = ['Site', 'Invoice No', 'Invoice Date', 'Customer Name', 'Party Group Description', 'Item Code',
    'Item Name', 'Item Net Amount', 'Receipt Status', 'Goods Received Date'];
  const KEY_FORMULA = ['Revised Billing Date', 'GRN Source', 'Days to GRN', 'Current Non-GRN Amt', 'Current Age Days', 'Current Bucket'];
  const PRESETS = {
    all: () => cols.map((_, i) => i),
    key: () => cols.map((c, i) => i).filter(i => (cols[i].group === 'source' ? KEY_SOURCE : KEY_FORMULA).includes(cols[i].name)),
    formula: () => cols.map((c, i) => i).filter(i => cols[i].group === 'formula'),
  };
  const presetBtns = document.querySelectorAll('[data-preset]');
  let preset = 'all';
  if (presetBtns.length) {
    try { preset = localStorage.getItem('nongrn-preset-' + G.key) || 'key'; } catch (e) { preset = 'key'; }
  }
  let vis = PRESETS[preset]();

  function esc(s) {
    return String(s).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  }

  function fmt(v, c) {
    if (v === '' || v === null || v === undefined) return '';
    if (typeof v === 'number') {
      if (c.fmt === 'num') return v < 0 ? '(' + fmtNum.format(-v) + ')' : fmtNum.format(v);
      if (c.fmt === 'int') return String(v);
      return fmtAuto.format(v);
    }
    return esc(v);
  }

  // the month column whose row-1 date is today gets highlighted
  const tc = (i) => (cols[i].today ? ' today' : '');
  function buildHead() {
    let h = '<thead>';
    // Excel column letters
    h += '<tr class="letters"><th class="rn corner"></th>' +
      vis.map(i => `<th class="${cols[i].group}${tc(i)}" data-i="${i}">${cols[i].letter}</th>`).join('') + '</tr>';
    if (hasSnap) {   // Combine row 1: snapshot dates above the month columns
      h += '<tr class="snaprow"><th class="rn">1</th>' +
        vis.map(i => `<th class="${cols[i].group}${tc(i)}"${cols[i].today ? ' title="Today"' : ''}>${cols[i].snap || ''}</th>`).join('') + '</tr>';
    }
    h += `<tr class="names"><th class="rn">${hasSnap ? 2 : 1}</th>` + vis.map(i => [cols[i], i]).map(([c, i]) =>
      `<th class="${c.group}${tc(i)} sortable" data-i="${i}" title="${esc(c.name)}${c.formula ? '\n' + esc(c.formula) : ''}">` +
      `${c.formula ? '<span class="fx">ƒx</span>' : ''}${esc(c.name)}<span class="sort-ind"></span></th>`).join('') + '</tr>';
    h += '<tr class="filters"><th class="rn"><i class="bi bi-funnel"></i></th>' + vis.map(i =>
      `<th class="${cols[i].group}${tc(i)}"><input data-i="${i}" class="flt" placeholder="filter" value="${esc(state.filters[i] || '')}"></th>`).join('') + '</tr>';
    h += '</thead><tbody></tbody><tfoot></tfoot>';
    table.innerHTML = h;

    table.querySelectorAll('tr.names th.sortable').forEach(th => th.addEventListener('click', () => {
      const i = +th.dataset.i;
      if (state.sort === i) { if (state.desc) { state.sort = null; state.desc = false; } else state.desc = true; }
      else { state.sort = i; state.desc = false; }
      state.page = 1; load();
    }));
    let t;
    table.querySelectorAll('input.flt').forEach(inp => inp.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(() => { state.filters[inp.dataset.i] = inp.value; state.page = 1; load(); }, 350);
    }));
  }

  let render = function (data) {
    const body = table.tBodies[0];
    body.innerHTML = data.rows.map(r =>
      `<tr><th class="rn">${r.n}</th>` + vis.map(i => [r.v[i], i]).map(([v, i]) =>
        `<td class="${typeof v === 'number' ? 'n' : ''} ${cols[i].group === 'formula' ? 'f' : ''}${tc(i)}" data-i="${i}">${fmt(v, cols[i])}</td>`
      ).join('') + '</tr>').join('');
    const tf = table.tFoot;
    const keys = Object.keys(data.totals);
    tf.innerHTML = keys.length ? '<tr><th class="rn">Σ</th>' + vis.map(i =>
      `<td class="n${tc(i)}">${data.totals[i] !== undefined ? fmt(data.totals[i], cols[i]) : ''}</td>`).join('') + '</tr>' : '';
    table.querySelectorAll('tr.names th').forEach(th => {
      const ind = th.querySelector('.sort-ind');
      if (ind) ind.textContent = (+th.dataset.i === state.sort) ? (state.desc ? ' ▼' : ' ▲') : '';
    });
    state.total = data.total;
    const pages = Math.max(1, Math.ceil(data.total / state.size));
    const from = data.total ? (state.page - 1) * state.size + 1 : 0;
    const to = Math.min(state.page * state.size, data.total);
    document.getElementById('status').textContent =
      `Rows ${from.toLocaleString('en-IN')}–${to.toLocaleString('en-IN')} of ${data.total.toLocaleString('en-IN')}` +
      (data.total !== data.all_rows ? ` (filtered from ${data.all_rows.toLocaleString('en-IN')})` : '') +
      (keys.length ? ' · Σ = total of filtered rows' : '');
    document.getElementById('pageinfo').textContent = `Page ${state.page} / ${pages}`;
    body.querySelectorAll('td').forEach(td => td.addEventListener('click', () => select(td)));
  }

  function select(td) {
    table.querySelectorAll('td.sel').forEach(x => x.classList.remove('sel'));
    td.classList.add('sel');
    const c = cols[+td.dataset.i];
    const rn = td.parentElement.querySelector('th.rn').textContent;
    document.getElementById('fb-ref').textContent = c.letter + rn;
    document.getElementById('fb-text').textContent =
      c.formula ? c.formula + '   →   ' + td.textContent : td.textContent;
  }

  let ctrl;
  function load() {
    if (ctrl) ctrl.abort();
    ctrl = new AbortController();
    const p = new URLSearchParams({ page: state.page, size: state.size, q: state.q });
    if (state.sort !== null) { p.set('sort', state.sort); if (state.desc) p.set('desc', '1'); }
    for (const [k, v] of Object.entries(state.filters)) if (v) p.set('f' + k, v);
    document.getElementById('status').textContent = 'Calculating…';
    document.getElementById('grid-scroll').classList.add('busy');
    fetch(G.url + '?' + p, { signal: ctrl.signal })
      .then(r => r.json())
      .then(d => { if (d.error) throw new Error(d.error); render(d); document.getElementById('grid-scroll').classList.remove('busy'); })
      .catch(e => {
        if (e.name === 'AbortError') return;
        document.getElementById('grid-scroll').classList.remove('busy');
        document.getElementById('status').textContent = 'Error: ' + e.message;
      });
  }

  let lastData = null;
  const _render = render;
  render = (d) => { lastData = d; _render(d); };

  function applyPreset(name) {
    preset = name;
    vis = PRESETS[name]();
    presetBtns.forEach(b => b.classList.toggle('on', b.dataset.preset === name));
    try { localStorage.setItem('nongrn-preset-' + G.key, name); } catch (e) {}
    buildHead();
    if (lastData) render(lastData);
  }
  presetBtns.forEach(b => b.addEventListener('click', () => applyPreset(b.dataset.preset)));
  presetBtns.forEach(b => b.classList.toggle('on', b.dataset.preset === preset));

  buildHead();
  load();

  let qt;
  document.getElementById('q').addEventListener('input', e => {
    clearTimeout(qt);
    qt = setTimeout(() => { state.q = e.target.value; state.page = 1; load(); }, 350);
  });
  document.getElementById('size').addEventListener('change', e => { state.size = +e.target.value; state.page = 1; load(); });
  const pages = () => Math.max(1, Math.ceil(state.total / state.size));
  document.getElementById('first').onclick = () => { state.page = 1; load(); };
  document.getElementById('prev').onclick = () => { if (state.page > 1) { state.page--; load(); } };
  document.getElementById('next').onclick = () => { if (state.page < pages()) { state.page++; load(); } };
  document.getElementById('last').onclick = () => { state.page = pages(); load(); };
  document.getElementById('clear-filters').onclick = () => {
    state.filters = {}; state.q = ''; state.sort = null; state.page = 1;
    document.getElementById('q').value = '';
    table.querySelectorAll('input.flt').forEach(i => i.value = '');
    load();
  };
  document.getElementById('jump').addEventListener('change', e => {
    if (e.target.value === '') return;
    if (!vis.includes(+e.target.value) && presetBtns.length) applyPreset('all');
    const th = table.querySelector(`tr.names th[data-i="${e.target.value}"]`);
    const sc = document.getElementById('grid-scroll');
    sc.scrollLeft = th.offsetLeft - 60;
    th.classList.add('flash'); setTimeout(() => th.classList.remove('flash'), 1200);
    e.target.value = '';
  });
})();
