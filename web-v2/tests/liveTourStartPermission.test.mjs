import assert from 'node:assert/strict'
import { canStartOutsideShift } from '../src/lib/liveTourStartPermission.js'
for (const [stamp, expected] of [
  ['2026-09-22T16:59:59Z', false], ['2026-09-22T17:00:00Z', true],
  ['2026-09-22T18:59:59Z', true], ['2026-09-22T19:00:00Z', false],
]) {
  assert.equal(canStartOutsideShift(false, true, Date.parse(stamp)), expected)
  assert.equal(canStartOutsideShift(false, false, Date.parse(stamp)), false)
  assert.equal(canStartOutsideShift(true, false, Date.parse(stamp)), true)
}
assert.equal(canStartOutsideShift(false, true, NaN), false)
console.log('Live Tour delegated start: Vietnam boundaries, explicit grant and Admin passed')
