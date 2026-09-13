import test from 'node:test'
import assert from 'node:assert/strict'
import { createLeavePageLoader } from '../src/lib/leavePageLoader.js'

function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const tick = () => new Promise((resolve) => setImmediate(resolve))
function observer(options = {}) {
  const data = [], errors = [], started = []
  let finished = 0
  return { data, errors, started, get finished() { return finished }, handlers: {
    onStart: (ids) => started.push(ids), onData: (...args) => data.push(args),
    onError: (...args) => errors.push(args), onFinish: () => { finished += 1 }, ...options,
  } }
}

test('publishes completed records while catalog waits and never bursts reads', async () => {
  const loader = createLeavePageLoader(), view = observer(), catalog = deferred()
  const calls = []
  const jobs = ['daily', 'records', 'reasons', 'employees'].map((id) => ({ id, key: 'today', read: async () => {
    calls.push(id)
    return id === 'reasons' ? catalog.promise : id
  } }))
  const done = loader.run(jobs, view.handlers)
  await tick()
  assert.deepEqual(calls, ['daily', 'records', 'reasons'])
  assert.deepEqual(view.data, [['daily', 'daily'], ['records', 'records']])
  assert.equal(view.finished, 0)
  catalog.resolve('catalog')
  assert.equal(await done, true)
  assert.equal(calls.at(-1), 'employees')
})

test('only a changed filter reloads; explicit refresh still reads every section', async () => {
  const loader = createLeavePageLoader(), view = observer(), calls = []
  const jobs = ['daily', 'records', 'reasons', 'employees'].map((id) => ({ id, key: 'today', read: async () => { calls.push(id); return id } }))
  await loader.run(jobs, view.handlers)
  calls.length = 0
  const next = jobs.map((job) => job.id === 'daily' ? { ...job, key: 'next-week' } : job)
  await loader.run(next, { ...view.handlers, onlyChanged: true })
  assert.deepEqual(calls, ['daily'])
  calls.length = 0
  await loader.run(next, view.handlers)
  assert.deepEqual(calls, ['daily', 'records', 'reasons', 'employees'])
})

test('rapid filters discard old responses and skip obsolete queued reads', async () => {
  const loader = createLeavePageLoader(), first = deferred(), view = observer(), calls = []
  let active = 0, maximum = 0
  const job = (key, data) => ({ id: 'records', key, read: async () => {
    calls.push(key); maximum = Math.max(maximum, ++active)
    try { return await data } finally { active -= 1 }
  } })
  const old = loader.run([job('old', first.promise)], view.handlers)
  await tick()
  const skipped = loader.run([job('skipped', 'skipped')], view.handlers)
  const latest = loader.run([job('latest', 'latest')], view.handlers)
  first.resolve('old')
  assert.deepEqual(await Promise.all([old, skipped, latest]), [false, false, true])
  assert.deepEqual(calls, ['old', 'latest'])
  assert.deepEqual(view.data, [['records', 'latest']])
  assert.equal(maximum, 1)
  assert.equal(view.finished, 1)
})

test('one failed section does not hide other data and retries on the next load', async () => {
  const loader = createLeavePageLoader(), view = observer()
  let failing = true
  const jobs = [{ id: 'daily', key: 'today', read: async () => { if (failing) throw Error('Database busy'); return 'stats' } },
    { id: 'records', key: 'today', read: async () => 'records' }]
  assert.equal(await loader.run(jobs, view.handlers), false)
  assert.deepEqual(view.data, [['records', 'records']])
  assert.equal(view.errors[0][0], 'daily')
  failing = false
  assert.equal(await loader.run(jobs, { ...view.handlers, onlyChanged: true }), true)
  assert.deepEqual(view.started.at(-1), ['daily'])
})

test('leaving the page prevents late data and loading callbacks from updating it', async () => {
  const loader = createLeavePageLoader(), read = deferred(), view = observer()
  const done = loader.run([{ id: 'records', key: 'today', read: () => read.promise }], view.handlers)
  await tick()
  loader.invalidate()
  read.resolve('old')
  assert.equal(await done, false)
  assert.deepEqual(view.data, [])
  assert.equal(view.finished, 0)
})

test('switching away and back before a queued read starts still completes the visible load', async () => {
  const loader = createLeavePageLoader(), view = observer(), calls = []
  const job = (key) => ({ id: 'records', key, read: async () => { calls.push(key); return key } })
  await loader.run([job('today')], view.handlers)
  const away = loader.run([job('tomorrow')], { ...view.handlers, onlyChanged: true })
  const back = loader.run([job('today')], { ...view.handlers, onlyChanged: true })
  assert.deepEqual(await Promise.all([away, back]), [false, true])
  assert.deepEqual(calls, ['today', 'today'])
  assert.deepEqual(view.started.at(-1), ['records'])
  assert.deepEqual(view.data.at(-1), ['records', 'today'])
})
