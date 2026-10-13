import { formatVeraDate } from './veraDate.js'

export const salarySource = value => value === 'attendance' ? 'attendance' : 'schedule'

export const salarySourceLabel = value => salarySource(value) === 'attendance' ? 'Chấm công' : 'Thống kê'

export const PAYROLL_BACKEND_UPDATE_REQUIRED = 'Cần cập nhật máy chủ để dùng nguồn lương từng nhân viên và cách tính đi trễ mới. Hiện chỉ xem dữ liệu đã lưu; tính lương, sửa, lưu, xuất và gửi email đang tạm khóa. Sau khi cập nhật máy chủ, bấm Làm mới.'

export const supportsPayrollContract = result => result?.hc_payroll_contract === 1
  && Number.isSafeInteger(result.employee_config_revision) && result.employee_config_revision >= 0

export const hasPayrollRevisions = result => Number.isSafeInteger(result?.draft_revision) && result.draft_revision >= 0
  && Number.isSafeInteger(result?.history_revision) && result.history_revision >= 0

// A capability may have been cached before a backend rollback. New operations
// must never reach an old handler that ignores unknown fields or missing rows.
export const versionedPayrollPath = path => path.replace(/^\/v2\/department-payroll(?=\/)/, '/v2/department-payroll-v2')

export function normalizeSalaryConfigTables(tables = {}) {
  return Object.fromEntries(['operations', 'tapvu'].map(group => [group,
    (tables[group] || []).map(row => ({ ...row, salary_source: salarySource(row.salary_source) })),
  ]))
}

export const hasPendingPayrollEvidence = rows => rows.some(row => Boolean(row.attendance_pending || row.configuration_pending))

const isConfigurationIssue = issue => /^missing_rate:|^\d{4}-\d{2}-\d{2}:missing_(shift|overtime)_times$/.test(issue)
const isLateIssue = issue => /^(unverified_late_event|late_event_schedule_changed|late_event_evidence_changed|late_payable_basis_mismatch):/.test(issue)

export function payrollPendingLabel(row) {
  if (!row.configuration_pending) return 'Chờ xác nhận công'
  const issues = row.configuration_issues || []
  if (issues.length && issues.every(isConfigurationIssue) && !row.attendance_pending) return 'Chờ cấu hình ca/đơn giá'
  if (issues.length && issues.every(isLateIssue) && !row.attendance_pending) return 'Chờ đối chiếu đi trễ'
  return 'Chờ đối chiếu lương'
}

export function payrollPendingDetails(row) {
  const rateLabels = { rate_ca1: 'Ca 1', rate_ca2_before_22: 'Ca 2 trước 22h', rate_ca2_after_22: 'Ca 2 sau 22h', default_base_salary: 'lương tháng' }
  const lateLabels = {
    unverified_late_event: 'Sự kiện đi trễ chưa được xác minh',
    late_event_schedule_changed: 'Ca làm việc hiện tại không khớp với ca ghi nhận khi xử lý đi trễ',
    late_event_evidence_changed: 'Dữ liệu chấm công hiện tại không khớp với dữ liệu ghi nhận khi xử lý đi trễ',
    late_payable_basis_mismatch: 'Thời gian tính lương không khớp với cơ sở tính đi trễ',
  }
  const details = [...new Set(row.configuration_issues || [])].map(issue => {
    const [code, value] = String(issue).split(':')
    if (code === 'missing_rate') return `Chưa cấu hình đơn giá ${rateLabels[value] || value}. Kiểm tra mức riêng của nhân viên hoặc mức chung của bộ phận.`
    if (value === 'missing_shift_times') return `${formatVeraDate(code, code)}: thiếu giờ bắt đầu/kết thúc ca. Kiểm tra lịch phân ca và cài đặt ca của bộ phận.`
    if (value === 'missing_overtime_times') return `${formatVeraDate(code, code)}: thiếu giờ bắt đầu/kết thúc tăng ca. Kiểm tra lịch tăng ca.`
    if (lateLabels[code]) return `${lateLabels[code]} (sự kiện ${value || '—'}). Kiểm tra chấm công, phân ca và vi phạm đi trễ.`
    return `Cần kiểm tra dữ liệu tính lương (mã: ${issue}).`
  })
  if (row.configuration_pending && !details.length) details.push('Bảng lương chưa có mã lỗi chi tiết. Bấm Tính lương để kiểm tra lại dữ liệu hiện tại.')
  if (row.attendance_pending) {
    const dates = [...new Set(row.pending_dates || [])].map(date => formatVeraDate(date, date))
    details.push(`Dữ liệu chấm công chưa đủ điều kiện tính lương${dates.length ? `: ${dates.join(', ')}` : ''}. Kiểm tra bản ghi đã đồng bộ, xác minh và lịch phân ca.`)
  }
  return details.join('\n\n')
}

// Payroll sends decimal strings from exact seconds. Keep those decimals through
// half-up rounding instead of rounding the two-decimal display time again.
function decimalRatio(value) {
  const match = String(value ?? 0).match(/^\+?(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/)
  if (!match) return [0n, 1n]
  const scale = (match[2] || '').length - Number(match[3] || 0)
  if (!Number.isInteger(scale) || Math.abs(scale) > 100) return [0n, 1n]
  const digits = BigInt(match[1] + (match[2] || ''))
  return scale >= 0 ? [digits, 10n ** BigInt(scale)] : [digits * 10n ** BigInt(-scale), 1n]
}

export function monthlyPayrollSalary(baseSalary, workDays, standardDays = 26) {
  const [base, baseScale] = decimalRatio(baseSalary)
  const [days, dayScale] = decimalRatio(workDays)
  const [standard, standardScale] = decimalRatio(standardDays)
  if (standard <= 0n) return 0
  const numerator = base * days * standardScale
  const denominator = baseScale * dayScale * standard
  return Number((2n * numerator + denominator) / (2n * denominator))
}

export function recalculateDepartmentPayroll(source, config, changedField) {
  const row = { ...source }
  const number = (key) => Math.max(0, Number(row[key] || 0))
  const actualEntitlement = row.hc_late_original_penalty != null
  const monthlyBaseEdit = config.calculation_mode === 'monthly' && changedField === 'base_salary'
  const monthlySeconds = Number(config.standard_day_hours || 8) * 3600 * Number(config.standard_month_days || 26)
  if (Array.isArray(row.late_penalty_adjustments) && (!actualEntitlement || monthlyBaseEdit)) {
    row.late_penalty_adjustments = row.late_penalty_adjustments.map(event => {
      const hasSecondBasis = event.paid_work_day_seconds != null && event.including_late_work_day_seconds != null
      const hasMonthlyBasis = config.calculation_mode === 'monthly'
        && (hasSecondBasis || (event.paid_work_days != null && event.including_late_work_days != null
          && Number.isFinite(Number(event.paid_work_days)) && Number.isFinite(Number(event.including_late_work_days))))
      const naturalLoss = hasMonthlyBasis
        ? Math.max(0, monthlyPayrollSalary(number('base_salary'), hasSecondBasis ? event.including_late_work_day_seconds : event.including_late_work_days, hasSecondBasis ? monthlySeconds : config.standard_month_days || 26)
          - monthlyPayrollSalary(number('base_salary'), hasSecondBasis ? event.paid_work_day_seconds : event.paid_work_days, hasSecondBasis ? monthlySeconds : config.standard_month_days || 26))
        : Math.max(0, Number(event.unpaid_wage || 0))
      const unpaidWage = actualEntitlement && hasMonthlyBasis && (event.unpaid_seconds != null || event.unpaid_hours != null)
        ? monthlyPayrollSalary(number('base_salary'), event.unpaid_seconds ?? event.unpaid_hours,
          Number(config.standard_day_hours || 8) * Number(config.standard_month_days || 26) * (event.unpaid_seconds != null ? 3600 : 1))
        : naturalLoss
      const original = Math.max(0, Number(event.original_penalty || 0))
      if (!actualEntitlement) return { ...event, unpaid_wage: unpaidWage, credit: Math.min(unpaidWage, original) }
      const additional = event.approved ? 0 : unpaidWage
      return { ...event, unpaid_wage: unpaidWage, additional_penalty: additional,
        rounding_adjustment: unpaidWage - naturalLoss, credit: Math.max(0, original - additional) }
    })
    row.unpaid_late_wage = row.late_penalty_adjustments.reduce((sum, event) => sum + event.unpaid_wage, 0)
    if (actualEntitlement) {
      row.hc_late_original_penalty = row.late_penalty_adjustments.reduce((sum, event) => sum + Number(event.original_penalty || 0), 0)
      row.hc_late_additional_penalty = row.late_penalty_adjustments.reduce((sum, event) => sum + event.additional_penalty, 0)
      row.late_wage_rounding_adjustment = row.late_penalty_adjustments.reduce((sum, event) => sum + event.rounding_adjustment, 0)
      row.late_penalty_credit = Math.max(0, row.hc_late_original_penalty - row.hc_late_additional_penalty)
      row.late_penalty_surcharge = Math.max(0, row.hc_late_additional_penalty - row.hc_late_original_penalty)
    } else {
      row.late_penalty_credit = Math.min(number('late_penalty'), row.late_penalty_adjustments.reduce((sum, event) => sum + event.credit, 0))
    }
  }
  // Read-only time buckets are display-rounded. Preserve the server's exact
  // salary when editing allowances or deductions, including advance refreshes.
  const preserveSalary = Number.isFinite(row.salary) && !(config.calculation_mode === 'monthly' && changedField === 'base_salary')
  const hasWorkSeconds = row.payroll_time_basis?.work_day_seconds != null
  const salary = preserveSalary ? row.salary : config.calculation_mode === 'monthly'
    ? Math.max(0, monthlyPayrollSalary(number('base_salary'), hasWorkSeconds ? row.payroll_time_basis.work_day_seconds : row.payroll_time_basis?.work_days ?? number('work_days'), hasWorkSeconds ? monthlySeconds : config.standard_month_days || 26) - Number(row.late_wage_rounding_adjustment || 0))
    : Math.round((
      number('hours_ca1') * Number(config.rate_ca1 || 0)
      + number('hours_ca2_before_22') * Number(config.rate_ca2_before_22 || 0)
      + number('hours_ca2_after_22') * Number(config.rate_ca2_after_22 || 0)
    ) * (row.probation_rate === 0.75 ? 0.75 : 1),
    )
  row.salary = salary
  row.total_salary = row.salary + ['full_allowance', 'attendance_bonus', 'responsibility', 'seniority', 'combo_sales'].reduce((sum, key) => sum + number(key), 0)
  row.effective_late_penalty = actualEntitlement
    ? Math.max(0, number('late_penalty') - number('hc_late_original_penalty')) + number('hc_late_additional_penalty')
    : Math.max(0, number('late_penalty') - number('late_penalty_credit'))
  row.net_salary = row.total_salary - ['violation_penalty', 'advance'].reduce((sum, key) => sum + number(key), 0) - row.effective_late_penalty
  if (hasPendingPayrollEvidence([row])) Object.assign(row, { salary: null, total_salary: null, net_salary: null })
  return row
}

// Account/permission changes remount the panel. All other changes to a payroll
// snapshot invalidate this generation before React renders the next version.
// A late response remains stale even if its transport ignores AbortSignal.
export function createPayrollOperationScope() {
  let generation = 0
  let controller = null
  let mounted = true
  const invalidate = () => {
    generation += 1
    controller?.abort()
    controller = null
  }
  return {
    invalidate,
    mount() { mounted = true },
    dispose() { mounted = false; invalidate() },
    start() {
      invalidate()
      const version = generation
      controller = new AbortController()
      const signal = controller.signal
      const isCurrent = () => mounted && generation === version && !signal.aborted
      return {
        signal,
        isCurrent,
        assertCurrent() {
          if (!isCurrent()) throw new DOMException('Bảng lương đã thay đổi.', 'AbortError')
        },
      }
    },
  }
}
