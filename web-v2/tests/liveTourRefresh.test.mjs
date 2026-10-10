import test from 'node:test'
import assert from 'node:assert/strict'
import { createLiveTourRefresh } from '../src/lib/liveTourRefresh.js'

const flush = () => new Promise(resolve => setImmediate(resolve))

function fixture(t) {
  t.mock.timers.enable({apis:['setTimeout']})
  const requests = [], data = [], errors = [], loading = []
  let revision = 1
  const reader = createLiveTourRefresh({
    getRevision: () => revision,
    read: options => new Promise((resolve,reject) => requests.push({...options,resolve,reject})),
    onData: (value,meta) => data.push({value,...meta}),
    onError: error => errors.push(error),
    onLoading: value => loading.push(value),
  })
  t.after(() => reader.dispose())
  return {reader,requests,data,errors,loading,
    revise(value) {revision=value;reader.schedule()},
    async advance() {t.mock.timers.tick(180);await flush()},
  }
}

test('a slow read coalesces a revision burst into one trailing read of the latest target', async t => {
  const f = fixture(t)
  f.reader.schedule()
  await f.advance()
  for (let revision=2;revision<=100;revision++) f.revise(revision)
  await f.advance()
  assert.equal(f.requests.length,1)
  assert.equal(f.requests[0].signal.aborted,false)
  f.requests[0].resolve({revision:1})
  await flush()
  assert.equal(f.reader.lastLoadedRevision,1)
  assert.equal(f.loading.at(-1),true,'keep catch-up visible as loading')
  await f.advance()
  assert.equal(f.requests.length,2)
  assert.equal(f.requests[1].requestRevision,100)
  f.requests[1].resolve({revision:100})
  await flush()
  await f.advance()
  assert.equal(f.requests.length,2,'no queue proportional to the number of revisions')
  assert.equal(f.reader.lastLoadedRevision,100)
  assert.equal(f.loading.at(-1),false)
  assert.deepEqual(f.data.map(item=>item.loadedRevision),[1,100])
})

test('the actual response revision satisfies queued invalidations without redundant reads', async t => {
  const f = fixture(t)
  f.reader.schedule()
  await f.advance()
  f.revise(2)
  f.revise(3)
  f.requests[0].resolve({revision:4})
  await flush()
  await f.advance()
  assert.equal(f.requests.length,1)
  assert.equal(f.reader.lastLoadedRevision,4)
  f.revise(4)
  await f.advance()
  assert.equal(f.requests.length,1)
  f.revise(5)
  await f.advance()
  assert.equal(f.requests.length,2)
  assert.equal(f.requests[1].requestRevision,5)
})

test('responses without revision retain the request revision, not the newest observed board', async t => {
  const f = fixture(t)
  f.reader.schedule()
  await f.advance()
  f.revise(10)
  f.requests[0].resolve({})
  await flush()
  assert.equal(f.reader.lastLoadedRevision,1)
  assert.equal(f.data[0].requestRevision,1)
  await f.advance()
  assert.equal(f.requests.length,2)
  f.requests[1].resolve({})
  await flush()
  assert.equal(f.reader.lastLoadedRevision,10)
})

for (const error of [Object.assign(new Error('Timed out'),{name:'TimeoutError'}),new Error('Network offline')]) {
  test(`${error.name}: release failed reads, consume one queued refresh and avoid a retry loop`, async t => {
    const f = fixture(t)
    f.reader.schedule()
    await f.advance()
    f.revise(2)
    f.revise(3)
    f.requests[0].reject(error)
    await flush()
    assert.equal(f.reader.lastLoadedRevision,null,'failure never claims to have loaded data')
    await f.advance()
    assert.equal(f.requests.length,2)
    assert.equal(f.requests[1].requestRevision,3)
    f.requests[1].reject(error)
    await flush()
    for(let index=0;index<10;index++) await f.advance()
    assert.equal(f.requests.length,2,'transport owns retries; no automatic error spin')
    assert.equal(f.loading.at(-1),false)
    assert.equal(f.errors.length,2)
    f.revise(4)
    await f.advance()
    f.requests[2].resolve({revision:4})
    await flush()
    assert.equal(f.reader.lastLoadedRevision,4)
    assert.equal(f.data.length,1)
  })
}

test('navigation cancels in-flight work and discards late success or error and its trailing refresh', async t => {
  for (const fail of [false,true]) {
    const f = fixture(t)
    f.reader.schedule()
    await f.advance()
    f.revise(2)
    f.reader.dispose()
    assert.equal(f.requests[0].signal.aborted,true)
    if(fail) f.requests[0].reject(new Error('obsolete failure'))
    else f.requests[0].resolve({revision:1})
    await flush()
    await f.advance()
    f.reader.schedule()
    await f.advance()
    assert.equal(f.requests.length,1)
    assert.deepEqual(f.data,[])
    assert.deepEqual(f.errors,[])
    assert.deepEqual(f.loading,[true],'no completion callback after disposal')
    t.mock.timers.reset()
  }
})

test('navigation removes a delayed trailing read before it starts', async t => {
  const f = fixture(t)
  f.reader.schedule()
  await f.advance()
  f.revise(2)
  f.requests[0].resolve({revision:1})
  await flush()
  f.reader.dispose()
  await f.advance()
  assert.equal(f.requests.length,1)
})
