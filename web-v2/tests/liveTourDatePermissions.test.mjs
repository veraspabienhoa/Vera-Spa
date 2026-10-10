import test from 'node:test'
import assert from 'node:assert/strict'
import { TOUR_DATE_SECTIONS, TOUR_DATE_PRESET_IDS, resolveTourDatePolicy, allowedTourPresets, normalizeTourDateFilters, tourDateFiltersReady, tourDatePolicyKey, tourProfileKey, readTourDateSelection, saveTourDateSelection, tourExportSection } from '../src/lib/liveTourDatePermissions.js'

const user = (permissions = {}, id = 'account-a') => ({ id, role: 'letan', permissions: { live_tour_pending_view: true, live_tour_invoice_view: true, live_tour_paid_invoice_view: true, live_tour_reports_view: true, live_tour_history_view: true, ...permissions } })
const contract = (sections = {}) => ({ date_filters: { version: 1, server_today: '2026-10-10', sections: Object.fromEntries(TOUR_DATE_SECTIONS.map(section => [section, sections[section] || ['today']])) } })

test('each of the 32 date grants inherits only its section read permission until explicitly configured', () => {
  for (const section of TOUR_DATE_SECTIONS) {
    assert.deepEqual(allowedTourPresets(resolveTourDatePolicy(user()), section), TOUR_DATE_PRESET_IDS)
    for (const preset of TOUR_DATE_PRESET_IDS) {
      const feature = `live_tour_${section}_date_${preset.replaceAll('-', '_')}`
      const denied = resolveTourDatePolicy(user({ [feature]: false }))
      assert.equal(denied.sections[section].includes(preset), false, feature)
      assert.equal(denied.sections[section].length, 7)
      assert.equal(resolveTourDatePolicy(user({ [feature]: true })).sections[section].includes(preset), true)
    }
  }
})

test('section prerequisites remain mandatory, independent of payment and operation grants', () => {
  const policy = resolveTourDatePolicy(user({ live_tour_pending_view: false, live_tour_paid_invoice_view: false, live_tour_reports_view: false, live_tour_history_view: false, live_tour_payment: true, live_tour_operate: true, live_tour_admin: true,
    ...Object.fromEntries(TOUR_DATE_SECTIONS.flatMap(section => TOUR_DATE_PRESET_IDS.map(preset => [`live_tour_${section}_date_${preset.replaceAll('-', '_')}`, true]))) }))
  assert.ok(TOUR_DATE_SECTIONS.every(section => policy.sections[section].length === 0))
  assert.equal(resolveTourDatePolicy(user({ live_tour_invoice_view: false })).sections.pending.length, 0)
  assert.equal(resolveTourDatePolicy(user({ live_tour_history_view: false, live_tour_backup: true })).sections.history.length, 8)
})

test('standalone reports and exports retain section-only access without board view', () => {
  const policy = resolveTourDatePolicy(user({ live_tour_view: false }))
  assert.ok(TOUR_DATE_SECTIONS.every(section => policy.sections[section].length === 8))
})

test('server contract and explicit profile revocations intersect; unknown versions fail closed', () => {
  assert.deepEqual(resolveTourDatePolicy(user(), contract()).sections.invoices, ['today'])
  assert.deepEqual(resolveTourDatePolicy(user({ live_tour_invoices_date_today: false }), contract()).sections.invoices, [])
  assert.deepEqual(resolveTourDatePolicy(user({ live_tour_paid_invoice_view: false }), { ...contract(), paid_invoice_view: true }).sections.invoices, [])
  assert.deepEqual(resolveTourDatePolicy(user(), { date_filters: { version: 2, sections: {} } }).sections.reports, [])
  assert.deepEqual(resolveTourDatePolicy(user(), { date_filters: null }).sections.pending, [])
})

test('Admin always retains every preset, including with empty or denied saved settings', () => {
  const policy = resolveTourDatePolicy({ ...user({ live_tour_reports_view: false }), role: 'Admin' }, contract({ reports: [] }))
  assert.ok(TOUR_DATE_SECTIONS.every(section => policy.sections[section].length === 8))
})

test('revoked/stored custom ranges cannot widen fallback; paid Today defaults are server anchored', () => {
  const filters = normalizeTourDateFilters({ preset: 'custom', date_from: '2000-01-01', date_to: '2099-12-31', date: '2001-01-01', employee: 'An' }, ['today'], { serverToday: '2026-10-10' })
  assert.deepEqual(filters, { preset: 'today', date_from: '2026-10-10', date_to: '2026-10-10', date: '', employee: 'An', customer: '', service: '', bill_no: '' })
  assert.equal(normalizeTourDateFilters({ preset: 'today' }, ['week', 'month'], { preferredPreset: 'today' }).preset, 'week')
  assert.equal(normalizeTourDateFilters(null, ['all', 'yesterday'], { preferredPreset: 'yesterday' }).preset, 'yesterday')
  assert.equal(normalizeTourDateFilters({ preset: 'month' }, ['all', 'yesterday'], { preferredPreset: 'yesterday' }).preset, 'all')
})

test('Vietnam calendar ranges preserve leap, week and year boundaries using the server day', () => {
  assert.equal(normalizeTourDateFilters({ preset: 'yesterday' }, ['yesterday'], { serverToday: '2027-01-01' }).date_from, '2026-12-31')
  assert.equal(normalizeTourDateFilters({ preset: 'last-month' }, ['last-month'], { serverToday: '2024-03-01' }).date_to, '2024-02-29')
  const week = normalizeTourDateFilters({ preset: 'week' }, ['week'], { serverToday: '2026-10-11' })
  assert.equal(week.date_from, '2026-10-05'); assert.equal(week.date_to, '2026-10-11')
})

test('no grants means no request; custom-only defaults bounded but incomplete edits stay incomplete', () => {
  assert.equal(tourDateFiltersReady(normalizeTourDateFilters({}, [])), false)
  const initial = normalizeTourDateFilters(null, ['custom'], { serverToday: '2026-10-10' })
  assert.equal(initial.date_from, '2026-10-10'); assert.equal(tourDateFiltersReady(initial), true)
  const cleared = normalizeTourDateFilters({ ...initial, date_from: '' }, ['custom'], { serverToday: '2026-10-10' })
  assert.equal(cleared.date_from, ''); assert.equal(tourDateFiltersReady(cleared), false)
  assert.equal(tourDateFiltersReady({ ...initial, date_from: '2026-02-30' }), false)
  assert.equal(tourDateFiltersReady({ ...initial, date_from: '2026-10-11' }), false)
})

test('persisted selection is account and section scoped and excludes private search values', () => {
  const values = new Map(), storage = { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) }
  saveTourDateSelection(user(), 'invoices', { preset: 'custom', date_from: '2026-10-01', date_to: '2026-10-02', customer: 'Private name', employee: 'Private employee' }, storage)
  assert.equal(readTourDateSelection(user({}, 'account-b'), 'invoices', storage), null)
  assert.equal(readTourDateSelection(user(), 'reports', storage), null)
  assert.equal(readTourDateSelection(user(), 'invoices', storage).preset, 'custom')
  assert.doesNotMatch([...values.values()].join(), /Private/)
  const first = resolveTourDatePolicy(user(), contract())
  assert.notEqual(tourDatePolicyKey(user(), first), tourDatePolicyKey(user({}, 'account-b'), first))
  assert.notEqual(tourDatePolicyKey(user(), first), tourDatePolicyKey(user(), resolveTourDatePolicy(user(), contract({ invoices: [] }))))
  assert.notEqual(tourProfileKey(user()), tourProfileKey(user({ live_tour_paid_invoice_view: false })))
})

test('export kinds map to their own independently granted section', () => {
  for (const kind of ['revenue', 'reports', 'tip', 'employee', 'performance']) assert.equal(tourExportSection(kind), 'reports')
  assert.equal(tourExportSection('paid'), 'invoices'); assert.equal(tourExportSection('pending'), 'pending')
  assert.equal(tourExportSection('breaks'), 'history'); assert.equal(tourExportSection('board'), '')
})
