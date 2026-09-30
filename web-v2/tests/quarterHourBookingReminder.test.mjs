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
