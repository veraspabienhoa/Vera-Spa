import assert from 'node:assert/strict'
import test from 'node:test'

import {
  LIVE_TOUR_CLOCK_TICK_MS,
  LIVE_TOUR_POLL_MS,
  startLiveTourClock,
  startLiveTourPolling,
} from '../src/lib/liveTourPerformance.js'

test('clock-driven whole-page renders are reduced twenty-fold', () => {
  assert.equal(LIVE_TOUR_CLOCK_TICK_MS / 1_000, 20)
  let callback
  const fakeWindow = { setInterval(fn, delay) { callback = fn; assert.equal(delay, 20_000); return 7 } }
  let renders = 0
  assert.equal(startLiveTourClock(() => { renders += 1 }, fakeWindow), 7)
  callback()
  assert.equal(renders, 1)
})

test('poll remains responsive while visible and does no work in hidden tabs', () => {
  let callback
  const fakeWindow = { setInterval(fn, delay) { callback = fn; assert.equal(delay, LIVE_TOUR_POLL_MS); return 8 } }
  const fakeDocument = { visibilityState: 'hidden' }
  let polls = 0
  assert.equal(startLiveTourPolling(() => { polls += 1 }, fakeWindow, fakeDocument), 8)
  callback()
  assert.equal(polls, 0)
  fakeDocument.visibilityState = 'visible'
  callback()
  assert.equal(polls, 1)
})
