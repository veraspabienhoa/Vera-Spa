import test from 'node:test'
import assert from 'node:assert/strict'
import { leaveMonthRange } from '../src/lib/leaveMonthRange.js'

test('range filters cannot read a neighboring month, including leap years', () => {
  assert.deepEqual(leaveMonthRange('2028-02', '2028-01-31', '2028-03-05'), ['2028-02-01', '2028-02-29'])
  assert.deepEqual(leaveMonthRange('2026-09', '2026-09-28', '2026-10-04'), ['2026-09-28', '2026-09-30'])
  assert.deepEqual(leaveMonthRange('2026-10', '2026-09-01', '2026-09-30'), ['2026-10-01', '2026-10-31'])
  assert.deepEqual(leaveMonthRange('2026-12', '', ''), ['2026-12-01', '2026-12-31'])
})

// Exercise the actual API method with HTTP transport replaced at its boundary.
const { readFile } = await import('node:fs/promises')
const apiSource = await readFile(new URL('../src/lib/api.js', import.meta.url), 'utf8')
const method = apiSource.split('  leaveRecords: ')[1].split(',\n  leaveReasons:')[0]
const api = (request) => new Function('request', 'isApiConfigured', `return (${method})`)(request, true)

test('month endpoint uses the selected month, with safe rolling-release fallback', async () => {
  const calls = []
  const read = api(async (url) => {
    calls.push(url)
    if (url.includes('month-records')) throw Object.assign(new Error('old release'), { status: 404 })
    return { records: [] }
  })
  assert.deepEqual(await read('2026-09-01', '2026-09-30'), { records: [] })
  assert.equal(calls.length, 2)
  assert.match(calls[0], /month=2026-09/)
  assert.match(calls[1], /start=2026-09-01&end=2026-09-30/)
  await assert.rejects(read('2026-09-01', '2026-10-01'), /tháng/)
  assert.equal(calls.length, 2)
})

test('permission failures never fall back to another endpoint', async () => {
  let calls = 0
  const read = api(async () => { calls++; throw Object.assign(new Error('denied'), { status: 403 }) })
  await assert.rejects(read('2026-09-01', '2026-09-01'), /denied/)
  assert.equal(calls, 1)
})
