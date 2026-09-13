import test from 'node:test'
import assert from 'node:assert/strict'
import { filterTourRows, tourFilterOptions } from '../src/lib/liveTourFilters.js'

test('invoice number matches paid, pending, history snapshots and backup metadata', () => {
  const rows = [{ id: 'paid', bill_no: 'VERA-0012' }, { id: 'pending', bill_no: 'VERA-0013' },
    { id: 'history', before: { bill_no: 'VERA-0012' } }, { id: 'backup', bill_numbers: ['VERA-0012', 'VERA-0013'] }, { id: 'empty' }]
  assert.deepEqual(filterTourRows(rows, { bill_no: ' vera-0012 ' }).map(row => row.id), ['paid', 'history', 'backup'])
  assert.equal(filterTourRows(rows, { bill_no: '999' }).length, 0)
  assert.equal(filterTourRows(rows, {}).length, 5)
  assert.equal(tourFilterOptions(rows).bill_no.length, 2)
})
