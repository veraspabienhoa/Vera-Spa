import test from 'node:test'
import assert from 'node:assert/strict'
import { acknowledgeSchedule, emptyScheduleCell, emptyScheduleWorkspace, reconcileSchedule, resolveScheduleConflict, scheduleCellKey, scheduleCellValue, scheduleHasChanges } from '../src/lib/scheduleConcurrency.js'

const day = '2026-10-05'
const key = name => scheduleCellKey(name, day)
const row = (name, shift_code = 'Ca 1', revision = 1) => ({ employee_username: name, work_date: day, shift_code, revision })
const load = rows => reconcileSchedule(emptyScheduleWorkspace(), rows)
const edit = (state, name, value) => ({ ...state, drafts: { ...state.drafts, [key(name)]: scheduleCellValue(value) } })

test('editable, pasted and imported values cannot carry revision metadata', () => {
  const value = scheduleCellValue({ ...row('A', 'Ca 2', 42), expected_revision: 7, note: 'copy', start_time: '09:00:00' })
  assert.equal(value.revision, undefined)
  assert.equal(value.expected_revision, undefined)
  assert.equal(value.employee_username, undefined)
  assert.equal(value.start_time, '09:00')
  assert.equal(value.note, 'copy')
})

test('refresh brings untouched remote edits forward while retaining disjoint local cells', () => {
  const state = edit(load([row('A'), row('B')]), 'A', { shift_code: 'Ca 2' })
  const next = reconcileSchedule(state, [row('A'), row('B', 'Nghỉ', 9), row('C', 'Ca 2', 10)])
  assert.equal(next.drafts[key('A')].shift_code, 'Ca 2')
  assert.equal(next.saved[key('A')].shift_code, 'Ca 1')
  assert.equal(next.drafts[key('B')].shift_code, 'Nghỉ')
  assert.equal(next.drafts[key('C')].shift_code, 'Ca 2')
  assert.deepEqual(next.conflicts, {})
  assert.equal(next.revisions[key('A')], 1)
  assert.equal(next.revisions[key('B')], 9)
})

test('same-cell conflict preserves both versions until explicit choice', () => {
  const state = edit(edit(load([row('A'), row('B')]), 'A', { shift_code: 'Ca 2' }), 'B', { shift_code: 'Ca 2' })
  const next = reconcileSchedule(state, [row('A', 'Nghỉ', 8), row('B')], [row('A')])
  assert.deepEqual(next.conflicts, { [key('A')]: true })
  assert.equal(next.saved[key('A')].shift_code, 'Nghỉ')
  assert.equal(next.drafts[key('A')].shift_code, 'Ca 2')
  assert.equal(next.drafts[key('B')].shift_code, 'Ca 2')
  const remote = resolveScheduleConflict(next, key('A'), false)
  assert.equal(remote.drafts[key('A')].shift_code, 'Nghỉ')
  assert.equal(remote.drafts[key('B')].shift_code, 'Ca 2')
  assert.equal(remote.manualSaveRequired, true)
  const local = resolveScheduleConflict(next, key('A'), true)
  assert.equal(local.drafts[key('A')].shift_code, 'Ca 2')
  assert.equal(local.revisions[key('A')], 8)
  assert.deepEqual(local.conflicts, {})
})

test('stale deletion conflicts with new remote data and never silently removes it', () => {
  const state = edit(load([row('A')]), 'A', {})
  const next = reconcileSchedule(state, [row('A', 'Ca 2', 20)])
  assert.deepEqual(next.conflicts, { [key('A')]: true })
  assert.equal(next.drafts[key('A')].shift_code, '')
  assert.equal(next.saved[key('A')].shift_code, 'Ca 2')
  assert.equal(resolveScheduleConflict(next, key('A'), false).drafts[key('A')].shift_code, 'Ca 2')
})

test('remote deletion conflicts with local edit; explicit recreate uses absent revision zero', () => {
  const next = reconcileSchedule(edit(load([row('A')]), 'A', { shift_code: 'Ca 2' }), [])
  assert.deepEqual(next.conflicts, { [key('A')]: true })
  assert.equal(next.revisions[key('A')] || 0, 0)
  assert.equal(resolveScheduleConflict(next, key('A'), true).drafts[key('A')].shift_code, 'Ca 2')
})

test('save acknowledgement preserves newer same-cell edits and new disjoint edits', () => {
  let state = load([row('A')])
  const changes = [{ key: key('A'), after: scheduleCellValue({ shift_code: 'Ca 2' }) }]
  state = edit(edit(state, 'A', { shift_code: 'Nghỉ' }), 'B', { shift_code: 'Ca 1' })
  const next = acknowledgeSchedule(state, changes, { revisions: [row('A', 'Ca 2', 7)] })
  assert.equal(next.saved[key('A')].shift_code, 'Ca 2')
  assert.equal(next.revisions[key('A')], 7)
  assert.equal(next.drafts[key('A')].shift_code, 'Nghỉ')
  assert.equal(next.drafts[key('B')].shift_code, 'Ca 1')
  assert.equal(next.revisions[key('B')] || 0, 0)
  assert.equal(scheduleHasChanges(next), true)
})

test('edit during slow deletion remains pending against an absent baseline', () => {
  const state = edit(load([row('A')]), 'A', { shift_code: 'Ca 2' })
  const next = acknowledgeSchedule(state, [{ key: key('A'), after: emptyScheduleCell() }], { revisions: [] })
  assert.equal(next.saved[key('A')], undefined)
  assert.equal(next.revisions[key('A')] || 0, 0)
  assert.equal(next.drafts[key('A')].shift_code, 'Ca 2')
})

test('unknown network outcome reconciles committed local value without repeat write', () => {
  const state = edit(load([row('A')]), 'A', { shift_code: 'Ca 2' })
  const next = reconcileSchedule({ ...state, needsRefresh: true }, [row('A', 'Ca 2', 12)])
  assert.equal(scheduleHasChanges(next), false)
  assert.deepEqual(next.conflicts, {})
  assert.equal(next.needsRefresh, false)
  assert.equal(next.revisions[key('A')], 12)
})

test('unknown network outcome plus later edit requires review, not stale replay', () => {
  const state = edit(load([row('A')]), 'A', { shift_code: 'Nghỉ' })
  const next = reconcileSchedule(state, [row('A', 'Ca 2', 12)])
  assert.deepEqual(next.conflicts, { [key('A')]: true })
  assert.equal(next.drafts[key('A')].shift_code, 'Nghỉ')
})

test('invalid revision cannot become a zero baseline or partial acknowledgement', () => {
  assert.throws(() => load([{ ...row('A'), revision: undefined }]), /phiên bản/)
  const state = load([row('A')])
  assert.throws(() => acknowledgeSchedule(state, [{ key: key('A'), after: { shift_code: 'Ca 2' } }], {}), /phiên bản/)
  assert.equal(state.saved[key('A')].shift_code, 'Ca 1')
  assert.equal(state.revisions[key('A')], 1)
})

test('blank imported or copied cells ignore stale note and time metadata', () => {
  assert.deepEqual(scheduleCellValue({ shift_code: '', note: 'old', overtime_shift: 'TC Ca 1', start_time: '09:00', combo_sold: true, revision: 9 }), emptyScheduleCell())
  const state = edit(load([]), 'A', { shift_code: '', note: 'old' })
  assert.equal(scheduleHasChanges(state), false)
})
