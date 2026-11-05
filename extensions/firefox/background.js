/* The native service owns quotas. This extension only reports and enforces. */
const api = globalThis.browser || chrome;
let port = null, busy = false, ready = false, lastSignature = '', lastResponse = 0;
let rules = [];
// Same normalization as the service: leading "*" and "." mark subdomains, a trailing dot is ignored.
function target(pattern) { return new URL(pattern.includes('://') ? pattern : 'https://' + pattern.replace(/^[*.]+/, '')); }
function bare(host) { return host.toLowerCase().replace(/\.$/, ''); }
function match(url, pattern) {
  try {
    const u = new URL(url);
    if (!['http:', 'https:', 'ws:', 'wss:'].includes(u.protocol)) return false;
    if (pattern === '*') return true;
    const p = target(pattern);
    const host = bare(u.hostname), domain = bare(p.hostname);
    return (host === domain || host.endsWith('.' + domain)) && (p.pathname === '/' || u.pathname.startsWith(p.pathname));
  } catch { return false; }
}
function denied(url) { return rules.some(r => r.targets.some(p => match(url, p)) && !r.exceptions.some(p => match(url, p))); }
function filter(pattern) {
  if (pattern === '*') return '*';
  const p = target(pattern);
  return '||' + bare(p.hostname) + (p.pathname === '/' ? '^' : p.pathname);
}
async function applyRules(next) {
  const signature = JSON.stringify(next.map(r => [r.id, r.targets, r.exceptions]));
  if (signature === lastSignature && ready) return;
  ready = false;
  const dynamic = [];
  let id = 1;
  // Per-rule excluded domains preserve deny dominance across overlapping rules.
  for (const r of next) {
    const exceptions = r.exceptions.map(p => p === '*' ? '*' : bare(target(p).hostname));
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
// Rules match scheme, host and path only. Without credentials, query, fragment and
// non-web addresses (e.g. large data: URLs) a pulse stays far below the native host's
// 512 KiB limit, and credentials cannot push the host past the service's URL cut-off.
function address(url) {
  try {
    const u = new URL(url);
    return ['http:', 'https:', 'ws:', 'wss:'].includes(u.protocol) ? (u.origin + u.pathname).slice(0, 2048) : '';
  } catch { return ''; }
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
    const tabs = windows.flatMap(w=>w.tabs || []).map(t=>({id:t.id,url:address(t.url || t.pendingUrl || '')}));
    port.postMessage({op:'pulse',tabs,focused:!!focused,active_url:address(active?.url || ''),ready:ready && Date.now()-lastResponse<4000});
  } catch { ready = false; } finally { busy = false; }
}
api.tabs.onUpdated.addListener((id,change,tab)=> { if (change.url && denied(change.url)) closeDeniedTabs([id]); });
api.tabs.onActivated.addListener(pulse);
api.windows.onFocusChanged.addListener(pulse);
api.runtime.onStartup.addListener(pulse);
api.runtime.onInstalled.addListener(pulse);
setInterval(pulse, 750);
pulse();
