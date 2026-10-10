import assert from 'node:assert/strict'
import test from 'node:test'
import { canEditCatalogFeature, catalogAllowedFeatures, catalogFeatureAllowed, datePermissionSaveProblem, hasAnyDateParent, permissionFeatureKeys, supportsDateFilterPolicy } from '../src/lib/permissionCatalog.js'

const presets = ['all', 'today', 'yesterday', 'week', 'last_week', 'month', 'last_month', 'custom']
const sections = {
  pending: ['live_tour_pending_view', 'live_tour_invoice_view'],
  invoices: ['live_tour_paid_invoice_view'],
  reports: ['live_tour_reports_view'],
  history: [],
}
const dateFeatures = Object.fromEntries(Object.keys(sections).flatMap((section) => presets.map((preset) => [`live_tour_${section}_date_${preset}`, preset])))
const source = {
  date_filter_policy_version: 1,
  date_filter_features: dateFeatures,
  date_filter_parent_any: Object.fromEntries(presets.map((preset) => [`live_tour_history_date_${preset}`, ['live_tour_history_view', 'live_tour_backup']])),
  dependencies: Object.fromEntries(Object.entries(sections).flatMap(([section, parents]) => presets.map((preset) => [`live_tour_${section}_date_${preset}`, parents]))),
  groups: { 'Live Tour': { ...dateFeatures, live_tour_view: 'Board', live_tour_payment: 'Payment', live_tour_history_view: 'History', live_tour_backup: 'Backup', ...Object.fromEntries(Object.values(sections).flat().map((key) => [key, key])) } },
  defaults: Object.fromEntries(['quanly', 'letan', 'leader', 'nhanvien', 'support', 'locker', 'tapvu'].map((role) => [role, ['quanly', 'letan'].includes(role) ? ['live_tour_view', 'live_tour_payment'] : ['live_tour_view']])),
  legacy_inheritance: Object.fromEntries(Object.values(sections).flat().map((key) => [key, 'live_tour_payment'])),
  role_overrides: {}, account_overrides: {},
}

for (const role of Object.keys(source.defaults)) {
  test(`first Admin load shows inherited effective dates for ${role}`, () => {
    const checked = catalogAllowedFeatures(role, '', source)
    assert.equal(checked.filter((key) => key in dateFeatures).length, ['quanly', 'letan'].includes(role) ? 24 : 0)
    for (const [section, parents] of Object.entries(sections)) {
      for (const preset of presets) {
        assert.equal(catalogFeatureAllowed(`live_tour_${section}_date_${preset}`, role, '', source), parents.length > 0 && parents.every((parent) => catalogFeatureAllowed(parent, role, '', source)))
      }
    }
  })
}

for (const [feature] of Object.entries(dateFeatures)) {
  test(`${feature}: account overrides role, but denied read parents win`, () => {
    const current = structuredClone(source)
    const parents = current.dependencies[feature]
    const anyParents = current.date_filter_parent_any[feature] || []
    current.role_overrides.letan = { ...Object.fromEntries([...parents, ...anyParents].map((key) => [key, true])), [feature]: false }
    assert.equal(catalogFeatureAllowed(feature, 'letan', 'operator', current), false)
    current.account_overrides.operator = { [feature]: true }
    assert.equal(catalogFeatureAllowed(feature, 'letan', 'operator', current), true)
    current.account_overrides.operator = { [feature]: true, ...Object.fromEntries([...parents, ...anyParents].map((key) => [key, false])) }
    assert.equal(catalogFeatureAllowed(feature, 'letan', 'operator', current), false)
  })
}

test('an explicit all-false account stays denied, reset follows current role dates', () => {
  const current = structuredClone(source)
  current.role_overrides.letan = Object.fromEntries(Object.keys(dateFeatures).map((key) => [key, key.endsWith('_today')]))
  current.account_overrides.operator = Object.fromEntries(Object.keys(dateFeatures).map((key) => [key, false]))
  assert.equal(catalogAllowedFeatures('letan', 'operator', current).filter((key) => key in dateFeatures).length, 0)
  assert.deepEqual(catalogAllowedFeatures('letan', '', current).filter((key) => key in dateFeatures), ['live_tour_pending_date_today', 'live_tour_invoices_date_today', 'live_tour_reports_date_today'])
})

test('section-only explicit read accounts keep their direct export date grants', () => {
  const current = structuredClone(source)
  current.account_overrides.operator = { live_tour_view: false }
  assert.equal(catalogAllowedFeatures('letan', 'operator', current).filter((key) => key in dateFeatures).length, 24)
})

test('backup-only history checks never imply audit/history read', () => {
  const current = structuredClone(source)
  current.account_overrides.operator = { live_tour_history_view: false, live_tour_backup: true }
  const checked = catalogAllowedFeatures('letan', 'operator', current)
  assert.equal(checked.filter((key) => key.startsWith('live_tour_history_date_')).length, 8)
  assert.equal(checked.includes('live_tour_history_view'), false)
  assert.equal(hasAnyDateParent('live_tour_history_date_today', checked, current), true)
  assert.equal(hasAnyDateParent('live_tour_history_date_today', [], current), false)
})

test('admin retains all features and page catalog contains each key once', () => {
  const current = structuredClone(source)
  current.pages = [{ features: current.groups['Live Tour'] }, { features: dateFeatures }]
  assert.equal(permissionFeatureKeys(current).length, Object.keys(current.groups['Live Tour']).length)
  assert.equal(catalogAllowedFeatures('admin', 'admin', current).length, permissionFeatureKeys(current).length)
})

for (const version of [undefined, 0, 2, '1']) {
  test(`date controls stay hidden without supported numeric v1 catalog (${String(version)})`, () => {
    const current = { ...source, date_filter_policy_version: version }
    assert.equal(supportsDateFilterPolicy(current), false)
    for (const key of Object.keys(dateFeatures)) {
      assert.equal(canEditCatalogFeature(key, current), false)
      assert.equal(catalogFeatureAllowed(key, 'admin', '', current), false)
    }
    assert.equal(permissionFeatureKeys(current).some((key) => key in dateFeatures), false)
    assert.equal(canEditCatalogFeature('live_tour_reports_view', current), true)
  })
}

test('known date IDs are hidden on an old catalog even without date metadata', () => {
  const current = { ...source, date_filter_features: undefined, date_filter_policy_version: undefined }
  assert.equal(permissionFeatureKeys(current).some((key) => key in dateFeatures), false)
})

test('cached v1 catalog cannot turn an old backend generic success into date-policy confirmation', () => {
  assert.notEqual(datePermissionSaveProblem({ ok: true, revision: 13 }, { ...source, revision: 13 }), '')
})

test('date save must be acknowledged and read back with the supported policy and revision', () => {
  const result = { ok: true, date_filter_policy_version: 1, revision: 13 }
  assert.notEqual(datePermissionSaveProblem(result, null), '')
  assert.notEqual(datePermissionSaveProblem(result, { revision: 13 }), '')
  assert.notEqual(datePermissionSaveProblem(result, { ...source, revision: 12 }), '')
  assert.notEqual(datePermissionSaveProblem({ ...result, revision: undefined }, { ...source, revision: 13 }), '')
  assert.equal(datePermissionSaveProblem(result, { ...source, revision: 13 }), '')
  assert.equal(datePermissionSaveProblem(result, { ...source, revision: 14 }), '')
})
