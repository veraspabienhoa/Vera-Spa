import test from 'node:test'
import assert from 'node:assert/strict'
import { holidayPayload, holidayPeriodsLabel, vietnamToday } from '../src/lib/holidayLeave.js'

test('Vietnam calendar dates and inclusive full-day labels', () => {
  assert.equal(vietnamToday(new Date('2026-10-19T18:00:00Z')), '2026-10-20')
  assert.equal(holidayPeriodsLabel({ mode: 'day', periods: [{ starts_at: '2026-10-19T17:00:00Z', ends_at: '2026-10-20T17:00:00Z' }] }), '20-10-2026')
  assert.equal(holidayPeriodsLabel({ mode: 'range', periods: [{ starts_at: '2026-10-19T17:00:00Z', ends_at: '2026-10-22T17:00:00Z' }] }), '20-10-2026 → 22-10-2026')
})
test('Overnight hourly period preserves dates and 24-hour time', () => {
  assert.equal(holidayPeriodsLabel({ mode: 'hours', periods: [{ starts_at: '2026-10-20T16:00:00Z', ends_at: '2026-10-20T19:00:00Z' }] }), '20-10-2026 23:00:00 → 21-10-2026 02:00:00')
})
test('Changed scopes and modes send only applicable fields', () => {
  const form = { scope: 'departments', departments: ['locker'], employees: ['An'], mode: 'hours', day: '2026-10-20', dates: ['2026-10-21'], dateFrom: '2026-10-20', dateTo: '2026-10-22', startsAt: '2026-10-20T23:00', endsAt: '2026-10-21T02:00', note: ' Lễ ' }
  assert.deepEqual(holidayPayload(form, 'request'), { request_id: 'request', scope: 'departments', mode: 'hours', note: 'Lễ', departments: ['locker'], employees: [], dates: [], date_from: null, date_to: null, starts_at: form.startsAt, ends_at: form.endsAt })
  form.scope = 'employees'; form.mode = 'dates'
  assert.deepEqual(holidayPayload(form, 'retry').dates, ['2026-10-21'])
  assert.deepEqual(holidayPayload(form, 'retry').departments, [])
})

test('Hours combine with selected dates and clear when switching to all day',()=>{
 const form={scope:'all',mode:'dates',dates:['2026-10-10','2026-10-12'],note:'Lễ',timeMode:'hours',timeFrom:'17:00:00',timeTo:'00:00:00'}
 const payload=holidayPayload(form,'id')
 assert.deepEqual(payload.dates,form.dates);assert.equal(payload.time_from,'17:00:00');assert.equal(payload.time_to,'00:00:00')
 assert.equal(holidayPayload({...form,timeMode:'all_day'},'id').time_from,undefined)
})
