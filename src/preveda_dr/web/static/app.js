/* PreVeda Madhu-DR web app - plain JS, no external libraries (works offline). */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const store = {
    get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* private mode */ } },
    del(k) { try { sessionStorage.removeItem(k); } catch (e) { /* ignore */ } }
  };
  let token = store.get('pv_token');
  let me = null;
  try { me = JSON.parse(store.get('pv_me') || 'null'); } catch (e) { me = null; }
  let poll = null;
  const rs = { triage: '', q: '', offset: 0, limit: 15 };

  function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); setTimeout(() => t.classList.remove('show'), 2600); }
  async function api(path, opt = {}) {
    const headers = Object.assign({}, opt.headers || {});
    if (token) headers.Authorization = 'Bearer ' + token;
    if (opt.json) { headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(opt.json); }
    const r = await fetch('/ui-api' + path, { method: opt.method || 'GET', headers, body: opt.body });
    if (r.status === 401 && path !== '/login') { signOut(); throw new Error('Please sign in again'); }
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) { /* not json */ } throw new Error(typeof m === 'string' ? m : JSON.stringify(m)); }
    return opt.raw ? r : r.json();
  }
  const fmt = iso => iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '-';
  const badge = t => `<span class="badge t-${esc(t)}">${esc(t)}</span>`;
  const TRI = { HIGH: '#A8372F', MEDIUM: '#E6B34A', LOW: '#1F6F68', RETAKE: '#5A6B70' };
  const NAV = [['dashboard', 'Dashboard'], ['results', 'Results'], ['settings', 'Settings'], ['system', 'System']];

  /* ---------- login ---------- */
  function showLogin(msg) {
    clearInterval(poll);
    $('#app').innerHTML = `<div class="login-wrap"><form class="login" id="lf" autocomplete="off">
      <div class="brand"><span class="logo"><i></i></span>PreVeda Madhu-DR</div>
      <h1>Sign in</h1><p class="sub">Retinal screening for your hospital.</p>
      <label for="u">Username</label><input id="u" type="text" required autofocus>
      <label for="p">Password</label><input id="p" type="password" required>
      <div class="err" id="le">${esc(msg || '')}</div>
      <button class="btn block" type="submit">Sign in</button>
      <div class="demo"><b>Demo accounts</b> (trial only; replaced by hospital sign-in in production)
        <div class="chips"><button type="button" class="chip" data-u="doctor" data-p="doctor123">Doctor</button>
        <button type="button" class="chip" data-u="admin" data-p="admin123">Admin</button></div></div></form></div>`;
    document.querySelectorAll('.chip').forEach(c => c.onclick = () => { $('#u').value = c.dataset.u; $('#p').value = c.dataset.p; });
    $('#lf').onsubmit = async e => {
      e.preventDefault();
      try {
        const r = await api('/login', { method: 'POST', json: { username: $('#u').value.trim(), password: $('#p').value } });
        token = r.token; me = r.user; store.set('pv_token', token); store.set('pv_me', JSON.stringify(me));
        location.hash = '#/dashboard'; boot();
      } catch (err) { $('#le').textContent = err.message; }
    };
  }
  function signOut() {
    if (token) fetch('/ui-api/logout', { method: 'POST', headers: { Authorization: 'Bearer ' + token } }).catch(() => { });
    token = null; me = null; store.del('pv_token'); store.del('pv_me'); showLogin();
  }

  /* ---------- shell ---------- */
  function shell() {
    $('#app').innerHTML = `<div class="shell"><aside class="side"><div class="brand"><span class="logo"><i></i></span>Madhu-DR</div>
      <nav class="nav">${NAV.map(([k, l]) => `<a href="#/${k}" data-k="${k}">${l}</a>`).join('')}</nav>
      <div class="who"><b>${esc(me.name)}</b>${esc(me.role.replace('_', ' '))}<br><a href="#" id="so" style="color:#6FD0C6">Sign out</a></div></aside>
      <main class="main" id="view"></main></div>`;
    $('#so').onclick = e => { e.preventDefault(); signOut(); };
  }
  function route() {
    clearInterval(poll);
    const k = (location.hash.replace('#/', '') || 'dashboard').split('?')[0];
    const key = NAV.some(n => n[0] === k) ? k : 'dashboard';
    document.querySelectorAll('.nav a').forEach(a => a.classList.toggle('on', a.dataset.k === key));
    ({ dashboard, results, settings, system })[key]().catch(e => { $('#view').innerHTML = `<div class="card"><b class="bad">Something went wrong.</b><p>${esc(e.message)}</p></div>`; });
  }

  /* ---------- dashboard ---------- */
  async function dashboard() {
    const d = await api('/dashboard'), t = d.totals, by = t.by_triage, max = Math.max(1, ...d.trend.map(x => x.count));
    const total = Math.max(1, t.total), sc = d.scan, cfg = d.config, m = d.model;
    const kp = (n, l, c) => `<div class="card kpi ${c ? 't' : ''}" ${c ? `style="--c:${c}"` : ''}><div class="n">${n}</div><div class="l">${l}</div></div>`;
    $('#view').innerHTML = `<div class="top"><div><h1>Welcome, ${esc(me.name)}</h1><p>Screening overview for this hospital node.</p></div>
      <button class="btn" id="scanb" ${sc.running ? 'disabled' : ''}>${sc.running ? 'Scanning...' : 'Scan folder now'}</button></div>
      <div class="grid kpis">${kp(t.total, 'Images screened')}${kp(by.HIGH, 'High priority', TRI.HIGH)}${kp(by.MEDIUM, 'Medium priority', TRI.MEDIUM)}${kp(by.LOW, 'Low priority', TRI.LOW)}${kp(by.RETAKE, 'Retake needed', TRI.RETAKE)}${kp(t.pending_review, 'Awaiting doctor review')}</div>
      <div class="grid two" style="margin-bottom:16px"><div class="card"><h3>Priority mix</h3>
        <div class="stack">${['HIGH', 'MEDIUM', 'LOW', 'RETAKE'].map(k => `<i style="width:${by[k] / total * 100}%;background:${TRI[k]}"></i>`).join('')}</div>
        <div class="legend">${['HIGH', 'MEDIUM', 'LOW', 'RETAKE'].map(k => `<span style="--c:${TRI[k]}">${k} ${by[k]}</span>`).join('')}</div>
        <h3 style="margin-top:24px">Screened per day (last 14 days)</h3>
        <div class="bars">${d.trend.map(x => `<div style="height:${Math.max(3, x.count / max * 100)}%" title="${x.day}: ${x.count}">${x.count ? `<span>${x.count}</span>` : ''}</div>`).join('')}</div>
        <div class="axis">${d.trend.map(x => `<span>${x.day.slice(8)}</span>`).join('')}</div></div>
        <div class="card"><h3>Image folder</h3>
          <p class="small muted" style="margin:0 0 4px">Reading from</p><b style="word-break:break-all">${esc(cfg.watch_path)}</b>
          <p class="small" style="margin:12px 0 4px">Auto-scan: <b>${cfg.auto_scan ? 'on, every ' + cfg.scan_interval + ' s' : 'off'}</b></p>
          <p class="small muted" style="margin:0">${esc(sc.message || 'No scan has run yet.')}</p>
          ${sc.running ? `<div class="prog" style="margin-top:10px"><i style="width:${sc.total ? sc.done / sc.total * 100 : 5}%"></i></div>` : ''}
          <p style="margin:12px 0 0"><a href="#/settings">Change folder</a></p>
          <h3 style="margin-top:22px">AI model</h3>
          ${m.loaded ? `<p class="small" style="margin:0">${esc(m.name)} v${esc(m.version)} <span class="tag">${esc(m.stage)}</span><br>Signature: <span class="${m.signature_verified ? 'ok' : 'bad'}">${m.signature_verified ? 'verified' : 'not verified'}</span></p>` : `<p class="bad">Model not loaded: ${esc(m.error)}</p>`}
          <p class="small" style="margin:10px 0 0">Audit trail: <span class="${d.audit.intact ? 'ok' : 'bad'}">${d.audit.intact ? 'intact' : 'ALTERED'}</span> (${d.audit.entries} entries)</p></div></div>
      <div class="grid two-eq"><div class="card"><h3>Needs doctor attention</h3>${listTable(d.needs_attention, 'Nothing waiting for review.')}</div>
        <div class="card"><h3>Latest results</h3>${listTable(d.recent, 'No results yet. Set the image folder in Settings and scan.')}</div></div>
      <p class="small muted" style="margin-top:20px">AI-assisted screening aid, not a diagnosis. The doctor makes the final decision.</p>`;
    $('#scanb').onclick = async () => { try { await api('/scan', { method: 'POST' }); toast('Scan started'); } catch (e) { toast(e.message); } route(); };
    bindRows();
    if (sc.running) poll = setInterval(route, 2500);
  }
  function listTable(rows, empty) {
    if (!rows.length) return `<p class="muted">${esc(empty)}</p>`;
    return `<table><thead><tr><th>Record</th><th>Priority</th><th>When</th></tr></thead><tbody>${rows.map(r =>
      `<tr class="click" data-id="${esc(r.result_id)}"><td>${esc(r.record)}${r.eye && r.eye !== 'Unknown' ? ` <span class="muted small">${esc(r.eye)}</span>` : ''}</td><td>${badge(r.triage)}</td><td class="small muted">${fmt(r.created_at)}</td></tr>`).join('')}</tbody></table>`;
  }
  function bindRows() { document.querySelectorAll('tr.click').forEach(tr => tr.onclick = () => openDetail(tr.dataset.id)); }

  /* ---------- results ---------- */
  async function results() {
    $('#view').innerHTML = `<div class="top"><div><h1>Results</h1><p>Every screened image, newest first.</p></div></div>
      <div class="card"><div class="filters">${['', 'HIGH', 'MEDIUM', 'LOW', 'RETAKE'].map(k => `<button class="fchip ${rs.triage === k ? 'on' : ''}" data-t="${k}">${k || 'All'}</button>`).join('')}
        <input type="text" id="q" placeholder="Search record or finding" value="${esc(rs.q)}"></div><div id="tbl"></div></div>`;
    document.querySelectorAll('.fchip').forEach(b => b.onclick = () => { rs.triage = b.dataset.t; rs.offset = 0; results(); });
    let tm; $('#q').oninput = e => { clearTimeout(tm); tm = setTimeout(() => { rs.q = e.target.value; rs.offset = 0; loadRows(); }, 300); };
    await loadRows();
  }
  async function loadRows() {
    const r = await api(`/results?triage=${rs.triage}&q=${encodeURIComponent(rs.q)}&limit=${rs.limit}&offset=${rs.offset}`);
    const end = Math.min(rs.offset + rs.limit, r.total);
    $('#tbl').innerHTML = r.items.length ? `<div style="overflow:auto"><table><thead><tr><th>Record</th><th>Eye</th><th>Priority</th><th>AI finding</th><th>Confidence</th><th>Review</th><th>When</th></tr></thead><tbody>${r.items.map(x =>
      `<tr class="click" data-id="${esc(x.result_id)}"><td><b>${esc(x.record)}</b></td><td>${esc(x.eye)}</td><td>${badge(x.triage)}</td><td>${esc(x.prediction)}${x.flags.length ? ' ' + x.flags.map(f => `<span class="tag">${esc(f.replace(/_/g, ' '))}</span>`).join('') : ''}</td><td>${Math.round(x.confidence * 100)}%</td><td>${x.reviewed ? `<span class="ok">${esc(x.confirmed_grade)}</span>` : '<span class="muted">pending</span>'}</td><td class="small muted">${fmt(x.created_at)}</td></tr>`).join('')}</tbody></table></div>
      <div class="pager"><span class="muted small">${rs.offset + 1}-${end} of ${r.total}</span><span class="row"><button class="btn sec" id="pv" ${rs.offset ? '' : 'disabled'}>Previous</button><button class="btn sec" id="nx" ${end < r.total ? '' : 'disabled'}>Next</button></span></div>`
      : '<p class="muted">No results match. Set the image folder in Settings and run a scan.</p>';
    bindRows();
    const pv = $('#pv'), nx = $('#nx');
    if (pv) pv.onclick = () => { rs.offset = Math.max(0, rs.offset - rs.limit); loadRows(); };
    if (nx) nx.onclick = () => { rs.offset += rs.limit; loadRows(); };
  }

  /* ---------- detail drawer ---------- */
  async function openDetail(id) {
    const r = await api('/results/' + id);
    const w = document.createElement('div');
    w.innerHTML = `<div class="scrim"></div><aside class="drawer" role="dialog" aria-label="Result detail">
      <button class="x" aria-label="Close">&times;</button>
      <h2>${esc(r.record)}</h2><p class="muted small" style="margin:4px 0 10px">${esc(r.eye)} eye &middot; ${fmt(r.created_at)}${r.source_file ? ' &middot; ' + esc(r.source_file) : ''}</p>
      ${badge(r.triage)} <b style="margin-left:8px">${esc(r.ai_finding)}</b>
      ${r.has_thumbnail ? '<img class="thumb" id="th" alt="Retinal image">' : ''}
      <div class="sec"><h4>Why</h4><p style="margin:0">${esc(r.rationale)}</p>${r.flags.map(f => `<span class="tag">${esc(f.replace(/_/g, ' '))}</span>`).join('')}</div>
      <div class="sec"><h4>AI probabilities</h4>${Object.entries(r.probabilities).map(([k, v]) => `<div class="pbar"><span>${esc(k)}</span><div><i style="width:${v * 100}%"></i></div><span>${Math.round(v * 100)}%</span></div>`).join('')}</div>
      <div class="sec"><h4>Suggested follow-up</h4><p style="margin:0">${esc(r.suggested_followup)}</p>
        <h4>Suggested management</h4><p style="margin:0">${esc(r.suggested_management)}</p>
        <h4>Medication note</h4><p style="margin:0">${esc(r.medication_note)}</p></div>
      <div class="sec"><h4>Doctor review</h4>${r.review.at ? `<p style="margin:0">Confirmed as <b>${esc(r.review.grade)}</b> (${esc(r.review.decision)}) by ${esc(r.review.reviewer)}, ${fmt(r.review.at)}.${r.review.rationale ? '<br>' + esc(r.review.rationale) : ''}</p>` : '<p class="muted" style="margin:0 0 8px">Not reviewed yet.</p>'}
        <label for="gr">Confirmed grade</label><select id="gr">${r.grades.map(g => `<option ${g === r.review.grade ? 'selected' : ''}>${esc(g)}</option>`).join('')}</select>
        <label>Decision</label><div class="row"><label style="margin:0;font-weight:500"><input type="radio" name="dc" value="accept" checked> Accept AI result</label><label style="margin:0;font-weight:500"><input type="radio" name="dc" value="override"> Override</label></div>
        <label for="rt">Note (optional)</label><textarea id="rt" rows="2"></textarea>
        <div class="row" style="margin-top:14px"><button class="btn" id="sv">Save review</button><button class="btn sec" id="rp">Open printable report</button></div></div>
      <p class="disc">${esc(r.disclaimer)} Guidelines status: ${esc(r.guidelines_status)}. Model ${esc(r.model_version)} (${esc(r.model_stage)}).</p></aside>`;
    document.body.appendChild(w);
    const close = () => w.remove();
    $('.scrim', w).onclick = close; $('.x', w).onclick = close;
    if (r.has_thumbnail) api('/results/' + id + '/thumbnail', { raw: true }).then(x => x.blob()).then(b => { const i = $('#th', w); if (i) i.src = URL.createObjectURL(b); }).catch(() => { });
    $('#rp', w).onclick = async () => { try { const h = await (await api('/results/' + id + '/report', { raw: true })).text(); window.open(URL.createObjectURL(new Blob([h], { type: 'text/html' })), '_blank'); } catch (e) { toast(e.message); } };
    $('#sv', w).onclick = async () => {
      try {
        await api('/results/' + id + '/review', { method: 'POST', json: { confirmed_grade: $('#gr', w).value, decision: w.querySelector('input[name=dc]:checked').value, rationale: $('#rt', w).value || null } });
        toast('Review saved'); close(); route();
      } catch (e) { toast(e.message); }
    };
  }

  /* ---------- settings ---------- */
  async function settings() {
    const c = await api('/settings'), ro = c.can_edit ? '' : 'disabled';
    $('#view').innerHTML = `<div class="top"><div><h1>Settings</h1><p>Tell Madhu-DR where your retinal images are.</p></div></div>
      <div class="grid two"><div class="card"><h3>Image folder</h3>
        ${c.can_edit ? '' : '<div class="note" style="margin-bottom:12px">Only a hospital admin can change these settings.</div>'}
        <label for="wp">Folder to read images from</label>
        <input type="text" id="wp" value="${esc(c.watch_path)}" ${ro} placeholder="D:\\Hospital\\FundusImages">
        <p class="small muted" style="margin:6px 0 0">Type the folder as you see it on this computer, for example <b>D:\\Hospital\\FundusImages</b>. Sub-folders are included.</p>
        <div class="row" style="margin-top:10px"><button class="btn sec" id="tp">Test folder</button><span id="tr" class="small"></span></div>
        <label style="display:flex;gap:10px;align-items:center;font-weight:500;margin-top:18px"><input type="checkbox" id="as" ${c.auto_scan ? 'checked' : ''} ${ro}> Scan automatically for new images</label>
        <label for="si">Check every (seconds)</label><input type="number" id="si" min="10" max="86400" value="${c.scan_interval}" ${ro} style="max-width:160px">
        <div class="row" style="margin-top:20px"><button class="btn" id="sv" ${ro}>Save settings</button></div></div>
        <div class="card"><h3>Scan</h3><p class="small muted" style="margin-top:0">Reads every new image in the folder, scores it, and adds it to Results. Images already scored are skipped.</p>
          <button class="btn" id="sn">Scan folder now</button><div id="ss" style="margin-top:14px"></div></div></div>
      <div class="card" style="margin-top:16px"><h3>Good to know</h3>
        <p class="small" style="margin:0 0 8px">Use <b>Test folder</b> to check the path and count the images before saving. The folder is only read, never changed. Supported files: jpg, png, tif, bmp.</p>
        <p class="small muted" style="margin:0">Only drives allowed during installation can be read. If a drive is missing, run the installer again and include it. Until you set a folder, the app reads <b>${esc(c.default_path)}</b> (the <i>images</i> folder next to the installer).</p></div>`;
    $('#tp').onclick = async () => {
      try { const v = await api('/settings/test-path', { method: 'POST', json: { path: $('#wp').value } });
        $('#tr').innerHTML = `<span class="${v.image_count ? 'ok' : 'bad'}">${esc(v.message)}</span>`; } catch (e) { $('#tr').textContent = e.message; }
    };
    $('#sv').onclick = async () => {
      try { await api('/settings', { method: 'PUT', json: { watch_path: $('#wp').value, auto_scan: $('#as').checked, scan_interval: parseInt($('#si').value, 10) || 60 } }); toast('Settings saved'); } catch (e) { toast(e.message); }
    };
    $('#sn').onclick = async () => { try { await api('/scan', { method: 'POST' }); } catch (e) { toast(e.message); } showScan(); };
    showScan(); poll = setInterval(showScan, 1500);
  }
  async function showScan() {
    const box = $('#ss'); if (!box) return;
    const s = await api('/scan/status').catch(() => null); if (!s) return;
    const pct = s.total ? Math.round(s.done / s.total * 100) : 0;
    box.innerHTML = `${s.running ? `<div class="prog"><i style="width:${pct}%"></i></div><p class="small">${s.done} of ${s.total} images (${pct}%)</p>` : ''}
      <p class="small" style="margin:6px 0">${esc(s.message || 'No scan has run yet.')}</p>${s.errors.length ? `<details><summary class="small bad">${s.errors.length} problem(s)</summary><ul class="small">${s.errors.map(e => `<li>${esc(e)}</li>`).join('')}</ul></details>` : ''}`;
    const b = $('#sn'); if (b) b.disabled = s.running;
  }

  /* ---------- system ---------- */
  async function system() {
    const s = await api('/system'), m = s.model, mt = m.metrics || {};
    $('#view').innerHTML = `<div class="top"><div><h1>System</h1><p>Model, integrity and audit trail.</p></div></div>
      <div class="grid two-eq"><div class="card"><h3>AI model</h3>${m.loaded ? `<table><tbody>
        <tr><td class="muted">Name</td><td>${esc(m.name)}</td></tr><tr><td class="muted">Version</td><td>${esc(m.version)} <span class="tag">${esc(m.stage)}</span></td></tr>
        <tr><td class="muted">Outcomes</td><td>${m.classes.map(esc).join(', ')}</td></tr><tr><td class="muted">Signature</td><td class="${m.signature_verified ? 'ok' : 'bad'}">${m.signature_verified ? 'Verified' : 'Not verified'}</td></tr>
        <tr><td class="muted">Fingerprint</td><td class="small" style="word-break:break-all">${esc(m.onnx_sha256)}</td></tr>
        <tr><td class="muted">Test score (AUROC)</td><td>${mt.auroc != null ? esc(Number(mt.auroc).toFixed(2)) : '-'}</td></tr></tbody></table>
        <p class="note small" style="margin-top:14px">Pilot-stage model. Tested on a small number of DR cases, so a LOW result never rules out disease.</p>` : `<p class="bad">${esc(m.error)}</p>`}</div>
        <div class="card"><h3>Audit trail</h3><p>Chain status: <b class="${s.audit.intact ? 'ok' : 'bad'}">${s.audit.intact ? 'Intact' : 'ALTERED at entry ' + s.audit.first_bad_id}</b> (${s.audit.entries} entries)</p>
        <table><thead><tr><th>When</th><th>Who</th><th>Action</th></tr></thead><tbody>${s.audit_tail.map(a => `<tr><td class="small muted">${fmt(a.ts)}</td><td>${esc(a.actor)}</td><td>${esc(a.action.replace(/_/g, ' ').toLowerCase())}</td></tr>`).join('') || '<tr><td colspan="3" class="muted">No activity yet.</td></tr>'}</tbody></table></div></div>
      <p class="small muted" style="margin-top:20px">Node ${esc(s.node)} &middot; version ${esc(s.version)} &middot; sign-in mode: ${s.auth_mode === 'off' ? 'demo login' : esc(s.auth_mode)}</p>
      <div class="card" style="margin-top:16px"><h3>For developers and other systems</h3><p class="small" style="margin:0">The same service also exposes a REST API: <a href="${esc(s.api_url)}/docs" target="_blank" rel="noopener">${esc(s.api_url)}/docs</a> (interactive documentation). Other hospital systems can send images to <code>POST /madhu/predict/dr</code> there.</p></div>`;
  }

  async function boot() {
    if (!token) return showLogin();
    try { me = await api('/me'); store.set('pv_me', JSON.stringify(me)); } catch (e) { return showLogin(); }
    shell(); route();
  }
  window.addEventListener('hashchange', () => { if (token && $('#view')) route(); });
  boot();
})();
