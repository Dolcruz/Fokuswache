const fs = require('fs'), vm = require('vm'), assert = require('assert');
let dynamics = [], disconnected, listener, posted = [], windows = [];
const noop=()=>{}, hook={addListener:noop};
const api={runtime:{connectNative(){return {postMessage:m=>posted.push(m),onMessage:{addListener(fn){listener=fn}},onDisconnect:{addListener(fn){disconnected=fn}}}},getURL:p=>'chrome-extension://test/'+p,onStartup:hook,onInstalled:hook},tabs:{onUpdated:hook,onActivated:hook,update:async()=>{}},windows:{onFocusChanged:hook,getAll:async()=>windows},declarativeNetRequest:{getDynamicRules:async()=>dynamics,updateDynamicRules:async p=>{dynamics=p.addRules}}};
const context=vm.createContext({chrome:api,URL,console,setInterval:noop,Date});
vm.runInContext(fs.readFileSync(require('path').join(__dirname,'../extensions/chromium/background.js'),'utf8'),context);
const check=(s)=>vm.runInContext(s,context);
(async()=>{
assert(check("match('https://sub.x.com/a','x.com')"));
assert(!check("match('https://notx.com/a','x.com')"));
assert(!check("match('https://x.com.evil.org/a','x.com')"));
assert(check("match('https://example.org/a','*')"));
assert(!check("match('file:///C:/example.org','*')"));
// Leading "*" and "." and a trailing dot are normalized exactly as the service does.
assert(check("match('https://sub.example.com/a','*example.com')"));
assert(check("match('https://x.com/a','.x.com')"));
assert.equal(check("filter('*example.com')"),'||example.com^');
assert.equal(check("filter('**.x.com/a')"),'||x.com/a');
assert.equal(check("filter('x.com.')"),'||x.com^');
await check("applyRules([{id:'1',targets:['*'],exceptions:['example.org']},{id:'2',targets:['example.org/private'],exceptions:[]}])");
assert.equal(dynamics.length,2);
assert.equal(dynamics[0].condition.excludedRequestDomains[0],'example.org');
assert.equal(dynamics[1].condition.excludedRequestDomains.length,0);
await check("applyRules([{id:'3',targets:['*'],exceptions:['*.example.org.','.example.net']}])");
assert.deepEqual([...dynamics[0].condition.excludedRequestDomains],['example.org','example.net']);
await check("applyRules([{id:'1',targets:['*'],exceptions:['example.org']},{id:'2',targets:['example.org/private'],exceptions:[]}])");
assert(!check("denied('https://example.org/public')"));
assert(check("denied('https://example.org/private')"));
assert(check("denied('https://x.com/a')"));
await check('applyRules([])');assert.equal(dynamics.length,0);
// The native host drops pulses above 512 KiB and the service keeps only 8192 characters per URL.
windows=[{focused:true,tabs:[{id:1,active:true,url:'https://'+'u'.repeat(9000)+'@x.com/home?q='+'q'.repeat(9000)},
  {id:2,url:'data:image/png;base64,'+'A'.repeat(600*1024)},{id:3,url:'',pendingUrl:'https://xn--mller-kva.de/a%20b#top'}]}];
await check('pulse()');
const pulse=posted.at(-1);
assert(JSON.stringify(pulse).length<4096);
assert.equal(pulse.active_url,'https://x.com/home');
assert.deepEqual(pulse.tabs.map(t=>t.url),['https://x.com/home','','https://xn--mller-kva.de/a%20b']);
console.log('Extension: domain boundaries, exceptions, deny dominance, dynamic rule removal, compact pulses passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
