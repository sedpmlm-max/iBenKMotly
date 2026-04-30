/**
 * Molty Royale Dashboard — Smooth Realtime Engine
 * DOM diffing: only updates changed values, no flickering.
 * Animated counters, smooth bars, auto-scroll logs.
 */
const $ = id => document.getElementById(id);
const esc = s => { const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; };
const fmt = n => n >= 1e6 ? (n/1e6).toFixed(1)+'M' : n >= 1e3 ? (n/1e3).toFixed(1)+'k' : String(n);

// ─── Item display names ───
const ITEM_NAMES = {
  'rewards':'$Moltz','reward1':'$Moltz','reward':'$Moltz',
  'emergency_food':'Emergency Food','emergency_rations':'Emergency Rations',
  'bandage':'Bandage','medkit':'Medkit','energy_drink':'Energy Drink',
  'dagger':'Dagger','sword':'Sword','katana':'Katana',
  'bow':'Bow','pistol':'Pistol','sniper':'Sniper',
  'binoculars':'Binoculars','map':'Map','megaphone':'Megaphone','radio':'Radio',
  'fist':'Fist','fists':'Fists',
};
function itemName(i) {
  if (typeof i === 'string') return ITEM_NAMES[i.toLowerCase()] || i;
  // Try name → typeId → type → itemType → id
  const raw = i.name || i.typeId || i.type || i.itemType || i.id || '?';
  // Look up in known items first
  const resolved = ITEM_NAMES[raw.toLowerCase()] || ITEM_NAMES[(i.typeId||'').toLowerCase()];
  if (resolved) return resolved;
  // If it's a UUID/hash, show truncated
  if (raw.length > 20 || raw.includes('-')) return raw.slice(0, 10) + '…';
  return raw;
}
function itemTag(i) {
  const name = itemName(i);
  const cat = (typeof i === 'object' ? i.cat : '') || '';
  const colors = {weapon:'#FF6B6B',recovery:'#00FF88',utility:'#00D2FF',currency:'#FFB800'};
  const bdr = colors[cat] ? `border-left:2px solid ${colors[cat]};` : '';
  return `<span class="item-tag" style="${bdr}">${esc(name)}</span>`;
}

// ─── State ───
let S = { agents:{}, stats:{}, logs:[], agent_logs:{}, accounts:[] };
let currentPage = 'dashboard', currentLogTab = 'all';
let prevAgentHash = '';

// ─── Navigation ───
function showPage(p) {
  document.querySelectorAll('.page').forEach(e => e.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(e => e.classList.remove('active'));
  $('page-'+p).classList.add('active');
  document.querySelector('[data-page="'+p+'"]').classList.add('active');
  currentPage = p;
}

// ─── WebSocket with fast reconnect ───
let ws, wsRetry = 0;
function connectWS() {
  const url = (location.protocol==='https:'?'wss:':'ws:') + '//' + location.host + '/ws';
  try { ws = new WebSocket(url); } catch(e) { setTimeout(connectWS, 2000); return; }
  ws.onopen = () => { wsRetry = 0; };
  ws.onmessage = e => {
    try {
      const m = JSON.parse(e.data);
      if (m.type === 'snapshot') { S = m.data; render(); }
    } catch(err) {}
  };
  ws.onclose = () => setTimeout(connectWS, Math.min(1000 * (++wsRetry), 8000));
  ws.onerror = () => ws.close();
}

// Polling — guaranteed realtime fallback (runs ALWAYS, even with WS open)
setInterval(() => {
  fetch('/api/state').then(r=>r.json()).then(d => { S = d; render(); }).catch(()=>{});
}, 3000);

// ─── Master render ───
function render() {
  try { renderHeader(); } catch(e) {}
  try { renderAgentCards(); } catch(e) {}
  try { renderAgentsTable(); } catch(e) {}
  try { renderDataTable(); } catch(e) {}
  try { renderLogs(); } catch(e) {}
}

// ─── Smooth text update (only if changed) ───
function setText(el, val) {
  if (typeof el === 'string') el = $(el);
  if (!el) return;
  const v = String(val);
  if (el.textContent !== v) el.textContent = v;
}

// ─── Animated counter ───
const counters = {};
function animateNum(id, target) {
  const el = $(id);
  if (!el) return;
  const key = id;
  const current = counters[key] || 0;
  if (current === target) return;
  counters[key] = target;
  // Simple step animation
  const start = parseFloat(el.textContent) || 0;
  const diff = target - start;
  if (diff === 0) { el.textContent = fmt(target); return; }
  const steps = 12;
  let step = 0;
  const timer = setInterval(() => {
    step++;
    const progress = step / steps;
    const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    const val = Math.round(start + diff * eased);
    el.textContent = fmt(val);
    if (step >= steps) { clearInterval(timer); el.textContent = fmt(target); }
  }, 30);
}

// ─── Header ───
function renderHeader() {
  const s = S.stats || {};
  const agentList = Object.values(S.agents || {});
  const total = agentList.length;
  // Count from actual agent card status (matches badge in top-right of each card)
  const playing = agentList.filter(a => a.status === 'playing').length;
  const dead = agentList.filter(a => a.status === 'dead').length;
  animateNum('h-agents', total);
  animateNum('h-playing', playing);
  animateNum('h-dead', dead);
  animateNum('h-wins', s.total_wins || 0);
  animateNum('h-moltz', s.total_moltz || 0);
  animateNum('h-smoltz', s.total_smoltz || 0);
}

// ─── Agent Cards (DOM diffing) ───
function renderAgentCards() {
  const container = $('agent-cards');
  const agents = Object.entries(S.agents || {});
  const hash = JSON.stringify(agents.map(([id,a]) => id + (a.hp||0) + (a.ep||0) + (a.status||'') + (a.last_action||'') + (a.kills||0) + (a.alive_count||0) + (a.inventory||[]).length + (a.enemies||[]).length + (a.region_items||[]).length + (a.region||'')));

  if (hash === prevAgentHash) return;
  prevAgentHash = hash;

  if (!agents.length) {
    container.innerHTML = '<div class="card" style="text-align:center;padding:40px;color:var(--text2)"><span class="status-dot idle"></span> Waiting for agent connection...</div>';
    return;
  }

  // Check if we need to rebuild or can patch
  const existingCards = container.querySelectorAll('.agent-card');
  const needRebuild = existingCards.length !== agents.length;

  if (needRebuild) {
    container.innerHTML = agents.map(([id]) => `<div class="card agent-card" data-aid="${id}"></div>`).join('');
  }

  agents.forEach(([id, a]) => {
    let card = container.querySelector(`[data-aid="${id}"]`);
    if (!card) return;
    patchAgentCard(card, id, a);
  });
}

function patchAgentCard(card, id, a) {
  const st = a.status || 'idle';
  // Badge: playing=green, dead=red(dead), error=red(err), idle=amber
  const bc = st==='playing'?'ok':st==='dead'?'dead':st==='error'?'err':'warn';
  const name = a.name || 'Agent';
  const hp = a.hp ?? 0, maxHp = a.maxHp || 100;
  const ep = a.ep ?? 0, maxEp = a.maxEp || 10;
  const hpPct = Math.min(100, Math.round((hp/maxHp)*100));
  const epPct = Math.min(100, Math.round((ep/maxEp)*100));
  const atk = a.atk || 0, def = a.def || 0, wpnBonus = a.weapon_bonus || 0;
  const weapon = a.weapon || 'fist';
  const kills = a.kills || 0;
  const region = a.region || '—';
  const roomId = a.room_id || '—';

  const inv = (a.inventory||[]).map(i => itemTag(i)).join('') || '<span style="color:var(--text2)">Empty</span>';
  const enemies = (a.enemies||[]).map(e => `<span class="item-tag" style="border-left:2px solid var(--red)">${esc(e.name||'?')} HP:${e.hp}</span>`).join('') || '<span style="color:var(--text2)">None</span>';
  const items = (a.region_items||[]).map(i => itemTag(i)).join('') || '<span style="color:var(--text2)">None</span>';

  // Status indicator: dot for playing/idle, skull for dead, no dot for error
  let statusIcon;
  if (st === 'dead') statusIcon = '<span style="font-size:12px;margin-right:6px">☠️</span>';
  else if (st === 'playing') statusIcon = '<span class="status-dot active"></span>';
  else if (st === 'error') statusIcon = '<span class="status-dot error"></span>';
  else statusIcon = '<span class="status-dot idle"></span>';

  card.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
      <div>${statusIcon}<span class="agent-name">${esc(name)}</span></div>
      <span class="badge ${bc}">${st.toUpperCase()}</span>
    </div>
    <div class="agent-meta">
      Room: ${esc(a.room_name||'—')} &nbsp;|&nbsp; ID: <span style="color:var(--text)">${esc(roomId)}</span> &nbsp;|&nbsp; 📍 ${esc(region)}
    </div>
    <div class="bar-row">
      <div class="bar-wrap">
        <div class="bar-label"><span class="bl">❤️ HP</span><span class="bv" style="color:${hpPct>50?'var(--green)':hpPct>25?'var(--amber)':'var(--red)'}">${hp} / ${maxHp}</span></div>
        <div class="bar-track"><div class="bar-fill hp" style="width:${hpPct}%"></div></div>
      </div>
      <div class="bar-wrap">
        <div class="bar-label"><span class="bl">⚡ EP</span><span class="bv" style="color:var(--cyan)">${ep} / ${maxEp}</span></div>
        <div class="bar-track"><div class="bar-fill ep" style="width:${epPct}%"></div></div>
      </div>
    </div>
    <div class="combat-row">
      <div class="combat-stat"><div class="cv">${atk+wpnBonus}</div><div class="cl">⚔️ ATK (${atk}+${wpnBonus})</div></div>
      <div class="combat-stat"><div class="cv">${def}</div><div class="cl">🛡️ DEF</div></div>
      <div class="combat-stat"><div class="cv" style="font-size:11px">${esc(ITEM_NAMES[weapon.toLowerCase()]||weapon)}</div><div class="cl">🗡️ WEAPON</div></div>
      <div class="combat-stat"><div class="cv">${kills}</div><div class="cl">💀 KILLS</div></div>
      <div class="combat-stat"><div class="cv">${a.alive_count||'?'}</div><div class="cl">👥 ALIVE</div></div>
    </div>
    <div class="agent-stats">
      <div class="agent-stat"><div class="v">${a.wins||0}</div><div class="l">WIN</div></div>
      <div class="agent-stat"><div class="v">${fmt(a.moltz||0)}</div><div class="l">MOLTZ</div></div>
      <div class="agent-stat"><div class="v">${fmt(a.smoltz||0)}</div><div class="l">sMOLTZ</div></div>
      <div class="agent-stat"><div class="v">${a.cross||0}</div><div class="l">CROSS</div></div>
    </div>
    <div class="action-log">${a.last_action ? '▸ '+esc(a.last_action) : '<span style="color:var(--text2)">Waiting...</span>'}</div>
    <div class="info-grid">
      <div class="info-block"><h4>📦 Inventory</h4><div class="items">${inv}</div></div>
      <div class="info-block"><h4>👁️ Enemies</h4><div class="items">${enemies}</div></div>
      <div class="info-block"><h4>🎯 Region Items</h4><div class="items">${items}</div></div>
    </div>`;
}

// ─── Agents Overview Table ───
function renderAgentsTable() {
  const s = S.stats || {};
  setText('ov-active', s.agents_active || 0);
  setText('ov-idle', s.agents_idle || 0);
  setText('ov-dead', s.agents_dead || 0);
  const tb = $('agents-tbody');
  const agents = Object.entries(S.agents || {});
  if (!agents.length) { tb.innerHTML = '<tr><td colspan="7" style="color:var(--text2);text-align:center">No agents</td></tr>'; return; }
  tb.innerHTML = agents.map(([id,a]) => {
    const st = a.status||'idle';
    // Status badge: playing=green, idle=amber, dead=red, error=red
    let bc, label;
    if (st === 'playing') { bc = 'ok'; label = 'playing'; }
    else if (st === 'dead') { bc = 'dead'; label = 'dead'; }
    else if (st === 'error') { bc = 'err'; label = 'error'; }
    else { bc = 'warn'; label = st; }
    const wl = a.whitelisted ? '<span class="badge ok">✓</span>' : '<span class="badge warn">…</span>';
    return `<tr><td>${esc(a.name||id)}</td><td><span class="badge ${bc}">${label}</span></td>
      <td>${fmt(a.moltz||0)}</td><td>${fmt(a.smoltz||0)}</td><td>${(a.cross||0)}</td>
      <td>${a.wins||0}</td><td>${wl}</td></tr>`;
  }).join('');
}

// ─── Data Table ───
function renderDataTable() {
  const tb = $('data-tbody');
  if (!tb) return; // Data page not in DOM (coming soon)
  if (!S.accounts?.length) { tb.innerHTML = '<tr><td colspan="5" style="color:var(--text2);text-align:center">No accounts</td></tr>'; return; }
  tb.innerHTML = S.accounts.map(a =>
    `<tr><td>${esc(a.agent_name||'—')}</td><td style="font-size:10px">${esc((a.api_key||'').slice(0,20))}…</td>
    <td style="font-size:10px">${esc((a.owner_eoa||'').slice(0,16))}…</td>
    <td>${a.room_mode||'free'}</td><td>${a.auto_whitelist?'✅':'❌'}</td></tr>`
  ).join('');
}

// ─── Logs (always render — no skip) ───
function renderLogs() {
  const logs = currentLogTab === 'all' ? (S.logs||[]) : ((S.agent_logs||{})[currentLogTab]||[]);
  const box = $('log-box');
  if (!box) return;

  const wasBottom = box.scrollTop >= box.scrollHeight - box.clientHeight - 40;
  const visible = logs.slice(-200);
  box.innerHTML = visible.map(l =>
    `<div class="log-line">${_logLine(l)}</div>`
  ).join('');
  if (wasBottom || box.scrollTop === 0) box.scrollTop = box.scrollHeight;
}

function _logLine(l) {
  const t = new Date((l.ts||0)*1000);
  const ts = t.toLocaleTimeString();
  const lvl = l.level || 'info';
  const agentName = l.agent ? (S.agents?.[l.agent]?.name || l.agent.slice(0,8)) : '';
  const agentLabel = agentName ? `<span style="color:var(--cyan);opacity:.7">[${esc(agentName)}]</span> ` : '';
  return `<span class="ts">${ts}</span> <span class="lvl-${lvl}">[${lvl.toUpperCase()}]</span> ${agentLabel}${esc(l.msg||'')}`;
}

function switchLogTab(tab, elem) {
  currentLogTab = tab;
  document.querySelectorAll('.log-tab').forEach(e => e.classList.remove('active'));
  if (elem) elem.classList.add('active');
  renderLogs();
}

// ─── Account Form ───
function saveAccount() {
  const acc = {
    api_key: $('f-apikey').value,
    agent_name: $('f-name').value,
    owner_eoa: $('f-owner').value,
    owner_pk: $('f-pk').value,
    room_mode: $('f-room').value
  };
  if (!acc.api_key) { alert('API Key required'); return; }
  fetch('/api/accounts', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(acc) })
    .then(r => r.json()).then(() => { alert('Saved!'); showPage('data'); }).catch(e => alert('Error: '+e));
}

function exportData() {
  fetch('/api/export').then(r=>r.blob()).then(b => {
    const u = URL.createObjectURL(b);
    const a = document.createElement('a');
    a.href = u; a.download = 'molty-'+new Date().toISOString().slice(0,10)+'.json'; a.click();
  });
}

function importData(e) {
  const f = e.target.files[0]; if (!f) return;
  const r = new FileReader();
  r.onload = ev => {
    fetch('/api/import', { method:'POST', headers:{'Content-Type':'application/json'}, body:ev.target.result })
      .then(() => alert('Imported!')).catch(err => alert('Error'));
  };
  r.readAsText(f);
}

// ─── Boot ───
// Ensure DOM is ready, then fetch state + connect WS
document.addEventListener('DOMContentLoaded', () => {
  // 1. Fetch state immediately so logs appear on first paint
  fetch('/api/state')
    .then(r => r.json())
    .then(d => { S = d; render(); })
    .catch(() => {});

  // 2. Connect WebSocket for realtime updates
  connectWS();

  // 3. Safety: force render after 2s in case of race condition
  setTimeout(() => { render(); }, 2000);
});
