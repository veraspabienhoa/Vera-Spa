import test from 'node:test'
import assert from 'node:assert/strict'
import { contractPeriod } from '../src/lib/laborContractPeriod.js'

test('contract periods include current Vietnam month, leap February and year rollover', () => {
  for (const [months, now, start, end] of [
    [1,'2026-10-15','2026-10-01','2026-10-31'],
    [2,'2026-10-15','2026-10-01','2026-11-30'],
    [3,'2026-10-15','2026-10-01','2026-12-31'],
    [3,'2026-12-15','2026-12-01','2027-02-28'],
    [1,'2028-02-15','2028-02-01','2028-02-29'],
    [1,'2026-09-30T18:00:00Z','2026-10-01','2026-10-31'],
  ]) assert.deepEqual(contractPeriod(months,new Date(now)),{contract_signed:start,contract_end:end})
})
