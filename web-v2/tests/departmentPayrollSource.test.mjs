import test from 'node:test'
import assert from 'node:assert/strict'
import { createPayrollOperationScope, hasPendingPayrollEvidence, monthlyPayrollSalary, normalizeSalaryConfigTables, supportsPayrollContract, versionedPayrollPath, payrollPendingLabel, recalculateDepartmentPayroll, salarySource } from '../src/lib/departmentPayrollSource.js'

test('legacy source defaults to schedule; each config carries one explicit exclusive source', () => {
  const original = { operations: [{ employee_username: 'a' }, { employee_username: 'b', salary_source: 'attendance' }], tapvu: [{ employee_username: 'c', salary_source: 'schedule' }] }
  const normalized = normalizeSalaryConfigTables(original)
  assert.deepEqual(normalized.operations.map(row => row.salary_source), ['schedule', 'attendance'])
  assert.equal(normalized.tapvu[0].salary_source, 'schedule')
  assert.equal(original.operations[0].salary_source, undefined)
  assert.equal(salarySource(null), 'schedule')
})

test('edits preserve per-employee source and opaque evidence snapshot and never double-deduct late wage', () => {
  const snapshot = { month: '2026-10', source: 'attendance', proof: 'opaque-server-value' }
  const row = { calculation_source: 'attendance', calculation_snapshot: snapshot, hours_ca1: 7, late_penalty: 50000, late_penalty_credit: 30000, advance: 10000, responsibility: 10000 }
  const result = recalculateDepartmentPayroll(row, { calculation_mode: 'hourly', rate_ca1: 30000 })
  assert.equal(result.salary, 210000)
  assert.equal(result.effective_late_penalty, 20000)
  assert.equal(result.net_salary, 190000)
  assert.equal(result.late_penalty, 50000)
  assert.equal(result.calculation_snapshot, snapshot)
  assert.equal(result.calculation_source, 'attendance')
  assert.equal(recalculateDepartmentPayroll({ ...row, late_penalty: 10000 }, { calculation_mode: 'hourly', rate_ca1: 30000 }).effective_late_penalty, 0)
})

for (const pending of ['attendance_pending', 'configuration_pending']) test(`${pending} prevents edits from creating payable amounts`, () => {
  const result = recalculateDepartmentPayroll({ [pending]: true, hours_ca1: 8, responsibility: 100000, advance: 50000 }, { rate_ca1: 30000 })
  assert.equal(result.salary, null); assert.equal(result.total_salary, null); assert.equal(result.net_salary, null)
  assert.equal(hasPendingPayrollEvidence([result]), true)
  assert.match(payrollPendingLabel(result), /Chờ/)
})

test('new requests, snapshot changes and unmount invalidate requests even if transport ignores abort', () => {
  const scope = createPayrollOperationScope()
  const first = scope.start(), second = scope.start()
  assert.equal(first.signal.aborted, true); assert.equal(first.isCurrent(), false)
  assert.throws(() => first.assertCurrent(), { name: 'AbortError' })
  assert.equal(second.isCurrent(), true)
  scope.invalidate(); assert.equal(second.isCurrent(), false)
  const third = scope.start(); scope.dispose(); assert.equal(third.isCurrent(), false)
  scope.mount(); const fourth = scope.start(); assert.equal(fourth.isCurrent(), true)
  assert.equal(third.isCurrent(), false)
})

test('monthly base edit recomputes unpaid late wage and same-event credit without restoring salary', () => {
  const cfg = { calculation_mode: 'monthly', standard_month_days: 30 }
  const row = { base_salary: 600000, work_days: 2, late_penalty: 50000, probation_rate: 0.75,
    late_penalty_adjustments: [{ original_penalty: 50000, unpaid_wage: 20000, credit: 20000, paid_work_days: '2', including_late_work_days: '3' }] }
  const original = recalculateDepartmentPayroll(row, cfg)
  assert.equal(original.salary, 40000); assert.equal(original.unpaid_late_wage, 20000); assert.equal(original.net_salary, 10000)
  const edited = recalculateDepartmentPayroll({ ...original, base_salary: 900000 }, cfg, 'base_salary')
  assert.equal(edited.salary, 60000); assert.equal(edited.unpaid_late_wage, 30000)
  assert.equal(edited.late_penalty_credit, 30000); assert.equal(edited.effective_late_penalty, 20000); assert.equal(edited.net_salary, 40000)
  const smallerFine = recalculateDepartmentPayroll({ ...edited, late_penalty: 10000 }, cfg)
  assert.equal(smallerFine.late_penalty_credit, 10000); assert.equal(smallerFine.effective_late_penalty, 0)
  const restoredFine = recalculateDepartmentPayroll({ ...smallerFine, late_penalty: 50000 }, cfg)
  assert.equal(restoredFine.late_penalty_credit, 30000); assert.equal(restoredFine.effective_late_penalty, 20000)
  assert.equal(row.late_penalty_adjustments[0].unpaid_wage, 20000)
})

test('money-only edits preserve authoritative salary instead of rebuilding rounded time buckets', () => {
  const row = { hours_ca1: 7.97, salary: 239167, responsibility: 10000, advance: 1000 }
  const hourly = recalculateDepartmentPayroll(row, { rate_ca1: 30000 }, 'responsibility')
  assert.equal(hourly.salary, 239167); assert.equal(hourly.net_salary, 248167)
  const monthly = recalculateDepartmentPayroll({ ...row, base_salary: 6000000, work_days: 0.99 }, { calculation_mode: 'monthly', standard_month_days: 26 }, 'advance')
  assert.equal(monthly.salary, 239167)
})

test('monthly edits use exact decimal time basis and half-up cents at the final currency unit', () => {
  assert.equal(monthlyPayrollSalary(100, '0.145', 1), 15)
  assert.equal(monthlyPayrollSalary(100, '0.1449999999999999999999999999', 1), 14)
  assert.equal(monthlyPayrollSalary(100, '1.45E-1', 1), 15)
  const row = { base_salary: 100, work_days: 0.14, salary: 10, payroll_time_basis: { work_days: '0.145' } }
  assert.equal(recalculateDepartmentPayroll(row, { calculation_mode: 'monthly', standard_month_days: 1 }, 'base_salary').salary, 15)
})

for (const approved of [true, false]) test(`actual monthly entitlement uses ${approved ? 'one' : 'two'} times independently rounded late wage after base edit`, () => {
  const cfg = { calculation_mode: 'monthly', standard_month_days: 26, standard_day_hours: 8 }
  // Seven seconds at 27,000/hour independently round to 53đ. Display days
  // are deliberately rounded to 1 and cannot be used for the salary basis.
  const row = { base_salary: 5616000, work_days: 1, salary: 215947, payroll_time_basis: { work_days: '0.9997569444444444444444444444' },
    late_penalty: approved ? 53 : 105, hc_late_original_penalty: approved ? 53 : 105,
    hc_late_additional_penalty: approved ? 0 : 53, late_wage_rounding_adjustment: 1,
    late_penalty_adjustments: [{ unpaid_seconds: '7', unpaid_hours: '0.001944444444444444444444444444', paid_work_days: '0.9997569444444444444444444444', including_late_work_days: '1', approved, original_penalty: approved ? 53 : 105 }] }
  const updated = recalculateDepartmentPayroll(row, cfg, 'base_salary')
  assert.equal(updated.salary, 215947); assert.equal(updated.unpaid_late_wage, 53)
  assert.equal(updated.effective_late_penalty, approved ? 0 : 53)
  assert.equal(216000 - updated.net_salary, approved ? 53 : 106)
  const higher = recalculateDepartmentPayroll({ ...updated, base_salary: 11232000 }, cfg, 'base_salary')
  assert.equal(higher.unpaid_late_wage, 105)
  assert.equal(higher.effective_late_penalty, approved ? 0 : 105)
  assert.equal(432000 - higher.net_salary, approved ? 105 : 210)
})

test('allowance edits preserve actual-entitlement server values and unrelated late fines', () => {
  const row = { salary: 100000, responsibility: 10000, late_penalty: 250,
    hc_late_original_penalty: 200, hc_late_additional_penalty: 300, unpaid_late_wage: 300,
    late_penalty_adjustments: [{ original_penalty: 200, unpaid_wage: 300, approved: false }] }
  const edited = recalculateDepartmentPayroll(row, { calculation_mode: 'hourly' }, 'responsibility')
  assert.equal(edited.salary, 100000); assert.equal(edited.unpaid_late_wage, 300)
  assert.equal(edited.effective_late_penalty, 350); assert.equal(edited.net_salary, 109650)
})

test('monthly base preview prefers authoritative work seconds over recurring-day approximations', () => {
  const config = { calculation_mode: 'monthly', standard_month_days: 26, standard_day_hours: 8 }
  const row = { base_salary: 5616000, salary: 0, work_days: 0, payroll_time_basis: { work_day_seconds: '7', work_days: '0.0002430555555555555555555555555' } }
  assert.equal(recalculateDepartmentPayroll(row, config, 'base_salary').salary, 53)
})

test('monthly late natural loss uses authoritative day seconds and keeps approved reduction exactly one wage', () => {
  const config = { calculation_mode: 'monthly', standard_month_days: 26, standard_day_hours: 8 }
  const row = { base_salary: 5616000, salary: 0, payroll_time_basis: { work_day_seconds: '28793', work_days: '0.9997569444444444444444444444' },
    late_penalty: 53, hc_late_original_penalty: 53, hc_late_additional_penalty: 0,
    late_penalty_adjustments: [{ unpaid_seconds: '7', paid_work_day_seconds: '28793', including_late_work_day_seconds: '28800', approved: true, original_penalty: 53 }] }
  const result = recalculateDepartmentPayroll(row, config, 'base_salary')
  assert.equal(result.late_wage_rounding_adjustment, 1)
  assert.equal(result.salary, 215947); assert.equal(result.unpaid_late_wage, 53)
  assert.equal(result.effective_late_penalty, 0); assert.equal(216000 - result.net_salary, 53)
})

test('mixed releases require explicit exact payroll capability and a safe revision', () => {
  assert.equal(supportsPayrollContract({ hc_payroll_contract: 1, employee_config_revision: 0 }), true)
  for (const result of [{}, { employee_config_revision: 1 }, { hc_payroll_contract: 1 },
    { hc_payroll_contract: 2, employee_config_revision: 1 }, { hc_payroll_contract: '1', employee_config_revision: 1 },
    { hc_payroll_contract: 1, employee_config_revision: -1 }]) assert.equal(supportsPayrollContract(result), false)
  assert.equal(versionedPayrollPath('/v2/department-payroll/settings/employees'), '/v2/department-payroll-v2/settings/employees')
  assert.equal(versionedPayrollPath('/v2/department-payroll/combined/draft?month=2026-10'), '/v2/department-payroll-v2/combined/draft?month=2026-10')
})
