/* The native service owns quotas. This extension only reports and enforces. */
const api = globalThis.browser || chrome;
let port = null, busy = false, ready = false, lastSignature = '', lastResponse = 0;
let rules = [];
function match(url, pattern) {
  try {
    const u = new URL(url);
    if (!['http:', 'https:', 'ws:', 'wss:'].includes(u.protocol)) return false;
    if (pattern === '*') return true;
    const p = new URL(pattern.includes('://') ? pattern : 'https://' + pattern.replace(/^\*\./, ''));
    const host = u.hostname.toLowerCase().replace(/\.$/, ''), target = p.hostname.toLowerCase().replace(/\.$/, '');
    return (host === target || host.endsWith('.' + target)) && (p.pathname === '/' || u.pathname.startsWith(p.pathname));
  } catch { return false; }
}
function denied(url) { return rules.some(r => r.targets.some(p => match(url, p)) && !r.exceptions.some(p => match(url, p))); }
function filter(pattern) {
  if (pattern === '*') return '*';
  const p = new URL(pattern.includes('://') ? pattern : 'https://' + pattern.replace(/^\*\./, ''));
  return '||' + p.hostname + (p.pathname === '/' ? '^' : p.pathname);
}
async function applyRules(next) {
  const signature = JSON.stringify(next.map(r => [r.id, r.targets, r.exceptions]));
  if (signature === lastSignature && ready) return;
  ready = false;
  const dynamic = [];
  let id = 1;
  // Per-rule excluded domains preserve deny dominance across overlapping rules.
  for (const r of next) {
    const exceptions = r.exceptions.map(p => p === '*' ? '*' : new URL(p.includes('://') ? p : 'https://' + p.replace(/^\*\./, '')).hostname);
    if (exceptions.includes('*')) continue;
    for (const p of r.targets) {
      dynamic.push({id:id++,priority:1,action:{type:'block'},condition:{urlFilter:filter(p),excludedRequestDomains:exceptions}});
    }
  }
  const old = await api.declarativeNetRequest.getDynamicRules();
  await api.declarativeNetRequest.updateDynamicRules({removeRuleIds:old.map(r=>r.id),addRules:dynamic});
  rules = next;
  lastSignature = signature;
  ready = true;
}
async function closeDeniedTabs(ids) {
  for (const id of ids) {
    try { await api.tabs.update(id, {url:api.runtime.getURL('blocked.html')}); } catch {}
  }
}
function connect() {
  if (port) return;
  try {
    port = api.runtime.connectNative('de.fokuswache.native');
    port.onMessage.addListener(async message => {
      if (message.error) { ready = false; return; }
      try {
        await applyRules(message.web_rules || []);
        await closeDeniedTabs(message.blocked_tabs || []);
        lastResponse = Date.now();
      } catch (error) { ready = false; console.error('FokusWache:', error); }
    });
    port.onDisconnect.addListener(() => { void api.runtime.lastError; port = null; ready = false; });
  } catch { port = null; ready = false; }
}
async function pulse() {
  if (busy) return;
  busy = true;
  try {
    connect();
    if (!port) return;
    const windows = await api.windows.getAll({populate:true,windowTypes:['normal','popup']});
    const focused = windows.find(w=>w.focused);
    const active = focused?.tabs?.find(t=>t.active);
    const tabs = windows.flatMap(w=>w.tabs || []).map(t=>({id:t.id,url:t.url || t.pendingUrl || ''}));
    port.postMessage({op:'pulse',tabs,focused:!!focused,active_url:active?.url || '',ready:ready && Date.now()-lastResponse<4000});
  } catch { ready = false; } finally { busy = false; }
}
api.tabs.onUpdated.addListener((id,change,tab)=> { if (change.url && denied(change.url)) closeDeniedTabs([id]); });
api.tabs.onActivated.addListener(pulse);
api.windows.onFocusChanged.addListener(pulse);
api.runtime.onStartup.addListener(pulse);
api.runtime.onInstalled.addListener(pulse);
setInterval(pulse, 750);
pulse();
