import test from 'node:test'
import assert from 'node:assert/strict'
import { readJsonRequest } from '../src/lib/readTransport.js'
import { sharedRead, invalidateSharedReads } from '../src/lib/sharedRead.js'
const deferred = () => { let resolve, reject; const promise = new Promise((a,b)=>{resolve=a;reject=b}); return {promise,resolve,reject} }

test('ten identical concurrent authenticated GETs use one HTTP request; later reads are fresh', async()=>{
  const previous=globalThis.fetch, release=deferred();let calls=0
  globalThis.fetch=async()=>{calls++;await release.promise;return {ok:true,status:200,json:async()=>({rows:[{amount:100}]})}}
  try {
    const reads=Array.from({length:10},()=>readJsonRequest('/same',{headers:{Authorization:'Bearer synthetic-a'}}))
    await Promise.resolve();assert.equal(calls,1);release.resolve()
    const results=await Promise.all(reads);results[0].payload.rows[0].amount=999
    assert.equal(results[1].payload.rows[0].amount,100)
    await readJsonRequest('/same',{headers:{Authorization:'Bearer synthetic-a'}});assert.equal(calls,2)
  }finally{globalThis.fetch=previous;invalidateSharedReads()}
})
test('different tokens, filters and methods never share a request',async()=>{
  const previous=globalThis.fetch;let calls=0
  globalThis.fetch=async()=>{calls++;return {ok:true,status:200,json:async()=>({ok:true})}}
  try {
    await Promise.all([
      readJsonRequest('/a?month=2026-09',{headers:{Authorization:'Bearer one'}}),
      readJsonRequest('/a?month=2026-09',{headers:{Authorization:'Bearer two'}}),
      readJsonRequest('/a?month=2026-10',{headers:{Authorization:'Bearer one'}}),
      readJsonRequest('/a',{method:'POST'}),readJsonRequest('/a',{method:'POST'}),
    ]);assert.equal(calls,5)
  }finally{globalThis.fetch=previous;invalidateSharedReads()}
})
test('one cancelled panel does not abort another; last cancellation releases transport',async()=>{
  const release=deferred(),a=new AbortController(),b=new AbortController();let networkSignal
  const load=signal=>{networkSignal=signal;return release.promise}
  const first=sharedRead('abort',load,a.signal),second=sharedRead('abort',load,b.signal)
  await Promise.resolve();a.abort();await assert.rejects(first,{name:'AbortError'});assert.equal(networkSignal.aborted,false)
  release.resolve({ok:true});assert.deepEqual(await second,{ok:true})
  const last=new AbortController(),stop=deferred()
  const final=sharedRead('last',signal=>{networkSignal=signal;return stop.promise},last.signal)
  await Promise.resolve();last.abort();await assert.rejects(final,{name:'AbortError'});assert.equal(networkSignal.aborted,true);stop.resolve(null)
})
test('write or authentication invalidation separates new reads from older in-flight data',async()=>{
  const old=deferred(),fresh=deferred();let calls=0
  const first=sharedRead('money',()=>{calls++;return old.promise})
  await Promise.resolve();invalidateSharedReads()
  const second=sharedRead('money',()=>{calls++;return fresh.promise})
  await Promise.resolve();old.resolve(1);assert.equal(await first,1)
  const third=sharedRead('money',()=>{throw Error('old completion evicted fresh request')})
  fresh.resolve(2);assert.deepEqual(await Promise.all([second,third]),[2,2]);assert.equal(calls,2)
})
test('errors are evicted and never cached',async()=>{
  await assert.rejects(sharedRead('retry',()=>Promise.reject(Error('temporary'))),/temporary/)
  assert.equal(await sharedRead('retry',async()=>42),42)
})
