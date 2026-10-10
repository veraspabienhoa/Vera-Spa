import test from 'node:test'
import assert from 'node:assert/strict'
import { nextQuarterHourAt, startQuarterHourBookingReminder, QUARTER_HOUR_MS } from '../src/lib/quarterHourBookingReminder.js'

const at = (hour, minute, second = 0) => {
  const date = new Date(2026, 8, 30, hour, minute, second)
  return date.getTime()
}

test('reminders align to the next quarter-hour boundary', () => {
  assert.equal(nextQuarterHourAt(at(19, 14, 59)), at(19, 15))
  assert.equal(nextQuarterHourAt(at(19, 15)), at(19, 30))
  assert.equal(nextQuarterHourAt(at(19, 30)), at(19, 45))
  assert.equal(nextQuarterHourAt(at(23, 55)), at(0, 0) + 24 * 60 * 60 * 1000)
})

test('only nonempty upcoming results trigger and cleanup stops future reminders', async () => {
  let clock = at(19, 14)
  const timers = []
  const reminders = []
  const cleanup = startQuarterHourBookingReminder({
    now: () => clock,
    setTimer: (callback, delay) => { const timer = { callback, delay, cleared: false }; timers.push(timer); return timer },
    clearTimer: timer => { timer.cleared = true },
    load: async () => ({ total: reminders.length ? 1 : 0 }),
    onReminder: result => reminders.push(result.total),
  })
  assert.equal(timers[0].delay, at(19, 15) - clock)
  clock = at(19, 15)
  timers[0].callback()
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(reminders, [])
  assert.equal(timers[1].delay, QUARTER_HOUR_MS)
  reminders.push('seed')
  clock = at(19, 30)
  timers[1].callback()
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(reminders, ['seed', 1])
  cleanup()
  assert.equal(timers[2].cleared, true)
})

function fixture({ hidden = false, load = async () => ({ total: 1 }) } = {}) {
  let clock = at(19, 14), id = 0, calls = 0
  const doc = new EventTarget(); doc.hidden = hidden
  const timers = new Map(), reminders = []
  const cleanup = startQuarterHourBookingReminder({
    document: doc, now: () => clock,
    setTimer: (callback, delay) => { timers.set(++id, { callback, delay }); return id },
    clearTimer: key => timers.delete(key),
    load: () => { calls++; return load() },
    onReminder: result => reminders.push(result.total),
  })
  return { timers, reminders, cleanup, get calls() { return calls },
    clock: value => { clock = value },
    visible: value => { doc.hidden = !value; doc.dispatchEvent(new Event('visibilitychange')) },
    fire: async () => { const timer = [...timers.values()][0]; assert.ok(timer); await timer.callback() },
  }
}
const tick = () => new Promise(resolve => setImmediate(resolve))

test('hidden tabs make no quarter-hour reads and catch up once after multiple boundaries', async () => {
  const f = fixture({ hidden: true })
  try {
    assert.equal(f.timers.size, 0)
    f.clock(at(20, 1)); f.visible(true); await tick()
    assert.equal(f.calls, 1); assert.deepEqual(f.reminders, [1])
    assert.equal([...f.timers.values()][0].delay, 14 * 60 * 1000)
    f.visible(true); await tick(); assert.equal(f.calls, 1)
    f.visible(false); assert.equal(f.timers.size, 0)
  } finally { f.cleanup() }
})

test('return before the next boundary retains alignment and a slow request never overlaps', async () => {
  let finish
  const f = fixture({ load: () => new Promise(resolve => { finish = resolve }) })
  try {
    f.visible(false); f.clock(at(19, 14, 30)); f.visible(true)
    assert.equal(f.calls, 0); assert.equal([...f.timers.values()][0].delay, 30000)
    f.clock(at(19, 15)); const pending = f.fire()
    f.visible(false); f.visible(true); f.visible(true)
    assert.equal(f.calls, 1)
    finish({ total: 2 }); await pending
    assert.deepEqual(f.reminders, []); assert.equal(f.timers.size, 1)
    assert.equal([...f.timers.values()][0].delay, 0, 'return during a slow read queues one fresh catch-up')
    const fresh = f.fire(); assert.equal(f.calls, 2)
    finish({ total: 3 }); await fresh
    assert.deepEqual(f.reminders, [3]); assert.equal(f.timers.size, 1)
    assert.equal([...f.timers.values()][0].delay, QUARTER_HOUR_MS)
  } finally { f.cleanup() }
})

test('a hidden late result is ignored and return rechecks; stopped account cannot show old reminders', async () => {
  const resolvers = []
  const f = fixture({ load: () => new Promise(resolve => resolvers.push(resolve)) })
  f.clock(at(19, 15)); const pending = f.fire()
  f.visible(false); resolvers.shift()({ total: 99 }); await pending
  assert.deepEqual(f.reminders, []); assert.equal(f.timers.size, 0)
  f.clock(at(19, 20)); f.visible(true)
  assert.equal(f.calls, 2)
  f.cleanup(); resolvers.shift()({ total: 55 }); await tick()
  assert.deepEqual(f.reminders, []); assert.equal(f.timers.size, 0)
  f.visible(true); assert.equal(f.calls, 2)
})

test('failed reminder reads stay bounded to the next visible quarter-hour', async () => {
  const f = fixture({ load: async () => { throw Error('offline') } })
  try {
    f.clock(at(19, 15)); await f.fire()
    assert.equal(f.calls, 1); assert.deepEqual(f.reminders, [])
    assert.equal([...f.timers.values()][0].delay, QUARTER_HOUR_MS)
    f.visible(false); f.clock(at(19, 35)); f.visible(true); await tick()
    assert.equal(f.calls, 2); assert.equal([...f.timers.values()][0].delay, 10 * 60 * 1000)
  } finally { f.cleanup() }
})
