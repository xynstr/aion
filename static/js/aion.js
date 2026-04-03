// AION Web UI — loaded at end of <body>; DOM is guaranteed ready when this runs.

// CONSTANTS & STATE
// ═══════════════════════════════════════════════════════════════════
// Lucide icon names for tools
const TOOL_ICONS = {
  web_search:'search', web_fetch:'globe', shell_exec:'terminal', winget_install:'package',
  file_read:'file', file_write:'file-pen', self_read_code:'eye', self_patch_code:'bandage',
  file_replace_lines:'scissors', self_modify_code:'pencil', install_package:'package-plus',
  create_plugin:'wrench', create_tool:'wrench', memory_record:'database', system_info:'info',
  reflect:'brain', update_character:'user-pen', switch_model:'refresh-cw',
  send_telegram_message:'send', continue_work:'fast-forward',
  todo_add:'circle-plus', todo_list:'list-todo', todo_done:'circle-check', todo_remove:'trash-2',
  smart_patch:'hammer', schedule_add:'clock', schedule_list:'calendar',
  schedule_remove:'trash-2', schedule_toggle:'toggle-right',
  image_search:'image', create_docx:'file-text', audio_tts:'volume-2',
  audio_transcribe_any:'mic', browser_open:'globe', browser_screenshot:'camera',
  browser_click:'mouse-pointer-click', browser_fill:'type', browser_get_text:'align-left',
  browser_evaluate:'code', browser_find:'search', browser_close:'x-circle',
  ask_claude:'bot', delegate_to_agent:'users', sessions_list:'layout-list',
  sessions_send:'send', sessions_history:'history',
};
// Lucide icon names for plugins
const PLUGIN_ICONS = {
  core_tools:'settings-2', reflection:'brain', shell_tools:'terminal', web_tools:'globe',
  character_manager:'user', memory_plugin:'database', gemini_provider:'sparkles',
  anthropic_provider:'bot', deepseek_provider:'cpu', grok_provider:'activity',
  ollama_provider:'hard-drive', openai_provider:'zap',
  telegram_bot:'send', discord_bot:'message-circle', slack_bot:'hash',
  image_search:'image', scheduler:'clock', audio_pipeline:'mic',
  audio_transcriber:'volume-2', smart_patch:'hammer', todo_tools:'list-todo',
  heartbeat:'heart-pulse', restart_tool:'rotate-ccw', pid_tool:'fingerprint',
  docx_tool:'file-text', moltbook:'book-open', playwright_browser:'monitor',
  multi_agent:'network', claude_cli_provider:'bot',
};

let isThinking        = false;
let currentBubble     = null;
let awaitingNewBubble = false;
const toolDataStore   = {};
let currentModalCallId = null;

// ── Detach-Task State ─────────────────────────────────────────────────────────
let _detachMode  = false;
let _detachQueue = [];   // {text, imgs}[] — Nachrichten während ausgelagertem Task

// Section state
let currentSection = 'chat';

// Channel switcher state
let _activeChannel = 'web';

// Prompt state
let _promptFile   = 'rules';
let _promptLoaded = {};
let _promptDirty  = {};
let _memDebounce  = null;

// Memory pagination state
let _memOffset   = 0;
const _MEM_LIMIT = 80;

// ═══════════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════════
async function loadHistory(channel) {
  const ch = channel || _activeChannel || 'web';
  try {
    const r = await fetch('/api/history' + (ch !== 'web' ? `?channel=${encodeURIComponent(ch)}` : ''));
    if (!r.ok) return;
    const data = await r.json();
    const msgEl = document.getElementById('messages');
    // Clear existing messages (preserve welcome if no history)
    msgEl.innerHTML = '';
    if (!data.messages || !data.messages.length) {
      msgEl.innerHTML = `<div class="welcome" id="welcome">
        <img src="aion-2026.svg" alt="AION" style="width:400px;height:auto;margin-bottom:32px">
        <div class="chips">
          <div class="chip" onclick="useChip(this)">What can you do?</div>
          <div class="chip" onclick="useChip(this)">Find latest AI news</div>
          <div class="chip" onclick="useChip(this)">Show me your source code</div>
          <div class="chip" onclick="useChip(this)">Install VLC Player</div>
          <div class="chip" onclick="useChip(this)">What system runs here?</div>
          <div class="chip" onclick="useChip(this)">Create a new tool</div>
        </div>
      </div>`;
      return;
    }
    for (const msg of data.messages) {
      if (msg.role === 'user') {
        if (Array.isArray(msg.content)) {
          // Multimodal message (text + images)
          const textPart = msg.content.find(p => p.type === 'text')?.text || '';
          if (textPart) appendUserMsg(textPart);
          for (const p of msg.content) {
            if (p.type === 'image_url' && p.image_url?.url) appendImageBlock(p.image_url.url);
          }
        } else if (typeof msg.content === 'string' && msg.content) {
          appendUserMsg(msg.content);
        }
      } else if (msg.role === 'assistant' && typeof msg.content === 'string' && msg.content.trim()) {
        appendHistoryAionMsg(msg.content);
      }
    }
    scrollChat();
  } catch {}
}

async function loadChannels() {
  try {
    const r = await fetch('/api/channels');
    if (!r.ok) return;
    const data = await r.json();
    const channels = data.channels || [];
    const bar  = document.getElementById('channelBar');
    const pills = document.getElementById('channelPills');
    if (!bar || !pills) return;
    if (channels.length <= 1) { bar.style.display = 'none'; return; }
    bar.style.display = '';
    pills.innerHTML = channels.map(ch => {
      const active = ch.id === _activeChannel ? 'active' : '';
      const badge  = ch.count ? `<span class="ch-badge">${ch.count}</span>` : '';
      const ro     = ch.id !== 'web' ? `<span class="ch-readonly">readonly</span>` : '';
      return `<button class="ch-pill ${active}" onclick="switchChannel('${esc(ch.id)}')">${esc(ch.label)}${badge}${ro}</button>`;
    }).join('');
  } catch {}
}

async function switchChannel(id) {
  _activeChannel = id;
  await loadChannels(); // re-render pills with new active
  // Clear messages + reload history for this channel
  document.getElementById('messages').innerHTML = '';
  await loadHistory(id);
  // If non-web channel, disable input
  const input   = document.getElementById('input');
  const sendBtn = document.getElementById('sendBtn');
  const isWeb   = id === 'web';
  if (input)   input.disabled   = !isWeb;
  if (sendBtn) sendBtn.disabled = !isWeb;
  if (!isWeb) {
    if (input) input.placeholder = 'Nur Ansicht — Antworten über ' + id.split('_')[0];
  } else {
    if (input) input.placeholder = 'Message to AION… (Enter = Send, Shift+Enter = New line)';
  }
}

async function checkUpdateBanner() {
  if (sessionStorage.getItem('updateBannerDismissed')) return;
  try {
    const r = await fetch('/api/update-status');
    if (!r.ok) return;
    const d = await r.json();
    if (d.update_available) {
      const banner = document.getElementById('updateBanner');
      const text   = document.getElementById('updateBannerText');
      const cur = d.current_version || '?';
      const lat = d.latest_version  || '?';
      const url = d.release_url     || '';
      text.innerHTML = url
        ? `AION <b>${lat}</b> verfügbar (aktuell: ${cur}) — <code>aion update</code> ausführen &nbsp;·&nbsp; <a href="${url}" target="_blank" rel="noopener">Release-Notes</a>`
        : `AION <b>${lat}</b> verfügbar (aktuell: ${cur}) — <code>aion update</code> ausführen`;
      banner.style.display = 'flex';
    }
  } catch {}
}

function dismissUpdateBanner() {
  document.getElementById('updateBanner').style.display = 'none';
  sessionStorage.setItem('updateBannerDismissed', '1');
}

const MOOD_ICONS = { curious: "💡", focused: "🎯", playful: "😊", calm: "🌿", reflective: "🤔" };
let _currentMood = "calm";
let _wakeupShown = false;

async function loadMood() {
  try {
    const d = await (await fetch('/api/status')).json();
    const mood = d.mood || "calm";
    if (mood === _currentMood) return;
    _currentMood = mood;
    const badge = document.getElementById('moodBadge');
    if (badge) badge.textContent = `${MOOD_ICONS[mood] || "·"} ${mood}`;
    document.querySelectorAll('.msg.aion .msg-bubble').forEach(b => {
      b.className = b.className.replace(/\bmood-\w+/g, '').trim();
      b.classList.add(`mood-${mood}`);
    });
  } catch {}
}

async function loadActivity() {
  const el = document.getElementById('activityContent');
  if (!el) return;
  try {
    const d = await (await fetch('/api/activity?limit=60')).json();
    const events = d.events || [];
    // Build a map: tool_call id → {name, ts} so we can pair durations
    const calls = {};
    const rows = [];
    for (const e of events) {
      if (e.type === 'tool_call') {
        calls[e.tool] = { ts: e.ts };
        rows.push({ ts: e.ts, tool: e.tool, ok: null, dur: null, id: e.tool });
      } else if (e.type === 'tool_result') {
        const key = e.tool;
        if (calls[key]) {
          const dur = e.duration != null ? Number(e.duration).toFixed(1) + 's' : null;
          // Update the matching row
          const row = rows.find(r => r.id === key && r.ok === null);
          if (row) { row.ok = e.ok !== false; row.dur = dur; }
        }
      } else if (e.type === 'turn_error') {
        rows.push({ ts: e.ts, tool: '⚠ ' + (e.error || 'turn_error'), ok: false, dur: null, id: null });
      }
    }
    if (!rows.length) {
      el.innerHTML = '<div class="memory-empty"><span style="opacity:.4">No activity yet</span></div>';
      return;
    }
    const fmtTime = ts => { try { return new Date(ts).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}); } catch { return ts || '–'; } };
    let html = '<table class="activity-table"><thead><tr><th>Time</th><th>Tool</th><th>Status</th><th>Duration</th></tr></thead><tbody>';
    for (const r of [...rows].reverse()) {
      const status = r.ok === null ? '<span style="color:var(--text3)">…</span>' : r.ok ? '<span class="aev-ok">✓</span>' : '<span class="aev-err">✗</span>';
      html += `<tr><td style="color:var(--text3);font-size:11px;white-space:nowrap">${fmtTime(r.ts)}</td><td class="aev-tool">${esc(r.tool)}</td><td>${status}</td><td class="aev-dur">${r.dur || '–'}</td></tr>`;
    }
    html += '</tbody></table>';
    el.innerHTML = html;
  } catch (err) {
    el.innerHTML = `<div class="memory-empty"><span style="color:var(--red)">Error loading activity</span></div>`;
  }
}

async function init() {
  try {
    const s = await (await fetch('/api/status')).json();
    syncModelSelects(s.model, document.getElementById('modelSelect'));
    // Mood init
    const mood = s.mood || "calm";
    _currentMood = mood;
    const badge = document.getElementById('moodBadge');
    if (badge) badge.textContent = `${MOOD_ICONS[mood] || "·"} ${mood}`;
    // Pending wakeup message (persisted in config.json — reliable even after SSE race)
    if (s.pending_wakeup) {
      setTimeout(() => {
        handleWakeup({ text: s.pending_wakeup });
        fetch('/api/wakeup-ack', { method: 'POST' }).catch(() => {});
      }, 1200);
    }
    // Retry — mehrfach, da Wakeup-LLM-Call 4–15s dauern kann
    for (const delay of [5000, 10000, 18000]) {
      setTimeout(async () => {
        if (_wakeupShown) return;
        try {
          const s2 = await (await fetch('/api/status')).json();
          if (s2.pending_wakeup) {
            handleWakeup({ text: s2.pending_wakeup });
            fetch('/api/wakeup-ack', { method: 'POST' }).catch(() => {});
          }
        } catch {}
      }, delay);
    }
  } catch {}
  // Load history and channels in parallel instead of sequentially
  await Promise.all([loadHistory(), loadChannels()]);
  if (window.lucide) lucide.createIcons();
  // Scroll-to-bottom Button: einblenden wenn nicht ganz unten
  (function() {
    const msgEl = document.getElementById('messages');
    const btn   = document.getElementById('scrollBottomBtn');
    if (!msgEl || !btn) return;
    msgEl.addEventListener('scroll', function() {
      const atBottom = msgEl.scrollHeight - msgEl.scrollTop - msgEl.clientHeight < 80;
      btn.classList.toggle('visible', !atBottom);
    });
  })();
  checkUpdateBanner();
  // Alle 6h erneut prüfen (bei offenem Browser-Tab)
  setInterval(checkUpdateBanner, 6 * 60 * 60 * 1000);
  // Mood: poll every 30s
  setInterval(loadMood, 30000);
  // Activity auto-refresh every 5s when tab is active
  setInterval(() => { if (currentSection === 'activity') loadActivity(); }, 5000);
}
init();

function syncModelSelects(model, ...selects) {
  selects.forEach(sel => {
    if (!sel) return;
    let found = false;
    for (let opt of sel.options) { if (opt.value === model) { sel.value = model; found = true; break; } }
    if (!found) { const o = document.createElement('option'); o.value = model; o.textContent = model; sel.appendChild(o); sel.value = model; }
  });
}

// ═══════════════════════════════════════════════════════════════════
// SECTION NAVIGATION
// ═══════════════════════════════════════════════════════════════════
function switchSection(name) {
  currentSection = name;
  document.querySelectorAll('.snav-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.getElementById(`snav-${name}`).classList.add('active');
  document.getElementById(`section-${name}`).classList.add('active');
  loadCurrentSection();
  if (name === 'chat') scrollChat();
}

function loadCurrentSection() {
  if (currentSection === 'prompts')  { if (!_promptLoaded[_promptFile]) loadPrompt(_promptFile); }
  if (currentSection === 'plugins')  loadPlugins();
  if (currentSection === 'memory')   loadMemory();
  if (currentSection === 'keys')     { loadKeys(); initGoogleOAuth(); }
  if (currentSection === 'settings') { loadSettings(); loadPermissions(); }
  if (currentSection === 'activity') loadActivity();
  // Re-initialize icons for newly visible static HTML elements
  if (window.lucide) lucide.createIcons();
}

// ── PROMPTS ───────────────────────────────────────────────────────────────────
function promptSwitch(name) {
  if (_promptDirty[_promptFile] && !confirm('Ungespeicherte Änderungen verwerfen?')) return;
  _promptDirty[_promptFile] = false; updateDirtyDot(_promptFile, false);
  document.querySelectorAll('.prompt-item').forEach(b => b.classList.remove('active'));
  document.getElementById(`pitem-${name}`).classList.add('active');
  _promptFile = name;
  loadPrompt(name);
}

async function loadPrompt(name) {
  const ta = document.getElementById('promptEditor');
  const st = document.getElementById('promptStatus');
  ta.value = ''; ta.placeholder = 'Laden…'; st.textContent = ''; st.className = 'prompt-status';
  try {
    const data = await (await fetch(`/api/prompt/${name}`)).json();
    ta.value = data.content || ''; ta.placeholder = '';
    ta.classList.remove('dirty');
    _promptLoaded[name] = true; _promptDirty[name] = false; updateDirtyDot(name, false);
  } catch { st.textContent = '✗ Fehler'; st.className = 'prompt-status err'; }
}

function onPromptEdit() {
  _promptDirty[_promptFile] = true;
  document.getElementById('promptEditor').classList.add('dirty');
  document.getElementById('promptStatus').textContent = '● Nicht gespeichert';
  document.getElementById('promptStatus').className   = 'prompt-status';
  updateDirtyDot(_promptFile, true);
}

async function savePrompt() {
  const content = document.getElementById('promptEditor').value;
  const btn = document.getElementById('promptSaveBtn');
  const st  = document.getElementById('promptStatus');
  btn.disabled = true; st.textContent = 'Speichern…'; st.className = 'prompt-status';
  try {
    const data = await (await fetch(`/api/prompt/${_promptFile}`, {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({content}),
    })).json();
    if (data.ok) {
      _promptDirty[_promptFile] = false;
      document.getElementById('promptEditor').classList.remove('dirty');
      updateDirtyDot(_promptFile, false);
      st.textContent = '✓ Gespeichert'; st.className = 'prompt-status ok';
      setTimeout(() => { if (!_promptDirty[_promptFile]) { st.textContent = ''; st.className = 'prompt-status'; } }, 2500);
    } else { st.textContent = `✗ ${data.error||'Fehler'}`; st.className = 'prompt-status err'; }
  } catch { st.textContent = '✗ Netzwerkfehler'; st.className = 'prompt-status err'; }
  finally { btn.disabled = false; }
}

function updateDirtyDot(name, dirty) {
  const d = document.getElementById(`pdirty-${name}`);
  if (d) d.classList.toggle('visible', dirty);
  // Sidebar nav dot: visible if any prompt has unsaved changes
  const anyDirty = Object.values(_promptDirty).some(Boolean);
  const navDot = document.getElementById('snav-dirty-prompts');
  if (navDot) navDot.classList.toggle('visible', anyDirty);
}

// ── PLUGINS ───────────────────────────────────────────────────────────────────
async function loadPlugins() {
  const list = document.getElementById('pluginList');
  list.innerHTML = '<div class="memory-empty"><span class="spinner" style="width:20px;height:20px;border-width:2px"></span></div>';
  try {
    const data = await (await fetch('/api/plugins')).json();
    document.getElementById('pluginTotalBadge').textContent = `${data.total_loaded} Tools geladen`;
    document.getElementById('ptab-installed-badge').textContent = data.plugins.length;
    renderPlugins(data);
  } catch(e) { list.innerHTML = `<div class="memory-empty">✗ Fehler: ${esc(e.message)}</div>`; }
}

function renderPlugins(data) {
  const list = document.getElementById('pluginList');
  list.innerHTML = '';
  let html = '';
  for (const p of data.plugins) {
    const picon    = pluginIcon(p.name);
    const isOff    = p.disabled;
    const cls      = isOff ? 'unloaded' : (p.loaded ? 'loaded' : 'unloaded');
    const cntCls   = p.loaded ? 'loaded' : '';
    const toggleLbl = isOff ? 'Enable' : 'Disable';
    const toggleFn  = isOff ? 'enablePlugin' : 'disablePlugin';
    const toolsHtml = p.tools.map(t => `
      <div class="plugin-tool-row">
        <span class="pt-status ${t.loaded ? 'ok' : 'err'}">${t.loaded ? '✓' : '✗'}</span>
        <span class="pt-name">${esc(t.name)}</span>
        <span class="pt-desc">${esc((t.description || '').slice(0, 100))}</span>
      </div>`).join('');
    html += `
      <div class="plugin-card ${cls}" id="pc-${esc(p.name)}">
        <div class="plugin-hdr" onclick="togglePlugin('${esc(p.name)}')">
          <span class="plugin-icon">${picon}</span>
          <span class="plugin-name">${esc(p.name)}</span>
          ${isOff ? '<span style="font-size:10px;color:var(--text3);margin-right:4px">disabled</span>' : ''}
          <span class="plugin-count ${cntCls}">${p.tools.length} Tools</span>
          <button class="action-btn" style="margin-left:auto;padding:2px 8px;font-size:11px" onclick="event.stopPropagation();${toggleFn}(this,'${esc(p.name)}')">${toggleLbl}</button>
          <span class="plugin-chevron" style="margin-left:6px">▶</span>
        </div>
        <div class="plugin-tools">${toolsHtml || '<span style="font-size:11px;color:var(--text3)">No tools registered</span>'}</div>
      </div>`;
  }
  if (data.orphan_tools && data.orphan_tools.length) {
    const chips = data.orphan_tools.map(t => `<span class="orphan-chip">${icon('settings-2',11)} ${esc(t.name)}</span>`).join('');
    html += `<div class="orphan-section"><div class="orphan-label">Weitere Tools (ohne Plugin-Ordner)</div><div style="display:flex;flex-wrap:wrap">${chips}</div></div>`;
  }
  list.innerHTML = html || '<div class="memory-empty"><span style="opacity:.3">Keine Plugins gefunden</span></div>';
  if (window.lucide) lucide.createIcons({rootNode: list});
}

function togglePlugin(name) { document.getElementById(`pc-${name}`).classList.toggle('open'); }

async function disablePlugin(btn, name) {
  btn.disabled = true; btn.innerHTML = '<span class="mini-spinner"></span>';
  try {
    await fetch('/api/plugins/disable', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name})});
    loadPlugins();
  } finally { btn.disabled = false; btn.textContent = 'Disable'; }
}
async function enablePlugin(btn, name) {
  btn.disabled = true; btn.innerHTML = '<span class="mini-spinner"></span>';
  try {
    await fetch('/api/plugins/enable', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name})});
    loadPlugins();
  } finally { btn.disabled = false; btn.textContent = 'Enable'; }
}

// ── PLUGIN HUB ────────────────────────────────────────────────────────────────
let _hubLoaded         = false;
let _hubData           = [];
let _hubFilterStatus   = 'available'; // 'available' | 'installed' | 'all'
let _hubFilterCategory = 'all';

const _HUB_CATS = {
  telegram_bot:'Messaging', discord_bot:'Messaging', slack_bot:'Messaging', alexa_plugin:'Messaging',
  anthropic_provider:'AI Providers', gemini_provider:'AI Providers', deepseek_provider:'AI Providers',
  grok_provider:'AI Providers', ollama_provider:'AI Providers', claude_cli_provider:'AI Providers',
  desktop:'Automation', playwright_browser:'Automation', multi_agent:'Automation',
  audio_pipeline:'Audio', audio_transcriber:'Audio',
  docx_tool:'Productivity', image_search:'Productivity', mcp_client:'Productivity', moltbook:'Productivity',
  mood_engine:'Personality', proactive:'Personality', character_manager:'Personality',
  focus_manager:'Personality', heartbeat:'Personality',
};

function switchPluginTab(tab) {
  const isHub = tab === 'hub';
  document.getElementById('ptab-installed').classList.toggle('active', !isHub);
  document.getElementById('ptab-hub').classList.toggle('active', isHub);
  document.getElementById('pluginList').style.display       = isHub ? 'none' : '';
  document.getElementById('snapSection').style.display      = isHub ? 'none' : '';
  document.getElementById('hubPanel').style.display         = isHub ? '' : 'none';
  const banner = document.getElementById('hubPromoBanner');
  if (banner) banner.style.display = isHub ? 'none' : '';
  if (isHub && !_hubLoaded) loadHub();
}

function setHubStatus(val) {
  _hubFilterStatus = val;
  ['available','installed','all'].forEach(v =>
    document.getElementById('hfc-'+v).classList.toggle('active', v === val));
  applyHubFilters();
}

function setHubCategory(val, el) {
  _hubFilterCategory = val;
  document.querySelectorAll('.hub-cat-chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
  applyHubFilters();
}

function applyHubFilters() {
  const q = (document.getElementById('hubSearch').value || '').toLowerCase();
  let list = _hubData;
  if (_hubFilterStatus === 'available') list = list.filter(p => !p.installed);
  if (_hubFilterStatus === 'installed') list = list.filter(p =>  p.installed);
  if (_hubFilterCategory !== 'all')
    list = list.filter(p => (_HUB_CATS[p.name] || 'Other') === _hubFilterCategory);
  if (q) list = list.filter(p =>
    ((p.name||'') + (p.display_name||'') + (p.description||'')).toLowerCase().includes(q));
  renderHub(list);
  document.getElementById('hubStatus').textContent = `${list.length} of ${_hubData.length}`;
}

function filterHub() { applyHubFilters(); }

async function loadHub() {
  const grid = document.getElementById('hubGrid');
  grid.innerHTML = '<div class="memory-empty" style="grid-column:1/-1"><span class="spinner" style="width:18px;height:18px;border-width:2px"></span></div>';
  document.getElementById('hubStatus').textContent = '';
  try {
    const data = await (await fetch('/api/hub')).json();
    if (data.error) throw new Error(data.error);
    _hubData   = data.plugins || [];
    _hubLoaded = true;
    const notInstalled = _hubData.filter(p => !p.installed).length;
    document.getElementById('ptab-hub-badge').textContent = _hubData.length;
    // Update promo banner
    const sub = document.getElementById('hubPromoSub');
    if (sub) sub.textContent = `${notInstalled} optional plugins available — browser automation, voice I/O, desktop control, Telegram bots & more. Install on demand, no restart needed.`;
    // Build category chips
    const cats = [...new Set(_hubData.map(p => _HUB_CATS[p.name] || 'Other'))].sort();
    const bar  = document.getElementById('hubFilterBar');
    bar.querySelectorAll('.hub-cat-chip').forEach(c => c.remove());
    bar.insertAdjacentHTML('beforeend',
      `<button class="hub-chip hub-cat-chip active" onclick="setHubCategory('all',this)">All categories</button>`);
    cats.forEach(cat => bar.insertAdjacentHTML('beforeend',
      `<button class="hub-chip hub-cat-chip" onclick="setHubCategory('${cat}',this)">${cat}</button>`));
    applyHubFilters();
  } catch(e) {
    grid.innerHTML = `<div class="memory-empty" style="grid-column:1/-1;color:var(--red)">✗ ${esc(e.message)}</div>`;
    document.getElementById('hubStatus').textContent = 'unreachable';
  }
}

function renderHub(plugins) {
  const grid = document.getElementById('hubGrid');
  if (!plugins.length) {
    grid.innerHTML = '<div class="memory-empty" style="grid-column:1/-1">No plugins found</div>';
    return;
  }
  grid.innerHTML = plugins.map(p => {
    const hasUpdate = p.update_available;
    const installed = p.installed;
    let verHtml = '', btnHtml = '';
    if (installed && hasUpdate) {
      verHtml = `<span class="hub-ver update">↑ ${esc(p.version)}</span>`;
      btnHtml = `<button class="hub-btn update" onclick="hubInstall('${esc(p.name)}',this)">Update</button>`;
    } else if (installed) {
      verHtml = `<span class="hub-ver installed">✓ ${esc(p.local_version || p.version)}</span>`;
      btnHtml = `<button class="hub-btn remove" onclick="hubRemove('${esc(p.name)}',this)">Remove</button>`;
    } else {
      verHtml = `<span class="hub-ver remote">${esc(p.version)}</span>`;
      btnHtml = `<button class="hub-btn install" onclick="hubInstall('${esc(p.name)}',this)">Install</button>`;
    }
    const deps = (p.dependencies || []).map(d => `<span class="hub-dep">${esc(d)}</span>`).join('');
    return `
      <div class="hub-card" id="hc-${esc(p.name)}">
        <div class="hub-card-hdr">
          <span class="hub-card-name">${esc(p.display_name || p.name)}</span>
          ${verHtml}
        </div>
        <div class="hub-desc">${esc(p.description || '')}</div>
        ${deps ? `<div class="hub-deps">${deps}</div>` : ''}
        <div class="hub-card-footer">${btnHtml}</div>
      </div>`;
  }).join('');
}

function filterHub() {
  const q = document.getElementById('hubSearch').value.toLowerCase();
  if (!q) { renderHub(_hubData); return; }
  renderHub(_hubData.filter(p =>
    (p.name + p.display_name + p.description).toLowerCase().includes(q)
  ));
}

async function hubInstall(name, btn) {
  const orig = btn.textContent;
  btn.disabled = true; btn.innerHTML = '<span class="mini-spinner"></span>';
  try {
    const r = await fetch('/api/hub/install', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name})});
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    // Update local data entry and re-render card
    const idx = _hubData.findIndex(p => p.name === name);
    if (idx >= 0) { _hubData[idx].installed = true; _hubData[idx].local_version = d.version; _hubData[idx].update_available = false; }
    applyHubFilters();
    loadPlugins();
  } catch(e) {
    btn.disabled = false; btn.textContent = orig;
    alert(`Install failed: ${e.message}`);
  }
}

async function hubRemove(name, btn) {
  const orig = btn.textContent;
  btn.disabled = true; btn.innerHTML = '<span class="mini-spinner"></span>';
  try {
    const r = await fetch('/api/hub/remove', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name})});
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    const idx = _hubData.findIndex(p => p.name === name);
    if (idx >= 0) { _hubData[idx].installed = false; _hubData[idx].local_version = null; }
    applyHubFilters();
    loadPlugins();
  } catch(e) {
    btn.disabled = false; btn.textContent = orig;
    alert(`Remove failed: ${e.message}`);
  }
}

// ── SNAPSHOTS ─────────────────────────────────────────────────────────────────
let _snapLoaded = false;

function toggleSnapSection() {
  const sec = document.getElementById('snapSection');
  sec.classList.toggle('open');
  if (sec.classList.contains('open') && !_snapLoaded) loadSnapshots();
}

async function loadSnapshots() {
  _snapLoaded = true;
  const body = document.getElementById('snapBody');
  try {
    const data = await (await fetch('/api/snapshots')).json();
    const snaps = data.snapshots || {};
    const plugins = Object.keys(snaps).sort();
    const total = plugins.reduce((s, p) => s + snaps[p].length, 0);
    document.getElementById('snapBadge').textContent = `${total} total`;
    if (!plugins.length) {
      body.innerHTML = '<div class="memory-empty" style="padding:12px;font-size:11px">No snapshots yet</div>';
      return;
    }
    let html = '';
    for (const p of plugins) {
      const ts = snaps[p];
      const tsHtml = ts.length
        ? ts.slice().reverse().map(t => `
            <div class="snap-ts-entry">
              <span class="snap-ts">${esc(t)}</span>
              <button class="snap-restore-btn" onclick="restoreSnapshot('${esc(p)}','${esc(t)}',this)">Restore</button>
            </div>`).join('')
        : '<span class="snap-ts" style="opacity:.4">—</span>';
      html += `<div class="snap-plugin-row">
        <span class="snap-plugin-name">${esc(p)}</span>
        <div class="snap-ts-list">${tsHtml}</div>
      </div>`;
    }
    body.innerHTML = html;
  } catch(e) {
    body.innerHTML = `<div class="memory-empty" style="padding:12px;font-size:11px">✗ ${esc(e.message)}</div>`;
  }
}

async function restoreSnapshot(plugin, timestamp, btn) {
  if (!confirm(`Restore ${plugin} to snapshot ${timestamp}?`)) return;
  btn.disabled = true; btn.textContent = '…';
  try {
    const res = await fetch(`/api/snapshots/${encodeURIComponent(plugin)}/restore`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({timestamp})
    });
    const data = await res.json();
    if (data.ok) {
      showToast(`✓ ${plugin} restored to ${timestamp}`);
      btn.textContent = '✓'; btn.style.color = 'var(--accent)';
      loadPlugins();
    } else {
      showToast('✗ Restore failed');
      btn.disabled = false; btn.textContent = 'Restore';
    }
  } catch(e) {
    showToast('✗ ' + e.message);
    btn.disabled = false; btn.textContent = 'Restore';
  }
}

async function reloadPlugins() {
  const btn = document.getElementById('pluginReloadBtn');
  btn.disabled = true; btn.innerHTML = '<span class="mini-spinner"></span>';
  try {
    const data = await (await fetch('/api/plugins/reload', {method:'POST'})).json();
    if (data.ok) { showToast(`✓ ${data.count} Tools geladen`); loadPlugins(); loadSettings(); }
    else showToast('✗ ' + (data.error || 'Fehler'));
  } catch(e) { showToast('✗ ' + e.message); }
  finally { btn.disabled = false; btn.textContent = 'Reload'; }
}

// ── MEMORY ────────────────────────────────────────────────────────────────────
let _memAllEntries = [];

async function loadMemory(append = false) {
  const q    = document.getElementById('memorySearch').value.trim();
  const list = document.getElementById('memoryList');
  if (!append) {
    _memOffset = 0;
    _memAllEntries = [];
    list.innerHTML = '<div class="memory-empty"><span class="spinner" style="width:20px;height:20px;border-width:2px"></span></div>';
  }
  try {
    let url = `/api/memory?limit=${_MEM_LIMIT}&offset=${_memOffset}`;
    if (q) url += `&search=${encodeURIComponent(q)}`;
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    document.getElementById('memoryTotalBadge').textContent = `${data.total} Einträge`;
    _memAllEntries = _memAllEntries.concat(data.entries);
    _memOffset += data.entries.length;
    renderMemory(_memAllEntries, data.has_more);
  } catch(e) { list.innerHTML = `<div class="memory-empty">✗ ${esc(e.message)}</div>`; }
}

function renderMemory(entries, hasMore = false) {
  const list = document.getElementById('memoryList');
  if (!entries.length) { list.innerHTML = '<div class="memory-empty"><span style="opacity:.25;display:flex"><i data-lucide="database" style="width:22px;height:22px;stroke-width:1.5"></i></span><span>Keine Einträge gefunden</span></div>'; if (window.lucide) lucide.createIcons({rootNode: list}); return; }
  const cards = entries.map(e => {
    const ts  = e.timestamp ? e.timestamp.replace('T',' ').slice(0,16) : '';
    const cls = e.success === false ? 'failure' : 'success';
    return `
      <div class="memory-entry ${cls}">
        <div class="memory-meta">
          <span class="memory-cat">${esc(e.category || 'general')}</span>
          <span class="memory-ts">${esc(ts)}</span>
        </div>
        <div class="memory-summary">${esc(e.summary || '')}</div>
        ${e.lesson ? `<div class="memory-lesson">${esc(e.lesson.slice(0,200))}</div>` : ''}
      </div>`;
  }).join('');
  const moreBtn = hasMore
    ? `<div style="text-align:center;padding:12px"><button class="action-btn" onclick="loadMemory(true)">Mehr laden</button></div>`
    : '';
  list.innerHTML = '<div class="memory-list">' + cards + '</div>' + moreBtn;
}

function debounceMemorySearch() { clearTimeout(_memDebounce); _memDebounce = setTimeout(() => loadMemory(false), 350); }

async function clearMemory() {
  if (!confirm('Memory komplett leeren? Das kann nicht rückgängig gemacht werden.')) return;
  try {
    const data = await (await fetch('/api/memory', {method:'DELETE'})).json();
    if (data.ok) { showToast('✓ Memory geleert'); loadMemory(); loadSettings(); }
    else showToast('✗ ' + (data.error || 'Fehler'));
  } catch(e) { showToast('✗ ' + e.message); }
}

// ── KEYS ──────────────────────────────────────────────────────────────────────
async function loadKeys() {
  try {
    const r = await fetch('/api/keys');
    if (!r.ok) throw new Error(r.status);
    const d = await r.json();
    renderKeys(d);
  } catch(e) {
    document.getElementById('keysList').innerHTML =
      `<div class="memory-empty"><span style="color:var(--danger)">Fehler beim Laden der Keys</span></div>`;
  }
}

// URLs + Hinweise pro Provider
const _KEY_META = {
  GEMINI_API_KEY:      { url: 'https://aistudio.google.com/apikey', label: 'Key holen (AI Studio)', hint: 'Kostenlos mit Google-Account' },
  OPENAI_API_KEY:      { url: 'https://platform.openai.com/api-keys', label: 'Key holen (OpenAI)', hint: 'Konto + Guthaben benötigt' },
  ANTHROPIC_API_KEY:   { url: 'https://console.anthropic.com/settings/keys', label: 'Key holen (Anthropic)', hint: 'Oder Claude-Abo via CLI nutzen' },
  DEEPSEEK_API_KEY:    { url: 'https://platform.deepseek.com/api_keys', label: 'Key holen (DeepSeek)', hint: 'Günstige Alternative' },
  XAI_API_KEY:         { url: 'https://console.x.ai/', label: 'Key holen (xAI)', hint: 'Grok-Modelle' },
  TELEGRAM_BOT_TOKEN:  { url: 'https://t.me/BotFather', label: 'Token via @BotFather', hint: 'Telegram öffnen → /newbot' },
  DISCORD_BOT_TOKEN:   { url: 'https://discord.com/developers/applications', label: 'Token holen', hint: 'New App → Bot → Token kopieren' },
  SLACK_BOT_TOKEN:     { url: 'https://api.slack.com/apps', label: 'Token holen', hint: 'New App → OAuth & Permissions' },
};

function renderKeys(data) {
  const el = document.getElementById('keysList');
  let html = '';

  const makeRow = (k) => {
    const meta = _KEY_META[k.key] || {};
    const getLink = meta.url
      ? `<a href="${esc(meta.url)}" target="_blank" class="action-btn" style="font-size:10px;padding:4px 8px;text-decoration:none">${esc(meta.label||'Get')} ↗</a>`
      : '';
    const hint = meta.hint
      ? `<span style="font-size:10px;color:var(--text3)">${esc(meta.hint)}</span>`
      : '';
    return `
    <tr style="border-bottom:1px solid var(--border)">
      <td style="padding:10px 12px;font-size:11px;color:var(--text);font-family:monospace;width:200px">${k.key}</td>
      <td style="padding:10px 12px;font-size:10px;color:var(--text3);">
        <span style="display:inline-block;padding:2px 6px;border-radius:3px;background:${k.set?'rgba(74,222,128,0.1)':'rgba(255,107,107,0.1)'}"><span style="color:${k.set?'var(--green)':'var(--red)'};font-weight:700">${k.set?'✓':'✗'}</span> ${k.set?'SET':'MISSING'}</span>
      </td>
      <td style="padding:10px 12px;font-size:10px;color:var(--text3);width:200px">${k.set ? esc(k.masked) : (hint || '—')}</td>
      <td style="padding:10px 12px">${getLink}</td>
      <td style="padding:10px 12px;display:flex;gap:6px;align-items:center">
        <input type="password" class="key-input" id="key-${k.key}" style="width:140px;padding:6px 8px;font-size:11px"
               placeholder="${k.set?'Keep':'Paste'}">
        <button class="action-btn primary" onclick="saveKey('${k.key}')" style="padding:6px 12px;font-size:11px">Save</button>
        ${k.set ? `<button class="action-btn" onclick="deleteKey('${k.key}')" style="padding:6px 10px;font-size:11px;color:var(--red);border-color:var(--red)" title="Key löschen">✕</button>` : ''}
      </td>
    </tr>`;
  };

  // Claude CLI
  html += `<div style="margin-bottom:20px">
    <div style="font-size:12px;font-weight:700;color:var(--text);margin-bottom:10px;display:flex;align-items:center;gap:8px">
      <span style="width:6px;height:6px;border-radius:50%;background:var(--blue,#2ea3f5)"></span> Claude (Subscription)
    </div>
    <div style="font-size:11px;color:var(--text3);margin-bottom:8px">Use Claude.ai subscription ($20/$200) — no API key needed</div>
    <div id="keysClaudeStatus" style="font-size:11px;color:var(--text2);margin-bottom:8px"></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="action-btn" id="keysClaudeLoginBtn" onclick="claudeCliLoginFromKeys()">Sign In</button>
      <button class="action-btn" onclick="checkClaudeStatusInKeys()">↺ Check Status</button>
    </div>
    <div id="keysClaudeMsg" style="margin-top:6px;font-size:11px;display:none"></div>
  </div>`;

  // AI Providers
  for (const prov of data.providers) {
    const allSet = prov.env_keys.every(k => k.set);
    const count = prov.env_keys.filter(k => k.set).length;
    html += `
    <div style="margin-bottom:20px">
      <div style="font-size:12px;font-weight:700;color:var(--text);margin-bottom:10px;display:flex;align-items:center;gap:8px">
        <span style="width:6px;height:6px;border-radius:50%;background:${allSet?'var(--green)':'var(--red)'}"></span>
        ${esc(prov.label)} <span style="font-size:10px;color:var(--text3);font-weight:400;margin-left:auto">${count}/${prov.env_keys.length}</span>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:11px">
        ${prov.env_keys.map(k => makeRow(k)).join('')}
      </table>
    </div>`;
  }

  // Other services
  if (data.other_keys && data.other_keys.length) {
    html += `
    <div style="margin-bottom:20px">
      <div style="font-size:12px;font-weight:700;color:var(--text);margin-bottom:10px;display:flex;align-items:center;gap:8px">
        <span style="width:6px;height:6px;border-radius:50%;background:var(--text3)"></span> Other Services
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:11px">
        ${data.other_keys.map(k => makeRow(k)).join('')}
      </table>
    </div>`;
  }

  // Add custom key
  html += `
  <div style="margin-top:24px;padding:14px;background:var(--bg4);border:1px solid var(--border);border-radius:8px">
    <div style="font-size:11px;font-weight:700;color:var(--text);margin-bottom:8px">Add Custom Key</div>
    <div style="font-size:10px;color:var(--text3);margin-bottom:10px">Set any environment variable (MISTRAL_API_KEY, CUSTOM_TOKEN, etc.)</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap">
      <input type="text" id="customKeyName" class="key-input" placeholder="ENV_VAR_NAME" style="max-width:150px;font-family:monospace;text-transform:uppercase;padding:6px 8px;font-size:11px" oninput="this.value=this.value.toUpperCase().replace(/\\s/g,'_')">
      <input type="password" id="customKeyValue" class="key-input" placeholder="Value" style="flex:1;min-width:150px;padding:6px 8px;font-size:11px">
      <button class="action-btn primary" onclick="saveCustomKey()" style="padding:6px 12px;font-size:11px">Add</button>
    </div>
  </div>`;

  el.innerHTML = html || '<div class="memory-empty"><span style="opacity:.4">Keine Keys gefunden</span></div>';
  if (window.lucide) lucide.createIcons({rootNode: el});
  checkClaudeStatusInKeys();
}

async function checkClaudeStatusInKeys() {
  const el = document.getElementById('keysClaudeStatus');
  if (!el) return;
  try {
    const r = await fetch('/api/claude-cli/status');
    const d = await r.json();
    if (!d.installed) {
      el.innerHTML = '<span style="color:var(--text3)">CLI nicht installiert</span>';
    } else if (!d.authenticated) {
      el.innerHTML = '<span style="color:var(--yellow,#f5a623)">⚠ Installiert, aber nicht angemeldet</span>';
    } else {
      el.innerHTML = '<span style="color:var(--green)">✓ Angemeldet — ask_claude nutzbar</span>';
    }
  } catch { if (el) el.textContent = ''; }
}

async function claudeCliLoginFromKeys() {
  const btn = document.getElementById('keysClaudeLoginBtn');
  const msg = document.getElementById('keysClaudeMsg');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  if (msg) { msg.style.display = ''; msg.style.color = 'var(--text3)'; msg.textContent = 'Starte Login…'; }
  try {
    const r = await fetch('/api/claude-cli/login', { method: 'POST' });
    const d = await r.json();
    if (d.ok) {
      if (d.step === 'already_authenticated') {
        if (msg) { msg.style.color = 'var(--green)'; msg.textContent = '✓ Bereits angemeldet.'; }
        checkClaudeStatusInKeys();
      } else if (d.step === 'browser_opened') {
        if (msg) { msg.style.color = 'var(--text2)'; msg.innerHTML = '🌐 Browser geöffnet — anmelden, dann "↺ Status" klicken.'; }
        let polls = 0;
        const iv = setInterval(async () => {
          if (++polls > 30) { clearInterval(iv); return; }
          try {
            const s = await (await fetch('/api/claude-cli/status')).json();
            if (s.authenticated) {
              clearInterval(iv);
              if (msg) { msg.style.color = 'var(--green)'; msg.textContent = '✓ Anmeldung erfolgreich!'; }
              checkClaudeStatusInKeys();
            }
          } catch {}
        }, 4000);
      }
    } else {
      if (msg) { msg.style.color = 'var(--red,#e55)'; msg.textContent = d.error || 'Fehler'; }
    }
  } catch(e) {
    if (msg) { msg.style.color = 'var(--red,#e55)'; msg.textContent = e.message; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Mit Claude anmelden'; }
  }
}

async function saveKey(envKey) {
  const input = document.getElementById(`key-${envKey}`);
  const val   = input.value.trim();
  if (!val) { showToast('Bitte einen Wert eingeben', true); return; }
  try {
    const r = await fetch('/api/keys', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({[envKey]: val}),
    });
    const d = await r.json();
    if (d.ok) {
      showToast(`✓ ${envKey} gespeichert`);
      input.value = '';
      loadKeys();
    } else {
      showToast(`Fehler: ${d.error}`, true);
    }
  } catch(e) { showToast('Netzwerkfehler', true); }
}

async function saveCustomKey() {
  const nameEl = document.getElementById('customKeyName');
  const valEl  = document.getElementById('customKeyValue');
  const name   = (nameEl?.value || '').trim().toUpperCase().replace(/\s+/g, '_');
  const val    = (valEl?.value  || '').trim();
  if (!name) { showToast('Bitte einen Key-Namen eingeben', true); return; }
  if (!val)  { showToast('Bitte einen Wert eingeben', true); return; }
  try {
    const r = await fetch('/api/keys', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({[name]: val}),
    });
    const d = await r.json();
    if (d.ok) {
      showToast(`✓ ${name} gespeichert`);
      if (nameEl) nameEl.value = '';
      if (valEl)  valEl.value  = '';
      loadKeys();
    } else {
      showToast(`Fehler: ${d.error}`, true);
    }
  } catch(e) { showToast('Netzwerkfehler', true); }
}

async function deleteKey(envKey) {
  if (!confirm(`Key "${envKey}" wirklich aus dem Vault löschen?`)) return;
  try {
    const r = await fetch(`/api/keys/${encodeURIComponent(envKey)}`, {method: 'DELETE'});
    const d = await r.json();
    if (d.ok) { showToast(`✓ ${envKey} gelöscht`); loadKeys(); }
    else showToast(`Fehler: ${d.error}`, true);
  } catch(e) { showToast('Netzwerkfehler', true); }
}

// ── PERMISSIONS ───────────────────────────────────────────────────────────────
let _permData = null;

async function loadPermissions() {
  try {
    const r = await fetch('/api/permissions');
    if (!r.ok) return;
    _permData = await r.json();
    renderPermissions(_permData);
  } catch {}
}

function renderPermissions(data) {
  const el = document.getElementById('permissionsList');
  if (!el || !data) return;
  el.innerHTML = Object.entries(data.permissions).map(([key, val]) => {
    const label = (data.labels && data.labels[key]) || key;
    return `<div class="perm-row">
      <span class="perm-label">${label}</span>
      <select class="perm-select val-${val}" onchange="savePerm('${key}', this.value, this)">
        <option value="allow" ${val==='allow'?'selected':''}>allow</option>
        <option value="ask"   ${val==='ask'  ?'selected':''}>ask</option>
        <option value="deny"  ${val==='deny' ?'selected':''}>deny</option>
      </select>
    </div>`;
  }).join('');
}

async function savePerm(key, value, selectEl) {
  if (selectEl) { selectEl.className = `perm-select val-${value}`; }
  try {
    await fetch('/api/permissions', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({[key]: value}),
    });
    showToast(`✓ ${key}: ${value}`);
  } catch { showToast('Fehler beim Speichern', true); }
}

const _PERM_PRESETS = {
  conservative: { shell_exec:'ask', install_package:'ask', file_write:'ask', file_delete:'ask', self_modify:'ask', create_plugin:'ask', restart:'ask', web_search:'allow', web_fetch:'allow', telegram_auto:'ask', memory_write:'allow', schedule:'ask' },
  balanced:     { shell_exec:'ask', install_package:'ask', file_write:'allow', file_delete:'ask', self_modify:'ask', create_plugin:'ask', restart:'ask', web_search:'allow', web_fetch:'allow', telegram_auto:'allow', memory_write:'allow', schedule:'ask' },
  autonomous:   { shell_exec:'allow', install_package:'allow', file_write:'allow', file_delete:'allow', self_modify:'allow', create_plugin:'allow', restart:'allow', web_search:'allow', web_fetch:'allow', telegram_auto:'allow', memory_write:'allow', schedule:'allow' },
};

async function applyPermPreset(preset) {
  const perms = _PERM_PRESETS[preset];
  if (!perms) return;
  try {
    const body = {...perms, preset};
    await fetch('/api/permissions', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    showToast(`✓ Preset "${preset}" gespeichert`);
    loadPermissions();
  } catch { showToast('Fehler', true); }
}

// ── THINKING LEVEL ────────────────────────────────────────────────────────────
function _renderThinkingSettings(cfg) {
  const sel = document.getElementById('thinkingLevelGlobal');
  if (sel && cfg.thinking_level) sel.value = cfg.thinking_level;
  const overrides = cfg.thinking_overrides || {};
  const el = document.getElementById('thinkingOverridesList');
  if (!el) return;
  el.innerHTML = Object.entries(overrides).map(([ch, lv]) =>
    `<span class="tag-chip" style="display:inline-flex;align-items:center;gap:4px;background:var(--bg4);border:1px solid var(--border);border-radius:4px;padding:3px 8px;font-size:11px;font-family:monospace;cursor:pointer" title="Klicken zum Entfernen" onclick="removeThinkingOverride('${esc(ch)}')">
      ${esc(ch)}: <b>${esc(lv)}</b> <span style="opacity:.5;margin-left:2px">×</span>
    </span>`
  ).join('');
}

async function saveThinkingLevel() {
  const level = document.getElementById('thinkingLevelGlobal')?.value;
  if (!level) return;
  try {
    const r = await fetch('/api/config/thinking', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({level}),
    });
    const d = await r.json();
    if (d.ok) { showToast(`✓ Thinking Level: ${level}`); _renderThinkingSettings(d); }
    else showToast(d.error || 'Fehler', true);
  } catch { showToast('Fehler', true); }
}

async function saveThinkingOverride() {
  const channel = document.getElementById('thinkingOverrideChannel')?.value.trim();
  const level   = document.getElementById('thinkingOverrideLevel')?.value;
  if (!channel) { showToast('Bitte Channel eingeben', true); return; }
  try {
    const r = await fetch('/api/config/thinking', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({level, channel}),
    });
    const d = await r.json();
    if (d.ok) {
      showToast(`✓ Override gespeichert: ${channel} → ${level}`);
      document.getElementById('thinkingOverrideChannel').value = '';
      _renderThinkingSettings(d);
    } else showToast(d.error || 'Fehler', true);
  } catch { showToast('Fehler', true); }
}

async function removeThinkingOverride(channel) {
  try {
    const r = await fetch('/api/config/thinking', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({channel, level: ''}),
    });
    const d = await r.json();
    if (d.ok) { showToast(`✓ Override entfernt: ${channel}`); _renderThinkingSettings(d); }
  } catch { showToast('Fehler', true); }
}

// ── CHANNEL ALLOWLIST ─────────────────────────────────────────────────────────
let _allowlistEntries = [];

function _renderAllowlistSettings(cfg) {
  _allowlistEntries = cfg.channel_allowlist ? [...cfg.channel_allowlist] : [];
  _refreshAllowlistUI();
}

function _refreshAllowlistUI() {
  const el = document.getElementById('allowlistEntries');
  if (!el) return;
  if (_allowlistEntries.length === 0) {
    el.innerHTML = '<span style="font-size:11px;color:var(--text3)">Leer — alle Channels erlaubt</span>';
    return;
  }
  el.innerHTML = _allowlistEntries.map((ch, i) =>
    `<span style="display:inline-flex;align-items:center;gap:4px;background:var(--bg4);border:1px solid var(--border);border-radius:4px;padding:3px 8px;font-size:11px;font-family:monospace;cursor:pointer" title="Klicken zum Entfernen" onclick="removeAllowlistEntry(${i})">
      ${esc(ch)} <span style="opacity:.5;margin-left:2px">×</span>
    </span>`
  ).join('');
}

function addAllowlistEntry() {
  const inp = document.getElementById('allowlistNewChannel');
  if (!inp) return;
  const val = inp.value.trim();
  if (!val) return;
  if (!_allowlistEntries.includes(val)) _allowlistEntries.push(val);
  inp.value = '';
  _refreshAllowlistUI();
}

function removeAllowlistEntry(idx) {
  _allowlistEntries.splice(idx, 1);
  _refreshAllowlistUI();
}

async function saveAllowlist() {
  try {
    const r = await fetch('/api/config/allowlist', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({channels: _allowlistEntries}),
    });
    const d = await r.json();
    if (d.ok) showToast(_allowlistEntries.length ? `✓ Allowlist gespeichert (${_allowlistEntries.length} Einträge)` : '✓ Allowlist geleert — alle Channels erlaubt');
    else showToast(d.error || 'Fehler', true);
  } catch { showToast('Fehler', true); }
}

async function clearAllowlist() {
  _allowlistEntries = [];
  _refreshAllowlistUI();
  await saveAllowlist();
}

// ── SETTINGS ──────────────────────────────────────────────────────────────────
async function refreshSettings() {
  const btn = document.getElementById('settingsRefreshBtn');
  const orig = btn ? btn.innerHTML : '';
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="mini-spinner"></span> Lade…'; }
  try {
    await loadSettings();
    showToast('✓ Einstellungen aktualisiert');
  } catch(e) { showToast('✗ ' + e.message, true); }
  finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = orig || '<i data-lucide="refresh-cw" style="width:13px;height:13px;stroke-width:1.75"></i> Aktualisieren';
      if (window.lucide) lucide.createIcons();
    }
  }
}

async function loadSettings() {
  _loadClaudeCliStatus(); // sofort beim Betreten der Seite holen
  try {
    const data = await (await fetch('/api/config')).json();
    document.getElementById('settingsBotDir').textContent = data.bot_dir || '–';
    document.getElementById('statMemory').textContent     = data.memory_entries ?? '–';
    document.getElementById('statExchanges').textContent  = data.exchange_count ?? '–';
    syncModelSelects(data.model, document.getElementById('modelSelect'));
    // TTS
    const cfg = data.config || {};
    if (cfg.tts_engine) {
      const sel = document.getElementById('ttsEngine');
      if (sel) { sel.value = cfg.tts_engine; if (!sel.value) sel.value = 'off'; }
    }
    if (cfg.tts_voice !== undefined) {
      const inp = document.getElementById('ttsVoice');
      if (inp) inp.value = cfg.tts_voice || '';
    }
    // Model fallback
    if (cfg.model_fallback && Array.isArray(cfg.model_fallback)) {
      const inp = document.getElementById('modelFallbackInput');
      if (inp) inp.value = cfg.model_fallback.join(', ');
    }
    // Cost optimization settings
    {
      const cmInp = document.getElementById('checkModelInput');
      if (cmInp) cmInp.value = cfg.check_model || '';
      const mhInp = document.getElementById('maxHistoryInput');
      if (mhInp) mhInp.value = cfg.max_history_turns != null ? cfg.max_history_turns : '';
    }
    // Thinking Level
    _renderThinkingSettings(cfg);
    // Channel Allowlist
    _renderAllowlistSettings(cfg);
    // Claude CLI status
    _loadClaudeCliStatus();
    try {
      const pd = await (await fetch('/api/plugins')).json();
      document.getElementById('statPlugins').textContent = (pd.plugins || []).filter(p => p.loaded).length;
      document.getElementById('statTools').textContent   = pd.total_loaded ?? '–';
    } catch {}
    // Load providers + build dynamic model dropdown + routing dropdowns
    try {
      const pv = await (await fetch('/api/providers')).json();
      _renderProviders(pv);
      _buildModelDropdown(pv);
      _buildRoutingDropdowns(pv, cfg.task_routing || {}, cfg.check_model || '');
    } catch {}
    loadCustomProviders();
  } catch {}
  if (window.lucide) lucide.createIcons();
}

function _renderProviders(pv) {
  const el = document.getElementById('providerList');
  if (!el) return;
  const rows = (pv.providers || []).map(p => {
    const badge = p.default
      ? '<span style="font-size:10px;color:var(--text3);margin-left:6px">default</span>'
      : '<span style="font-size:10px;color:var(--green);margin-left:6px">✓ active</span>';
    const modelCount = p.models?.length ? `<span style="font-size:10px;color:var(--text3);margin-left:4px">${p.models.length} models</span>` : '';
    return `<div style="display:flex;align-items:center;gap:5px;font-size:12px;color:var(--text)">
      <i data-lucide="cpu" style="width:12px;height:12px;stroke-width:1.75;flex-shrink:0"></i><span>${esc(p.label)}</span>${modelCount}${badge}
    </div>`;
  });
  el.innerHTML = rows.join('') || '<span style="font-size:11px;color:var(--text3)">No providers registered</span>';
  if (window.lucide) lucide.createIcons({rootNode: el});
}

function _buildModelDropdown(pv) {
  const sel = document.getElementById('settingsModel');
  if (!sel) return;
  const active = pv.active_model || '';
  sel.innerHTML = '';
  for (const p of (pv.providers || [])) {
    if (!p.models?.length) continue;
    const grp = document.createElement('optgroup');
    grp.label = `── ${p.label} ──`;
    for (const m of p.models) {
      const opt = document.createElement('option');
      opt.value = m; opt.textContent = m;
      if (m === active) opt.selected = true;
      grp.appendChild(opt);
    }
    sel.appendChild(grp);
  }
  // If active model not in list, add it
  let found = false;
  for (const opt of sel.options) { if (opt.value === active) { found = true; break; } }
  if (!found && active) {
    const opt = document.createElement('option');
    opt.value = active; opt.textContent = active; opt.selected = true;
    sel.prepend(opt);
  }
  syncModelSelects(active, document.getElementById('modelSelect'));
}

function _buildRoutingDropdowns(pv, routing, checkModel) {
  const fields = {
    routingCoding:   {key: 'coding',   placeholder: 'claude-opus-4-6'},
    routingReview:   {key: 'review',   placeholder: 'claude-sonnet-4-6'},
    routingBrowsing: {key: 'browsing', placeholder: 'gemini-2.5-flash'},
    routingDefault:  {key: 'default',  placeholder: 'gemini-2.5-pro'},
  };
  const groups = (pv.providers || []).filter(p => p.models?.length);
  for (const [id, info] of Object.entries(fields)) {
    const sel = document.getElementById(id);
    if (!sel) continue;
    const cur = (routing || {})[info.key] || '';
    sel.innerHTML = `<option value="">— ${info.placeholder} (Standard) —</option>`;
    for (const p of groups) {
      const grp = document.createElement('optgroup');
      grp.label = p.label;
      for (const m of p.models) {
        const opt = document.createElement('option');
        opt.value = m; opt.textContent = m;
        if (m === cur) opt.selected = true;
        grp.appendChild(opt);
      }
      sel.appendChild(grp);
    }
    // Falls gespeichertes Modell nicht in der Liste, trotzdem anzeigen
    if (cur && !Array.from(sel.options).some(o => o.value === cur)) {
      const opt = document.createElement('option');
      opt.value = cur; opt.textContent = cur; opt.selected = true;
      sel.appendChild(opt);
    }
  }
  // Check model dropdown
  const chkSel = document.getElementById('routingCheck');
  if (chkSel) {
    const cur = checkModel || '';
    chkSel.innerHTML = '<option value="">— auto (cheapest) —</option>';
    for (const p of groups) {
      const grp = document.createElement('optgroup');
      grp.label = p.label;
      for (const m of p.models) {
        const opt = document.createElement('option');
        opt.value = m; opt.textContent = m;
        if (m === cur) opt.selected = true;
        grp.appendChild(opt);
      }
      chkSel.appendChild(grp);
    }
    if (cur && !Array.from(chkSel.options).some(o => o.value === cur)) {
      const opt = document.createElement('option');
      opt.value = cur; opt.textContent = cur; opt.selected = true;
      chkSel.appendChild(opt);
    }
  }
}

async function loadCustomProviders() {
  const el = document.getElementById('customProviderList');
  if (!el) return;
  try {
    const d = await (await fetch('/api/custom-providers')).json();
    const list = d.providers || [];
    if (!list.length) { el.innerHTML = ''; return; }
    el.innerHTML = list.map(p => `
      <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--bg4);border-radius:7px;border:1px solid var(--border)">
        <i data-lucide="plug" style="width:12px;height:12px;stroke-width:1.75;color:var(--text3);flex-shrink:0"></i>
        <span style="flex:1;font-size:12px;color:var(--text)">${esc(p.name)}</span>
        <span style="font-size:11px;color:var(--text3);font-family:monospace">${esc(p.base_url)}</span>
        <span style="font-size:10px;color:var(--text3)">${p.models?.length || 0} Modelle</span>
        <button class="action-btn" style="padding:3px 8px;font-size:10px" onclick="deleteCustomProvider('${esc(p.name)}')">✕</button>
      </div>`).join('');
    if (window.lucide) lucide.createIcons({rootNode: el});
  } catch {}
}

async function saveCustomProvider() {
  const name    = (document.getElementById('cpName')?.value    || '').trim();
  const baseUrl = (document.getElementById('cpBaseUrl')?.value || '').trim();
  const apiEnv  = (document.getElementById('cpApiEnv')?.value  || '').trim().toUpperCase();
  const models  = (document.getElementById('cpModels')?.value  || '').trim();
  const status  = document.getElementById('cpStatus');
  if (!name || !baseUrl || !models) {
    if (status) { status.style.color='var(--red)'; status.textContent='Name, Base URL und Modelle sind Pflicht'; }
    return;
  }
  try {
    const r = await fetch('/api/custom-providers', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ name, base_url: baseUrl, api_key_env: apiEnv, models }),
    });
    const d = await r.json();
    if (d.ok) {
      showToast(`✓ Provider "${name}" hinzugefügt`);
      if (status) { status.style.color='var(--green)'; status.textContent='✓ gespeichert'; setTimeout(()=>{ if(status) status.textContent=''; }, 3000); }
      ['cpName','cpBaseUrl','cpApiEnv','cpModels'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
      loadCustomProviders();
      refreshProviderModels();
    } else {
      if (status) { status.style.color='var(--red)'; status.textContent=d.error||'Fehler'; }
    }
  } catch(e) { if (status) { status.style.color='var(--red)'; status.textContent=e.message; } }
}

async function deleteCustomProvider(name) {
  if (!confirm(`Provider "${name}" wirklich entfernen?`)) return;
  try {
    await fetch(`/api/custom-providers/${encodeURIComponent(name)}`, { method: 'DELETE' });
    showToast(`✓ Provider "${name}" entfernt`);
    loadCustomProviders();
    refreshProviderModels();
  } catch(e) { showToast('✗ ' + e.message, true); }
}

async function refreshProviderModels() {
  const btn = document.getElementById('refreshModelsBtn');
  if (btn) btn.disabled = true;
  try {
    const pv = await (await fetch('/api/providers')).json();
    _renderProviders(pv);
    _buildModelDropdown(pv);
    // Routing-Dropdowns mit aktuellen gespeicherten Werten neu befüllen
    const cfg = await (await fetch('/api/config')).json();
    _buildRoutingDropdowns(pv, (cfg.config || {}).task_routing || {}, (cfg.config || {}).check_model || '');
    showToast('✓ Modelle aktualisiert');
  } catch(e) { showToast('✗ ' + e.message); }
  finally { if (btn) btn.disabled = false; }
}

async function saveModelFromSettings() {
  const custom = (document.getElementById('settingsModelCustom')?.value || '').trim();
  const model  = custom || document.getElementById('settingsModel').value;
  if (!model) return;
  if (custom) document.getElementById('settingsModelCustom').value = '';
  await applyModel(model);
  syncModelSelects(model, document.getElementById('modelSelect'));
  // Refresh providers to update active model display
  try { const pv = await (await fetch('/api/providers')).json(); _buildModelDropdown(pv); } catch {}
}

async function saveModel() {
  const model = document.getElementById('modelSelect').value;
  await applyModel(model);
  syncModelSelects(model, document.getElementById('settingsModel'));
}

async function applyModel(model) {
  try {
    const d = await (await fetch('/api/model', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({model})})).json();
    if (d.ok) showToast('✓ Modell: ' + model); else showToast('✗ ' + (d.error||'?'));
  } catch(e) { showToast('✗ ' + e.message); }
}

async function resetExchanges() {
  if (!confirm('Gesprächszähler zurücksetzen?')) return;
  try {
    const d = await (await fetch('/api/config/reset_exchanges', {method:'POST'})).json();
    if (d.ok) { showToast('✓ Zähler zurückgesetzt'); loadSettings(); }
  } catch {}
}

// ═══════════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════════
function esc(s)      { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function fmtJson(o)  { try{return JSON.stringify(o,null,2)}catch{return String(o)} }
function icon(name, size=13) {
  return `<i data-lucide="${name}" style="width:${size}px;height:${size}px;display:inline-flex;align-items:center;flex-shrink:0;stroke-width:1.75"></i>`;
}
function toolIcon(n) { return icon(TOOL_ICONS[n] || 'square'); }
function pluginIcon(n) { return icon(PLUGIN_ICONS[n] || 'puzzle', 14); }
function autoResize(el) { el.style.height='auto'; el.style.height=Math.min(el.scrollHeight,130)+'px'; }
function scrollChat()   { const m=document.getElementById('messages'); m.scrollTop=m.scrollHeight; }
function showToast(msg) { const t=document.getElementById('toast'); t.textContent=msg; t.classList.add('show'); setTimeout(()=>t.classList.remove('show'),2500); }

function highlightJSON(jsonStr) {
  if (!jsonStr) return '';
  return esc(jsonStr).replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
    m => { let c='json-number'; if(/^"/.test(m)) c=/:$/.test(m)?'json-key':'json-string'; else if(/true|false/.test(m)) c='json-boolean'; else if(/null/.test(m)) c='json-null'; return `<span class="${c}">${m}</span>`; }
  );
}

function renderMd(text) {
  let s = text;
  s = s.replace(/```[\w]*\n([\s\S]*?)```/g, (_,c) => `<pre><code>${esc(c.trimEnd())}</code></pre>`);
  s = s.replace(/`([^`\n]+)`/g, (_,c) => `<code>${esc(c)}</code>`);
  s = s.replace(/\*\*\*(.+?)\*\*\*/g,'<strong><em>$1</em></strong>');
  s = s.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  s = s.replace(/\*(.+?)\*/g,'<em>$1</em>');
  s = s.replace(/^### (.+)$/gm,'<h3>$1</h3>');
  s = s.replace(/^## (.+)$/gm,'<h2>$1</h2>');
  s = s.replace(/^# (.+)$/gm,'<h1>$1</h1>');
  s = s.replace(/((?:^[ \t]*[-*+] .+\n?)+)/gm, b => `<ul>${b.trim().split('\n').map(l=>`<li>${l.replace(/^[ \t]*[-*+] /,'')}</li>`).join('')}</ul>`);
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank">$1</a>');
  s = s.replace(/\n\n/g,'</p><p>').replace(/\n/g,'<br>');
  return `<p>${s}</p>`;
}

// ═══════════════════════════════════════════════════════════════════
// CHAT HELPERS
// ═══════════════════════════════════════════════════════════════════
function removeWelcome() { const w=document.getElementById('welcome'); if(w)w.remove(); }

function appendUserMsg(text) {
  removeWelcome();
  const m=document.getElementById('messages'), d=document.createElement('div');
  d.className='msg user';
  d.innerHTML=`<div class="msg-label">Du</div>
    <div class="msg-bubble">${esc(text)}</div>
    <div class="msg-actions"><button class="copy-btn" onclick="copyMsg(this)">⎘ Kopieren</button></div>`;
  m.appendChild(d); scrollChat();
}

function appendAionBubble() {
  const m=document.getElementById('messages'), d=document.createElement('div');
  d.className='msg aion';
  const id='bubble-'+Date.now()+'-'+Math.random().toString(36).slice(2);
  d.innerHTML=`<div class="msg-label">AION</div>
    <div class="msg-bubble streaming mood-${_currentMood}" id="${id}"></div>
    <div class="msg-actions"><button class="copy-btn" onclick="copyMsg(this)">⎘ Kopieren</button></div>`;
  m.appendChild(d); scrollChat();
  return document.getElementById(id);
}

function finalizeCurrentBubble() {
  if (!currentBubble) return;
  currentBubble.classList.remove('streaming');
  if (currentBubble.dataset.raw) currentBubble.innerHTML = renderMd(currentBubble.dataset.raw);
  else { const w=currentBubble.closest('.msg'); if(w)w.remove(); }
  currentBubble = null;
  loadMood();
}

function appendApprovalButtons() {
  const bar = document.createElement('div');
  bar.className = 'approval-bar';
  bar.id = 'approvalBar';
  bar.innerHTML = `
    <span class="approval-bar-label">Warte auf Bestätigung</span>
    <button class="approval-btn confirm" onclick="sendApproval(true)">Bestätigen</button>
    <button class="approval-btn cancel"  onclick="sendApproval(false)">Abbrechen</button>`;
  document.getElementById('messages').appendChild(bar);
  scrollChat();
}

function sendApproval(confirmed) {
  const bar = document.getElementById('approvalBar');
  if (bar) {
    bar.querySelectorAll('.approval-btn').forEach(b => b.disabled = true);
    bar.querySelector('.approval-bar-label').textContent = confirmed ? 'Bestätigt ✓' : 'Abgebrochen';
  }
  // isThinking zurücksetzen: Stream ist nach approval-Event beendet,
  // aber das Flag könnte noch gesetzt sein → send() würde sonst früh abbrechen
  isThinking = false;
  const input = document.getElementById('input');
  input.value = confirmed ? 'ja' : 'nein';
  send();
}

function appendHistoryAionMsg(text) {
  removeWelcome();
  const m=document.getElementById('messages'), d=document.createElement('div');
  d.className='msg aion history';
  d.innerHTML=`<div class="msg-label">AION</div>
    <div class="msg-bubble mood-${_currentMood}">${renderMd(text)}</div>
    <div class="msg-actions"><button class="copy-btn" onclick="copyMsg(this)">⎘ Kopieren</button></div>`;
  m.appendChild(d);
}

function appendImageBlock(url) {
  const m=document.getElementById('messages'), d=document.createElement('div');
  d.className='msg aion';
  d.innerHTML=`<div class="msg-label">AION</div><div class="msg-bubble" style="padding:6px"><img src="${esc(url)}" alt="Bild" style="max-width:100%;max-height:400px;border-radius:8px;display:block;cursor:pointer" onclick="window.open('${esc(url)}','_blank')" onerror="this.closest('.msg').remove()"></div>`;
  m.appendChild(d); scrollChat();
}

function appendAudioBlock(url, format) {
  const mime = format === 'wav' ? 'audio/wav' : format === 'ogg' ? 'audio/ogg' : 'audio/mpeg';
  const m = document.getElementById('messages'), d = document.createElement('div');
  d.className = 'msg aion';
  d.innerHTML = `<div class="msg-label">AION</div>
    <div class="msg-bubble" style="padding:10px 12px;min-width:280px">
      <div style="font-size:11px;color:var(--text3);margin-bottom:6px">🔊 Sprachnachricht</div>
      <audio controls style="width:100%;max-width:360px;border-radius:6px;outline:none;display:block">
        <source src="${esc(url)}" type="${esc(mime)}">
        <a href="${esc(url)}" download style="color:var(--text2);font-size:11px">Audio herunterladen</a>
      </audio>
    </div>`;
  m.appendChild(d); scrollChat();
}

function copyMsg(btn) {
  const bubble = btn.closest('.msg').querySelector('.msg-bubble');
  if (!bubble) return;
  const text = bubble.innerText || bubble.textContent;
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = '✓ Kopiert';
    setTimeout(() => btn.textContent = orig, 1500);
  }).catch(() => showToast('Kopieren fehlgeschlagen'));
}

// ═══════════════════════════════════════════════════════════════════
// INLINE ACCORDIONS (Thoughts & Tools)
// ═══════════════════════════════════════════════════════════════════
function toggleAcc(hdr) { hdr.parentElement.classList.toggle('open'); }

function showThinkingRow() {
  if (document.getElementById('thinkingRow')) return;
  const d = document.createElement('div');
  d.className = 'inline-thinking'; d.id = 'thinkingRow';
  d.innerHTML = '<div class="spinner"></div><span style="font-size:11px">denkt…</span>';
  document.getElementById('messages').appendChild(d);
  scrollChat();
}
function hideThinkingRow() { const e=document.getElementById('thinkingRow'); if(e)e.remove(); }

function appendInlineThought(text, trigger) {
  hideThinkingRow();
  const preview = text.replace(/\n/g,' ').slice(0, 70) + (text.length > 70 ? '…' : '');
  const d = document.createElement('div');
  d.className = 'inline-acc thought-acc';
  d.innerHTML = `
    <div class="inline-acc-hdr" onclick="toggleAcc(this)">
      <span class="iacc-icon">${icon('brain')}</span>
      <span class="iacc-preview">${esc(preview)}</span>
      ${trigger ? `<span class="iacc-badge">${esc(trigger)}</span>` : ''}
      <span class="iacc-toggle">▶</span>
    </div>
    <div class="inline-acc-body">
      <div class="thought-body-text">${esc(text)}</div>
    </div>`;
  document.getElementById('messages').appendChild(d);
  if (window.lucide) lucide.createIcons({rootNode: d});
  scrollChat();
}

function appendInlineTool(callId, toolName, args) {
  if (toolName === 'reflect') return;
  hideThinkingRow();
  toolDataStore[callId] = { name: toolName, args, result: null, status: 'running' };
  const d = document.createElement('div');
  d.className = 'inline-acc tool-acc running'; d.id = `tacc-${callId}`;
  const argsStr = fmtJson(args);
  d.innerHTML = `
    <div class="inline-acc-hdr" onclick="toggleAcc(this)">
      <span class="iacc-icon">${toolIcon(toolName)}</span>
      <span class="iacc-name">${esc(toolName)}</span>
      <span style="flex:1"></span>
      <span class="iacc-status running" id="tstat-${callId}"><span class="mini-spinner"></span></span>
      <button class="iacc-detail-btn" onclick="event.stopPropagation();openModal('${callId}')" title="Vollbild">⬜</button>
      <span class="iacc-toggle">▶</span>
    </div>
    <div class="inline-acc-body">
      <div class="iacc-section-label">Eingabe</div>
      <div class="iacc-code">${highlightJSON(argsStr)}</div>
      <div class="iacc-section-label">Ergebnis</div>
      <div class="iacc-code result" id="taccr-${callId}"><span style="color:var(--text3);font-style:italic">läuft…</span></div>
    </div>`;
  document.getElementById('messages').appendChild(d);
  if (window.lucide) lucide.createIcons({rootNode: d});
  scrollChat();
}

function updateInlineTool(callId, result, ok) {
  if (!toolDataStore[callId]) return;
  toolDataStore[callId].result = result; toolDataStore[callId].status = ok ? 'ok' : 'err';
  const acc  = document.getElementById(`tacc-${callId}`);
  const stat = document.getElementById(`tstat-${callId}`);
  const res  = document.getElementById(`taccr-${callId}`);
  if (acc)  { acc.classList.remove('running'); acc.classList.add(ok ? 'ok' : 'err'); }
  if (stat) { stat.className = `iacc-status ${ok ? 'ok' : 'err'}`; stat.textContent = ok ? '✓' : '✗'; }
  if (res) {
    const resultStr = typeof result === 'string' ? result : fmtJson(result);
    const preview = resultStr.length > 400 ? resultStr.slice(0, 400) + '\n…' : resultStr;
    res.innerHTML = highlightJSON(preview);
  }
  if (currentModalCallId === callId) openModal(callId);
}

// ═══════════════════════════════════════════════════════════════════
// MODAL
// ═══════════════════════════════════════════════════════════════════
function openModal(callId) {
  const data = toolDataStore[callId]; if (!data) return;
  currentModalCallId = callId;
  const sc  = data.status==='running' ? 'var(--text2)' : (data.status==='ok' ? 'var(--green)' : 'var(--red)');
  const sh  = data.status==='running' ? '<span class="mini-spinner"></span>' : (data.status==='ok' ? '✓' : '✗');
  document.getElementById('modalTitle').innerHTML  = `${toolIcon(data.name)} ${esc(data.name)} <span style="color:${sc};font-size:16px;margin-left:5px">${sh}</span>`;
  document.getElementById('modalInput').innerHTML  = highlightJSON(fmtJson(data.args));
  document.getElementById('modalResult').innerHTML = data.status==='running'
    ? '<span style="color:var(--text3);font-style:italic">Wird ausgeführt…</span>'
    : highlightJSON(fmtJson(data.result));
  document.getElementById('toolModal').classList.add('show');
}
function closeModal(e) {
  if (!e || e.target.id==='toolModal') { document.getElementById('toolModal').classList.remove('show'); currentModalCallId=null; }
}

// ═══════════════════════════════════════════════════════════════════
// SEND / EVENTS
// ═══════════════════════════════════════════════════════════════════
function setThinking(active) {
  isThinking = active;
  document.getElementById('statusDot').className = 'status-dot' + (active ? ' thinking' : '');
  document.getElementById('sendBtn').style.display = active ? 'none' : '';
  document.getElementById('stopBtn').style.display = active ? '' : 'none';
  const detachBtn = document.getElementById('detachBtn');
  if (detachBtn) detachBtn.disabled = !active;
  document.getElementById('input').disabled = active;
  if (!active) { _detachMode = false; }
}

function detachTask() {
  if (!isThinking || _detachMode) return;
  _detachMode = true;

  // Tool-Akkordeons der laufenden Antwort ins Panel verschieben
  const panel = document.getElementById('detachPanel');
  const body  = document.getElementById('detachBody');
  body.innerHTML = '';
  document.querySelectorAll('.inline-acc.tool-acc').forEach(el => body.appendChild(el));

  panel.style.display = 'block';
  document.getElementById('detachTitle').textContent = '⚙ Aufgabe läuft…';
  document.getElementById('detachStatus').textContent = 'läuft…';

  // Input freigeben — User kann jetzt chatten
  document.getElementById('input').disabled = false;
  document.getElementById('sendBtn').style.display = '';
  document.getElementById('stopBtn').style.display = 'none';
  const db = document.getElementById('detachBtn'); if (db) db.disabled = true;
}

function closeDetachPanel() {
  document.getElementById('detachPanel').style.display = 'none';
}

let _abortCtrl = null;
async function stopGeneration() {
  if (_abortCtrl) { _abortCtrl.abort(); _abortCtrl = null; }
  try { await fetch('/api/stop', {method:'POST'}); } catch {}
  if (currentBubble) {
    currentBubble.classList.remove('streaming');
    finalizeCurrentBubble();
    currentBubble = null;
  }
  hideThinkingRow();
  setThinking(false);
}

let pendingImages = [];   // base64 data-URLs
let pendingTextFiles = []; // {name, content}

// File types processed server-side (text extracted, then included as context)
const SERVER_PROCESSABLE = ['.pdf','.docx','.doc','.xlsx','.xls',
                             '.ogg','.mp3','.wav','.m4a','.flac','.aac','.opus','.weba'];
// File types that no one can process yet → tell AION, let it suggest a solution
const TRULY_UNSUPPORTED  = ['.mp4','.mov','.avi','.mkv','.webm','.zip','.rar','.7z','.exe','.dmg','.iso'];

function _fileExt(f) { return '.' + f.name.split('.').pop().toLowerCase(); }

function onFileSelected(e) {
  const files = Array.from(e.target.files);
  e.target.value = '';
  files.forEach(f => {
    const ext = _fileExt(f);

    if (TRULY_UNSUPPORTED.includes(ext)) {
      // Tell AION about the file so it can suggest a processing strategy
      const sizeMb = (f.size / 1_048_576).toFixed(1);
      const msg = `[Datei-Upload] Ich habe die Datei "${f.name}" (${sizeMb} MB, Format: ${ext}) erhalten, kann sie aber noch nicht verarbeiten. Überlege, wie du diesen Dateityp unterstützen könntest – erstelle ggf. ein Plugin dafür.`;
      document.getElementById('input').value = msg;
      showToast(`📥 ${f.name} — AION wird nach einer Lösung gefragt`);
      return;
    }

    if (f.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = ev => { pendingImages.push(ev.target.result); renderAttachPreview(); };
      reader.readAsDataURL(f);
      return;
    }

    if (SERVER_PROCESSABLE.includes(ext)) {
      _processFileOnServer(f);
      return;
    }

    // Plain text / code files → read directly
    const reader = new FileReader();
    reader.onload = ev => { pendingTextFiles.push({name: f.name, content: ev.target.result}); renderAttachPreview(); };
    reader.readAsText(f);
  });
}

async function _processFileOnServer(f) {
  const placeholder = {name: f.name, content: `[Verarbeite ${f.name}…]`};
  pendingTextFiles.push(placeholder);
  renderAttachPreview();
  try {
    const fd = new FormData();
    fd.append('file', f);
    const r = await fetch('/api/process_file', {method: 'POST', body: fd});
    const d = await r.json();
    const idx = pendingTextFiles.indexOf(placeholder);
    if (d.ok) {
      pendingTextFiles[idx] = {name: f.name, content: d.text};
      showToast(`✓ ${f.name} verarbeitet`);
    } else {
      pendingTextFiles.splice(idx, 1);
      // Tell AION about the failure so it can suggest a fix
      const hint = d.hint || d.error || 'unbekannter Fehler';
      const msg  = `[Datei-Upload] Ich habe versucht "${f.name}" zu verarbeiten, bin aber gescheitert: ${hint}. Was kann ich tun?`;
      document.getElementById('input').value = msg;
      showToast(`⚠ ${f.name}: ${d.error}`, true);
    }
    renderAttachPreview();
  } catch(err) {
    showToast(`Fehler beim Verarbeiten: ${err}`, true);
    pendingTextFiles.splice(pendingTextFiles.indexOf(placeholder), 1);
    renderAttachPreview();
  }
}

function onPaste(e) {
  const items = e.clipboardData && e.clipboardData.items;
  if (!items) return;
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      e.preventDefault();
      const reader = new FileReader();
      reader.onload = ev => { pendingImages.push(ev.target.result); renderAttachPreview(); };
      reader.readAsDataURL(item.getAsFile());
    }
  }
}

function renderAttachPreview() {
  const el = document.getElementById('attachPreview');
  el.innerHTML = '';
  pendingImages.forEach((src, i) => {
    const wrap = document.createElement('div'); wrap.className = 'attach-thumb';
    const img = document.createElement('img'); img.src = src;
    const rm = document.createElement('button'); rm.className = 'remove-attach'; rm.textContent = '×';
    rm.onclick = () => { pendingImages.splice(i, 1); renderAttachPreview(); };
    wrap.append(img, rm); el.appendChild(wrap);
  });
  pendingTextFiles.forEach((f, i) => {
    const chip = document.createElement('div'); chip.className = 'attach-file-chip';
    chip.innerHTML = `📄 ${esc(f.name)} <button onclick="pendingTextFiles.splice(${i},1);renderAttachPreview()">×</button>`;
    el.appendChild(chip);
  });
  el.style.display = (pendingImages.length || pendingTextFiles.length) ? 'flex' : 'none';
}

function clearAttachments() {
  pendingImages = []; pendingTextFiles = [];
  const el = document.getElementById('attachPreview');
  if (el) { el.innerHTML = ''; el.style.display = 'none'; }
}

async function send() {
  const input = document.getElementById('input');
  let text  = input.value.trim();
  if (!text && !pendingImages.length && !pendingTextFiles.length) return;

  // Im Detach-Modus: Nachricht in Queue statt sofort senden
  if (_detachMode) {
    if (!text) return;
    const imgs = pendingImages.length ? [...pendingImages] : null;
    input.value = ''; autoResize(input); clearAttachments();
    _detachQueue.push({text, imgs});
    showToast(`⏳ Gequeuet (${_detachQueue.length}): ${text.slice(0, 40)}${text.length > 40 ? '…' : ''}`);
    return;
  }

  if (isThinking) return;
  // Remove any pending approval bar when user sends a new message
  const oldBar = document.getElementById('approvalBar');
  if (oldBar) oldBar.remove();
  // Append text file contents to message
  if (pendingTextFiles.length) {
    const fileContext = pendingTextFiles.map(f => `\`\`\`${f.name}\n${f.content}\n\`\`\``).join('\n\n');
    text = text ? text + '\n\n' + fileContext : fileContext;
  }
  const imgs = pendingImages.length ? [...pendingImages] : null;
  input.value = ''; autoResize(input);
  clearAttachments();
  // Switch to chat if on another section
  if (currentSection !== 'chat') switchSection('chat');
  appendUserMsg(text); setThinking(true);
  hideThinkingRow(); showThinkingRow();
  currentBubble = appendAionBubble(); awaitingNewBubble = false;
  _abortCtrl = new AbortController();
  try {
    const body = {message: text};
    if (imgs) body.images = imgs;
    const resp   = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body), signal: _abortCtrl.signal});
    const reader = resp.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
    while (true) {
      const {done, value} = await reader.read(); if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const lines = buffer.split('\n'); buffer = lines.pop();
      for (const line of lines) { if (!line.startsWith('data: ')) continue; try { handleEvent(JSON.parse(line.slice(6))); } catch {} }
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      // Nutzer hat gestoppt — kein Fehler anzeigen, Bubble bereits in stopGeneration() finalisiert
    } else if (currentBubble) {
      currentBubble.classList.remove('streaming');
      currentBubble.innerHTML=`<span style="color:var(--red)">Verbindungsfehler: ${esc(err.message)}</span>`;
      currentBubble=null;
    }
  }
  _abortCtrl = null;
  setThinking(false);
}

// ── Token tracking ────────────────────────────────────────────────────────────
let _lastUsage    = null;   // {in, out} des letzten Turns
let _sessionTokens = {in: 0, out: 0};
function fmtTok(n) { return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n || 0); }

function handleEvent(ev) {
  switch (ev.type) {
    case 'thought':
      hideThinkingRow();
      if (currentBubble) { finalizeCurrentBubble(); awaitingNewBubble = true; }
      appendInlineThought(ev.text, ev.trigger);
      break;
    case 'token':
      hideThinkingRow();
      if (awaitingNewBubble) { currentBubble = appendAionBubble(); awaitingNewBubble = false; }
      if (!currentBubble) { currentBubble = appendAionBubble(); }
      currentBubble.dataset.raw = (currentBubble.dataset.raw || '') + ev.content;
      currentBubble.textContent = currentBubble.dataset.raw;
      currentBubble.classList.add('streaming');
      scrollChat();
      break;
    case 'tool_call':
      hideThinkingRow();
      if (_detachMode) {
        appendInlineTool(ev.call_id, ev.tool, ev.args);
        // Neues Tool-Element direkt ins Panel verschieben
        const newEl = document.getElementById(`tacc-${ev.call_id}`);
        if (newEl) document.getElementById('detachBody').appendChild(newEl);
      } else {
        if (currentBubble) { finalizeCurrentBubble(); awaitingNewBubble = true; }
        appendInlineTool(ev.call_id, ev.tool, ev.args);
      }
      break;
    case 'tool_result':
      updateInlineTool(ev.call_id, ev.result, ev.ok);
      if (!_detachMode) showThinkingRow();
      break;
    case 'progress': {
      const pct   = ev.percent || 0;
      const label = ev.label   || (pct + '%');
      const bar   = document.getElementById('detachProgressBar');
      const lbl   = document.getElementById('detachProgressLabel');
      const wrap  = document.getElementById('detachProgressWrap');
      if (bar) { bar.style.width = pct + '%'; }
      if (lbl) { lbl.textContent = label; }
      if (wrap) { wrap.style.display = 'block'; }
      // Auch wenn noch nicht detached: Fortschritt im Tool-Akkordeon anzeigen
      const toolEl = document.getElementById(`tacc-${ev.call_id}`);
      if (toolEl) {
        let pb = toolEl.querySelector('.tool-progress-bar-wrap');
        if (!pb) {
          pb = document.createElement('div');
          pb.className = 'tool-progress-bar-wrap';
          pb.innerHTML = `<div class="tool-progress-bar"></div><span class="tool-progress-label"></span>`;
          toolEl.appendChild(pb);
        }
        pb.querySelector('.tool-progress-bar').style.width = pct + '%';
        pb.querySelector('.tool-progress-label').textContent = label;
      }
      break;
    }
    case 'approval':
      hideThinkingRow(); finalizeCurrentBubble();
      appendApprovalButtons();
      awaitingNewBubble = false;
      break;
    case 'usage':
      _lastUsage = {in: ev.input_tokens || 0, out: ev.output_tokens || 0, est: !!ev.estimated};
      _sessionTokens.in  += _lastUsage.in;
      _sessionTokens.out += _lastUsage.out;
      break;
    case 'done':
      hideThinkingRow();
      if (_detachMode) {
        // Finale Antwort in den Haupt-Chat schreiben
        if (ev.full_response) {
          const bubble = appendAionBubble();
          bubble.dataset.raw = ev.full_response;
          renderMarkdown(bubble, ev.full_response);
          bubble.classList.remove('streaming');
        }
        // Panel: "Fertig" anzeigen, dann ausblenden
        document.getElementById('detachTitle').textContent = '✓ Fertig';
        document.getElementById('detachStatus').textContent = 'Aufgabe abgeschlossen';
        setTimeout(() => {
          const p = document.getElementById('detachPanel');
          if (p) p.style.display = 'none';
          document.getElementById('detachProgressWrap').style.display = 'none';
        }, 3000);
        _detachMode = false;
        setThinking(false);
        // Queue-Nachricht senden
        if (_detachQueue.length) {
          const next = _detachQueue.shift();
          setTimeout(() => _sendQueued(next), 200);
        }
      } else {
        finalizeCurrentBubble();
        if (!ev.approval_pending) { const oldBar = document.getElementById('approvalBar'); if (oldBar) oldBar.remove(); }
        if (ev.response_blocks) for (const b of ev.response_blocks) {
          if (b.type==='image' && b.url) appendImageBlock(b.url);
          if (b.type==='audio' && b.url) appendAudioBlock(b.url, b.format);
        }
      }
      // Token-Badge unter der letzten Antwort
      if (_lastUsage) {
        const badge = document.createElement('div');
        badge.className = 'token-badge';
        const est = _lastUsage.est ? '~' : '';
        badge.textContent = `↳ in: ${est}${fmtTok(_lastUsage.in)}  out: ${est}${fmtTok(_lastUsage.out)}  ·  session: ${fmtTok(_sessionTokens.in)} / ${fmtTok(_sessionTokens.out)}`;
        const msgs = document.getElementById('messages');
        const aionMsgs = msgs.querySelectorAll('.msg.aion');
        const lastMsg = aionMsgs[aionMsgs.length - 1];
        if (lastMsg) lastMsg.appendChild(badge);
        _lastUsage = null;
      }
      awaitingNewBubble = false; scrollChat();
      break;
    case 'error':
      hideThinkingRow();
      if (currentBubble) { currentBubble.classList.remove('streaming'); currentBubble.innerHTML=`<span style="color:var(--red)">Fehler: ${esc(ev.message||'?')}</span>`; currentBubble=null; }
      break;
  }
}

// Gequeuete Nachricht senden (nach Detach-Task-Abschluss)
async function _sendQueued({text, imgs}) {
  const input = document.getElementById('input');
  input.value = text;
  pendingImages = imgs || [];
  await send();
}

async function resetChat() {
  try { await fetch('/api/reset', {method:'POST'}); } catch {}
  for (let k in toolDataStore) delete toolDataStore[k];
  currentBubble = null; awaitingNewBubble = false;
  _sessionTokens = {in: 0, out: 0}; _lastUsage = null;
  switchSection('chat');
  document.getElementById('messages').innerHTML = `
    <div class="welcome" id="welcome">
      <div class="welcome-icon">◈</div><h2>AION</h2>
      <p>Conversation reset.</p>
      <div class="chips">
        <div class="chip" onclick="useChip(this)">What can you do?</div>
        <div class="chip" onclick="useChip(this)">Find latest AI news</div>
        <div class="chip" onclick="useChip(this)">Show me your source code</div>
        <div class="chip" onclick="useChip(this)">What system runs here?</div>
      </div>
    </div>`;
}

function useChip(el) { document.getElementById('input').value = el.textContent; send(); }
function onKey(e) { if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); send(); } }

// ── TTS SETTINGS ──────────────────────────────────────────────────────────────
async function saveTTSSettings() {
  const engine = document.getElementById('ttsEngine')?.value;
  const voice  = document.getElementById('ttsVoice')?.value?.trim();
  try {
    const r = await fetch('/api/config/settings', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ tts_engine: engine, tts_voice: voice }),
    });
    const d = await r.json();
    if (d.ok) showToast('✓ TTS gespeichert');
    else showToast('✗ ' + (d.error || 'Fehler'));
  } catch(e) { showToast('✗ ' + e.message); }
}

// ── KI-KOSTEN OPTIMIEREN ───────────────────────────────────────────────────────
async function saveCostSettings() {
  const checkModel   = (document.getElementById('checkModelInput')?.value || '').trim();
  const maxHistory   = parseInt(document.getElementById('maxHistoryInput')?.value || '', 10);
  const payload = {};
  payload.check_model       = checkModel;
  if (!isNaN(maxHistory) && maxHistory >= 5) payload.max_history_turns = maxHistory;
  try {
    const r = await fetch('/api/config/settings', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const d = await r.json();
    const el = document.getElementById('costSettingsSaveStatus');
    if (d.ok) {
      if (el) { el.textContent = '✓ Gespeichert'; setTimeout(() => { el.textContent = ''; }, 2500); }
      showToast('✓ Kosten-Einstellungen gespeichert');
    } else {
      if (el) el.textContent = '✗ Fehler';
      showToast('✗ ' + (d.error || 'Fehler'));
    }
  } catch(e) { showToast('✗ ' + e.message); }
}

// ── MODEL FALLBACK ─────────────────────────────────────────────────────────────
async function saveModelFallback() {
  const raw = document.getElementById('modelFallbackInput')?.value?.trim();
  const list = raw ? raw.split(',').map(s => s.trim()).filter(Boolean) : [];
  try {
    const r = await fetch('/api/config/settings', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ model_fallback: list }),
    });
    const d = await r.json();
    if (d.ok) showToast('✓ Model Fallback gespeichert');
    else showToast('✗ ' + (d.error || 'Fehler'));
  } catch(e) { showToast('✗ ' + e.message); }
}

async function saveTaskRouting() {
  const routing = {};
  const fields = {routingCoding:'coding', routingReview:'review', routingBrowsing:'browsing', routingDefault:'default'};
  for (const [id, key] of Object.entries(fields)) {
    const v = (document.getElementById(id)?.value || '').trim();
    if (v) routing[key] = v;
  }
  const checkModel = (document.getElementById('routingCheck')?.value || '').trim();
  try {
    const r = await fetch('/api/config/settings', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ task_routing: routing, check_model: checkModel }),
    });
    const d = await r.json();
    const el = document.getElementById('routingSaveStatus');
    if (d.ok) {
      showToast('✓ Task Routing saved');
      if (el) { el.textContent = '✓ saved'; setTimeout(() => { if(el) el.textContent = ''; }, 3000); }
    } else {
      showToast('✗ ' + (d.error || 'Error'));
      if (el) el.textContent = '✗ ' + (d.error || 'Error');
    }
  } catch(e) { showToast('✗ ' + e.message); }
}

async function claudeCliLogin() {
  const btn = document.getElementById('claudeLoginBtn');
  const msg = document.getElementById('claudeLoginMsg');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  if (msg) { msg.style.display = ''; msg.style.color = 'var(--text3)'; msg.textContent = 'Starte Login…'; }
  try {
    const r = await fetch('/api/claude-cli/login', { method: 'POST' });
    const d = await r.json();
    if (d.ok) {
      if (d.step === 'already_authenticated') {
        if (msg) { msg.style.color = 'var(--green)'; msg.textContent = '✓ Bereits angemeldet — ask_claude ist sofort nutzbar.'; }
        showToast('✓ Claude CLI bereits angemeldet');
      } else if (d.step === 'browser_opened') {
        if (msg) {
          msg.style.color = 'var(--text2)';
          msg.innerHTML = '🌐 <b>Browser wurde geöffnet.</b> Melde dich mit deinem Claude-Konto an.<br>'
            + 'Danach <b>"↺ Status prüfen"</b> klicken — fertig.';
        }
        // Auto-poll alle 4s für 2 Minuten
        let polls = 0;
        const interval = setInterval(async () => {
          polls++;
          if (polls > 30) { clearInterval(interval); return; }
          try {
            const sr = await fetch('/api/claude-cli/status');
            const sd = await sr.json();
            if (sd.authenticated) {
              clearInterval(interval);
              if (msg) { msg.style.color = 'var(--green)'; msg.innerHTML = '✓ <b>Anmeldung erfolgreich!</b> ask_claude ist jetzt nutzbar.'; }
              showToast('✓ Claude CLI angemeldet');
              _loadClaudeCliStatus();
            }
          } catch {}
        }, 4000);
      }
    } else {
      const errText = d.step === 'no_npm'
        ? 'Node.js nicht gefunden. Installieren: <a href="https://nodejs.org" target="_blank" style="color:var(--text2)">nodejs.org</a>'
        : ('Fehler: ' + (d.error || d.step || '?'));
      if (msg) { msg.style.color = 'var(--red,#e55)'; msg.innerHTML = errText; }
      showToast('✗ ' + (d.error || 'Login fehlgeschlagen'));
    }
  } catch(e) {
    if (msg) { msg.style.color = 'var(--red,#e55)'; msg.textContent = 'Fehler: ' + e.message; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Mit Claude anmelden'; }
  }
}

async function _loadClaudeCliStatus() {
  const el = document.getElementById('claudeCliStatus');
  if (!el) return;
  try {
    const r = await fetch('/api/claude-cli/status');
    const d = await r.json();
    if (!d.installed) {
      el.innerHTML = '<span style="color:var(--text3)">Claude CLI nicht installiert</span>';
    } else if (!d.authenticated) {
      el.innerHTML = '<span style="color:var(--yellow,#f5a623)">⚠ Installiert, aber nicht angemeldet</span> — Terminal: <code style="background:var(--bg4);padding:1px 4px;border-radius:3px">claude login</code>';
    } else {
      el.innerHTML = `<span style="color:var(--green)">✓ Claude CLI bereit</span> — <span style="font-size:10px;color:var(--text3)">${esc(d.path||'')}</span>`;
    }
  } catch { el.textContent = ''; }
}

// ── GOOGLE OAUTH ───────────────────────────────────────────────────────────────
async function initGoogleOAuth() {
  try {
    const r = await fetch('/api/keys');
    if (!r.ok) return;
    const d = await r.json();
    const allKeys = [...(d.providers || []).flatMap(p => p.env_keys || []),
                     ...(d.other_keys || []).map(k => k.key)];
    const hasClientId = allKeys.includes('GOOGLE_CLIENT_ID');
    if (hasClientId) {
      document.getElementById('googleOAuthSection').style.display = '';
      document.getElementById('googleOAuthDivider').style.display = '';
    }
    const hasRefresh = d.providers?.some(p => p.env_keys?.some(k => k.key === 'GOOGLE_REFRESH_TOKEN' && k.set))
      || d.other_keys?.some(k => k.key === 'GOOGLE_REFRESH_TOKEN' && k.set);
    if (hasRefresh) {
      document.getElementById('googleOAuthStatus').textContent = '✓ Verbunden';
      document.getElementById('googleOAuthStatus').style.color = 'var(--green)';
      document.getElementById('googleOAuthBtn').textContent = '↺ Neu verbinden';
    }
  } catch {}
}

async function startGoogleOAuth() {
  try {
    const r = await fetch('/api/oauth/google/start');
    const d = await r.json();
    if (d.error) { showToast('✗ ' + d.error); return; }
    const popup = window.open(d.url, 'google_oauth', 'width=500,height=650');
    const handler = (e) => {
      if (e.data?.ok) {
        showToast('✓ Google verbunden');
        document.getElementById('googleOAuthStatus').textContent = '✓ Verbunden';
        document.getElementById('googleOAuthStatus').style.color = 'var(--green)';
        document.getElementById('googleOAuthBtn').textContent = '↺ Neu verbinden';
        loadKeys();
        window.removeEventListener('message', handler);
      } else if (e.data?.error) {
        showToast('✗ OAuth Fehler: ' + e.data.error);
        window.removeEventListener('message', handler);
      }
    };
    window.addEventListener('message', handler);
  } catch(e) { showToast('✗ ' + e.message); }
}

// ── Telegram Settings ─────────────────────────────────────────────────────────
let _telegramAllowedIds = [];

async function loadTelegramSettings() {
  try {
    const r = await fetch('/api/telegram/config');
    if (!r.ok) return;
    const d = await r.json();
    _telegramAllowedIds = d.allowed_ids || [];
    document.getElementById('telegramTokenMasked').textContent =
      d.token_set ? `Current: ${d.token_masked}` : 'No token set';
    const status = document.getElementById('telegramPollingStatus');
    status.textContent = d.polling_active ? '● Active' : '○ Inactive';
    status.style.color = d.polling_active ? 'var(--green)' : 'var(--text3)';
    renderTelegramIds();
  } catch(e) { /* ignore */ }
}

function renderTelegramIds() {
  const list = document.getElementById('telegramAllowedList');
  if (_telegramAllowedIds.length === 0) {
    list.innerHTML = '<div style="font-size:11px;color:var(--text3);font-style:italic">No restrictions — all users allowed</div>';
    return;
  }
  list.innerHTML = _telegramAllowedIds.map((id, i) =>
    `<div class="settings-row" style="gap:6px">
      <span style="font-family:monospace;font-size:12px;flex:1">${id}</span>
      <button class="action-btn danger" style="padding:2px 8px;font-size:11px" onclick="removeTelegramId(${i})">Remove</button>
    </div>`
  ).join('');
}

function addTelegramId() {
  const inp = document.getElementById('telegramNewId');
  const val = inp.value.trim();
  if (!val) return;
  if (_telegramAllowedIds.includes(val)) { showToast('ID already in list'); return; }
  _telegramAllowedIds.push(val);
  inp.value = '';
  renderTelegramIds();
  saveTelegramIds();
}

function removeTelegramId(i) {
  _telegramAllowedIds.splice(i, 1);
  renderTelegramIds();
  saveTelegramIds();
}

async function saveTelegramIds() {
  try {
    await fetch('/api/telegram/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({allowed_ids: _telegramAllowedIds})
    });
  } catch(e) { showToast('✗ ' + e.message); }
}

async function saveTelegramToken() {
  const token = document.getElementById('telegramTokenInput').value.trim();
  if (!token) { showToast('Enter a token first'); return; }
  try {
    const r = await fetch('/api/telegram/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token})
    });
    const d = await r.json();
    if (d.ok) {
      showToast(d.polling_active ? '✓ Token saved — polling active' : '✓ Token saved');
      document.getElementById('telegramTokenInput').value = '';
      loadTelegramSettings();
    } else {
      showToast('✗ Error saving token');
    }
  } catch(e) { showToast('✗ ' + e.message); }
}

function toggleTelegramTokenVisibility() {
  const inp = document.getElementById('telegramTokenInput');
  inp.type = inp.type === 'password' ? 'text' : 'password';
}

function switchSettingsTab(tabName) {
  // Hide all tab contents
  document.querySelectorAll('.settings-tab-content').forEach(el => el.classList.remove('active'));
  // Deactivate all tab buttons
  document.querySelectorAll('.settings-tab').forEach(btn => btn.classList.remove('active'));
  // Show selected tab
  document.getElementById(`tab-${tabName}`).classList.add('active');
  // Activate selected button
  event.target.classList.add('active');
}

// ── Wakeup: AION meldet sich beim Start von selbst ────────────────────────────
function handleWakeup(ev) {
  if (!ev.text || _wakeupShown) return;
  _wakeupShown = true;
  // Wakeup-Ack sicherstellen — auch wenn Nachricht per SSE kam (nicht nur per init())
  fetch('/api/wakeup-ack', { method: 'POST' }).catch(() => {});
  // Kurze Verzögerung — fühlt sich an wie AION "tippt"
  setTimeout(() => {
    const bubble = appendAionBubble();
    bubble.dataset.raw = ev.text;
    bubble.innerHTML = renderMd(ev.text);
    bubble.classList.remove('streaming');
    scrollChat();
    // Auch im Tab-Titel anzeigen wenn nicht im Fokus
    if (document.hidden) {
      document.title = '💬 AION meldet sich…';
      window.addEventListener('focus', () => { document.title = 'AION'; }, { once: true });
    }
  }, 800);
}

// ── Proactive Push (SSE /api/events) ─────────────────────────────────────────
(function initPushStream() {
  let _evtSource = null;
  let _reconnectDelay = 3000;

  function connect() {
    try {
      _evtSource = new EventSource('/api/events');
      _evtSource.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data);
          // Server neu verbunden → _wakeupShown zurücksetzen damit neue Wakeup-Nachricht erscheint
          if (ev.type === 'connected') {
            _wakeupShown = false;
            // Wakeup kommt aus config.json — mehrfach prüfen bis sie da ist
            for (const d of [2000, 6000, 12000, 20000]) {
              setTimeout(async () => {
                if (_wakeupShown) return;
                try {
                  const s = await (await fetch('/api/status')).json();
                  if (s.pending_wakeup) {
                    handleWakeup({ text: s.pending_wakeup });
                    fetch('/api/wakeup-ack', { method: 'POST' }).catch(() => {});
                  }
                } catch {}
              }, d);
            }
          }
          if (ev.type === 'proactive') showProactiveToast(ev);
          if (ev.type === 'compress')  showCompressToast(ev);
          if (ev.type === 'wakeup')    handleWakeup(ev);
          if (ev.type === 'warning')   showWarningToast(ev);
        } catch {}
      };
      _evtSource.onerror = () => {
        _evtSource && _evtSource.close();
        // Reconnect after delay (server might restart)
        setTimeout(connect, _reconnectDelay);
        _reconnectDelay = Math.min(_reconnectDelay * 2, 60000);
      };
      _evtSource.onopen = () => { _reconnectDelay = 3000; };
    } catch {}
  }
  connect();
})();

function showCompressToast(ev) {
  const isRunning = ev.status === 'running';
  const toastId   = 'compress-toast';
  // For 'done': replace running toast if present, then auto-remove
  const existing  = document.getElementById(toastId);
  if (existing) existing.remove();
  const div = document.createElement('div');
  div.id        = toastId;
  div.className = `compress-toast ${ev.status || 'running'}`;
  div.innerHTML = `<span class="compress-icon">${isRunning ? '⚙' : '✓'}</span><span>${esc(ev.message || 'Optimizing context…')}</span>`;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), isRunning ? 60_000 : 3_500);
}

function showWarningToast(ev) {
  const text = ev.text || 'Ein Plugin konnte nicht geladen werden.';
  const div = document.createElement('div');
  div.className = 'proactive-toast';
  div.style.borderLeft = '3px solid #f59e0b';
  div.innerHTML = `
    <div class="pt-header">
      <span class="pt-icon">⚠</span>
      <span class="pt-title">Plugin-Fehler</span>
      <button class="pt-close" onclick="this.closest('.proactive-toast').remove()">✕</button>
    </div>
    <div class="pt-body">${text.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
    <div class="pt-actions">
      <button class="pt-btn-dismiss" onclick="this.closest('.proactive-toast').remove()">OK</button>
    </div>`;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 15000);
}

function showProactiveToast(ev) {
  // Remove any existing proactive toast first
  document.querySelectorAll('.proactive-toast').forEach(el => el.remove());

  const text   = ev.text   || 'AION has a suggestion for you.';
  const action = ev.action || '';

  const div = document.createElement('div');
  div.className = 'proactive-toast';
  div.innerHTML = `
    <div class="pt-header">
      <span class="pt-icon">◈</span>
      <span class="pt-title">AION suggests</span>
      <button class="pt-close" onclick="this.closest('.proactive-toast').remove()">✕</button>
    </div>
    <div class="pt-body">${text.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
    ${action ? `<div class="pt-actions">
      <button class="pt-btn-accept" onclick="acceptProactive(this,'${action.replace(/'/g,"\\'")}')">Accept</button>
      <button class="pt-btn-dismiss" onclick="this.closest('.proactive-toast').remove()">Dismiss</button>
    </div>` : `<div class="pt-actions">
      <button class="pt-btn-dismiss" onclick="this.closest('.proactive-toast').remove()">OK</button>
    </div>`}`;
  document.body.appendChild(div);
  // Auto-dismiss after 30 s
  setTimeout(() => div.remove(), 30000);
}

async function acceptProactive(btn, action) {
  btn.closest('.proactive-toast').remove();
  document.getElementById('input').value = action;
  await send();
}
