import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'

const built = await build({ entryPoints:['src/lib/useRevenueRealtime.js'], bundle:true, write:false,
  platform:'node', format:'cjs', external:['react'], define:{'import.meta.env':'{}'},
  plugins:[{name:'auth-fixture',setup(b){
    b.onResolve({filter:/\/supabase$/},()=>({path:'auth',namespace:'fixture'}))
    b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const getCurrentSession=async()=>null'}))
  }}] })
const mod={exports:{}}
new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
const {watchRevenueChanges}=mod.exports
const flush=async()=>{for(let i=0;i<5;i++)await Promise.resolve()}

test('Auto checks every 5 seconds but refreshes only changed data; hidden and busy screens stay protected',async()=>{
  const doc=new EventTarget();doc.hidden=false
  const timers=new Map();let id=0,revision='a',changes=0,reads=0,busy=false,fail=false,error='',stale=false
  const poller=watchRevenueChanges(async()=>{reads++;if(fail)throw Error('offline');return revision}, {
    document:doc,changed:()=>changes++,blocked:()=>busy,stale:()=>stale,failed:value=>{error=value},
    setTimeout:(fn,ms)=>{assert.equal(ms,5000);timers.set(++id,fn);return id},clearTimeout:key=>timers.delete(key),
  })
  const tick=async()=>{const [key,fn]=timers.entries().next().value;timers.delete(key);await fn();await flush()}
  await flush();assert.equal(changes,1)
  await tick();assert.equal(changes,1,'unchanged counters must not reload the ledger')
  busy=true;revision='b';await tick();assert.equal(changes,1)
  busy=false;await tick();assert.equal(changes,2,'a revision skipped during a save is still delivered')
  doc.hidden=true;doc.dispatchEvent(new Event('visibilitychange'));assert.equal(timers.size,0)
  const hiddenReads=reads;await poller.refresh();assert.equal(reads,hiddenReads)
  revision='c';doc.hidden=false;doc.dispatchEvent(new Event('visibilitychange'));await flush();assert.equal(changes,3)
  fail=true;await tick();assert.match(error,/Tạm mất kết nối/);assert.equal(changes,3)
  fail=false;await tick();assert.equal(error,'');assert.equal(changes,3)
  stale=true;await tick();assert.equal(changes,4,'retry a failed data reload even when its revision is unchanged')
  stale=false;await tick();assert.equal(changes,4)
  poller.stop();assert.equal(timers.size,0)
})

test('a slow revision request cannot overlap another poll',async()=>{
  const doc=new EventTarget();doc.hidden=false
  let resolve,reads=0
  const pending=new Promise(r=>{resolve=r})
  const poller=watchRevenueChanges(()=>{reads++;return pending},{document:doc,
    changed:()=>{},blocked:()=>false,failed:()=>{},setTimeout:()=>1,clearTimeout:()=>{}})
  await poller.refresh();doc.dispatchEvent(new Event('visibilitychange'));assert.equal(reads,1)
  resolve('a');await flush();poller.stop()
})
