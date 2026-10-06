import { createElement, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { flushSync } from 'react-dom'
import VeraDateInput from '../components/VeraDateInput'
import { searchTextMatches } from './searchText.js'
import { getCurrentSession } from './supabase'

const API_BASE = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const PANEL_ID = 'vera-department-salary-advance-ledger'
const STYLE_ID = 'vera-department-salary-advance-ledger-style'

let currentPayload = { items: [], summary: {}, employee_catalog: [] }
let dateRoot = null

function AdvanceDate({ initialValue }) {
  const [value, setValue] = useState(initialValue)
  return createElement(VeraDateInput, { value, onChange: event => setValue(event.target.value), required: true, clearOnFocus: false, 'aria-label': 'Ngày ứng lương, định dạng dd-mm-yyyy' })
}

function renderAdvanceDate(month) {
  if (dateRoot) flushSync(() => dateRoot.render(createElement(AdvanceDate, { key: month, initialValue: defaultAdvanceDate(month) })))
}

let currentMonth = ''
let ledgerFilterMonth = ''
let payrollSummary = {}
let refreshVersion = 0

function ledgerMonth() { return ledgerFilterMonth || selectedMonth() }
function previousMonth() {
  const [year, month] = monthNow().split('-').map(Number)
  const date = new Date(year, month - 2, 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}
let refreshTimer = 0
let applyTimer = 0

const money = (value) => `${Number(value || 0).toLocaleString('vi-VN')}đ`
const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim()

function monthNow() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function selectedMonth() {
  return document.querySelector('.department-payroll-toolbar input[type="month"]')?.value || currentMonth || monthNow()
}

function defaultAdvanceDate(month) {
  const now = new Date()
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  return today.startsWith(`${month}-`) ? today : `${month}-01`
}

function formatDate(value) {
  if (/^\d{2}-\d{2}-\d{4}$/.test(String(value || ''))) return String(value)
  const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return match ? `${match[3]}-${match[2]}-${match[1]}` : clean(value).replaceAll('/', '-') || '—'
}

function parseDisplayDate(value) {
  const match = clean(value).match(/^(\d{2})-(\d{2})-(\d{4})$/)
  if (!match) return ''
  const [, day, month, year] = match
  const iso = `${year}-${month}-${day}`
  const date = new Date(`${iso}T00:00:00`)
  return !Number.isNaN(date.getTime())
    && date.getFullYear() === Number(year)
    && date.getMonth() + 1 === Number(month)
    && date.getDate() === Number(day)
    ? iso
    : ''
}

function formatMoneyInput(value) {
  const digits = String(value || '').replace(/\D/g, '')
  return digits ? Number(digits).toLocaleString('vi-VN') : ''
}

async function apiRequest(path, options = {}) {
  if (!API_BASE) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers(options.headers || {})
  if (options.body) headers.set('Content-Type', 'application/json')
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

function ensureStyles() {
  if (document.getElementById(STYLE_ID)) return
  const style = document.createElement('style')
  style.id = STYLE_ID
  style.textContent = `
    #${PANEL_ID}{display:grid;min-width:0;max-width:100%;gap:12px;margin:14px 0;padding:16px;border:1px solid #e4d6b7;border-radius:14px;background:#fffaf0}
    #${PANEL_ID} .advance-ledger-title{display:flex;align-items:center;gap:8px;flex-wrap:nowrap;min-width:0;max-width:100%;overflow-x:auto}
    #${PANEL_ID} .advance-month-filters{display:flex;gap:6px;align-items:center;white-space:nowrap}#${PANEL_ID} .advance-month-filters button{padding:7px 9px;min-height:36px;font-size:12px}#${PANEL_ID} .advance-month-filters button.active{background:#193d31;color:white}#${PANEL_ID} .advance-month-filters input{width:140px}#${PANEL_ID} h3{white-space:nowrap}#${PANEL_ID} .advance-ledger-controls{margin-left:auto;white-space:nowrap;display:flex;gap:8px;align-items:center}#${PANEL_ID} .advance-ledger-controls button{width:auto;min-height:36px;padding:7px 12px;font-size:12px}
    #${PANEL_ID} h3{margin:0;color:#72551c;font-size:18px}#${PANEL_ID} p{margin:4px 0 0;color:#746b5b;font-size:12px}
    #${PANEL_ID} [data-advance-content]{display:grid;gap:12px}#${PANEL_ID} [data-advance-content][hidden]{display:none}
    #${PANEL_ID} .advance-ledger-summary{display:flex;gap:8px;flex-wrap:wrap}#${PANEL_ID} .advance-ledger-summary span{display:grid;gap:2px;min-width:145px;padding:9px 12px;border:1px solid #eadfc8;border-radius:10px;background:#fff;color:#746b5b;font-size:11px;font-weight:700}#${PANEL_ID} .advance-ledger-summary strong{font-size:16px;color:#193d31}
    #${PANEL_ID} .advance-ledger-form{display:grid;grid-template-columns:minmax(220px,1.4fr) 160px 150px 180px minmax(180px,1fr) auto;gap:8px;align-items:end}
    #${PANEL_ID} .advance-ledger-form label{display:grid;gap:5px;font-size:11px;font-weight:800;color:#4d5f56}#${PANEL_ID} .advance-ledger-form input{width:100%;min-height:38px;padding:8px 10px;border:1px solid #cfdad4;border-radius:9px;background:#fff;color:#1f342b;font:inherit}
    #${PANEL_ID} .advance-employee-field{position:relative}#${PANEL_ID} .advance-employee-options{position:absolute;z-index:30;top:100%;left:0;right:0;display:grid;max-height:260px;overflow:auto;margin-top:4px;padding:4px;border:1px solid #cfdad4;border-radius:10px;background:#fff;box-shadow:0 10px 26px rgba(25,61,49,.16)}#${PANEL_ID} .advance-employee-options[hidden]{display:none}#${PANEL_ID} .advance-employee-options button{display:grid;gap:2px;width:100%;min-height:0;padding:9px 10px;border:0;border-radius:7px;background:#fff;color:#273f35;text-align:left;cursor:pointer}#${PANEL_ID} .advance-employee-options button:hover,#${PANEL_ID} .advance-employee-options button:focus{background:#edf7f2;outline:none}#${PANEL_ID} .advance-employee-options strong{font-size:12px}#${PANEL_ID} .advance-employee-options small{font-size:10px;color:#6c7a73}#${PANEL_ID} .advance-employee-empty{padding:10px;color:#7b857f;font-size:11px;font-weight:600}
    #${PANEL_ID} .advance-ledger-form button{min-height:38px}
    #${PANEL_ID} .vera-date-input > input[type="text"]{padding-right:40px}
    #${PANEL_ID} .vera-date-picker-button{min-height:0}
    #${PANEL_ID} .vera-native-date-picker{width:32px;min-height:0;padding:0;border:0}
    #${PANEL_ID} .advance-ledger-table-wrap{max-width:100%;overflow:auto;border:1px solid #eadfc8;border-radius:10px;background:#fff}
    #${PANEL_ID} table{width:100%;min-width:900px;border-collapse:collapse}#${PANEL_ID} th,#${PANEL_ID} td{padding:8px 9px;border-bottom:1px solid #eee7d8;text-align:left;vertical-align:middle;font-size:12px}#${PANEL_ID} th{position:sticky;top:0;background:#f6f1e7;color:#5a5142;font-size:10px;text-transform:uppercase;letter-spacing:.03em}#${PANEL_ID} td.money{text-align:right;font-weight:900;color:#193d31}#${PANEL_ID} td small{display:block;color:#7b857f;margin-top:2px}
    #${PANEL_ID} .advance-status{display:inline-flex;padding:4px 7px;border-radius:999px;font-size:10px;font-weight:900;white-space:nowrap}.advance-status.pending{background:#fff0c2;color:#815b00}.advance-status.settled{background:#dcf2e7;color:#216346}
    #${PANEL_ID} .advance-ledger-message{display:none;padding:8px 10px;border-radius:9px;font-size:12px;font-weight:700}#${PANEL_ID} .advance-ledger-message.show{display:block}#${PANEL_ID} .advance-ledger-message.error{background:#fff0ef;color:#a13831}#${PANEL_ID} .advance-ledger-message.success{background:#eaf6ef;color:#246246}
    #${PANEL_ID} .advance-empty{padding:18px;text-align:center;color:#7b857f;font-size:12px}
    .department-payroll-panel .salary-advance-panel{display:none!important}
    @media(max-width:950px){#${PANEL_ID} .advance-ledger-form{grid-template-columns:1fr 1fr}#${PANEL_ID} .advance-ledger-form label:first-child,#${PANEL_ID} .advance-ledger-form label:nth-child(5){grid-column:1/-1}#${PANEL_ID} .advance-ledger-form button{grid-column:1/-1}}
    @media(max-width:620px){#${PANEL_ID} .advance-ledger-form{grid-template-columns:1fr}#${PANEL_ID} .advance-ledger-form>*{grid-column:1!important}#${PANEL_ID} .advance-ledger-summary span{flex:1;min-width:120px}}
  `
  document.head.appendChild(style)
}

function employeeOptionLabel(item) {
  return `${clean(item.employee_name)} · ${clean(item.department_label)} · ${clean(item.employee_username)}`
}

function searchable(value) {
  return clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('vi-VN')
}

function resolveEmployee(value, selectedUsername = '') {
  const needle = clean(value)
  const username = clean(selectedUsername)
  if (username) return (currentPayload.employee_catalog || []).find((item) => clean(item.employee_username) === username)
  return (currentPayload.employee_catalog || []).find((item) => employeeOptionLabel(item) === needle)
    || (currentPayload.employee_catalog || []).find((item) => clean(item.employee_username) === needle)
}

function renderEmployeeSuggestions(panel, value = '', showAll = false) {
  const menu = panel?.querySelector('[data-advance-employee-options]')
  if (!menu) return
  const needle = searchable(value)
  const matches = (currentPayload.employee_catalog || []).filter((item) => {
    if (showAll && !needle) return true
    return searchTextMatches([item.employee_name, item.employee_username, item.department_label], needle)
  }).slice(0, 30)
  menu.replaceChildren()
  if (!matches.length) {
    const empty = document.createElement('div')
    empty.className = 'advance-employee-empty'
    empty.textContent = 'Không tìm thấy nhân viên phù hợp.'
    menu.appendChild(empty)
  } else {
    matches.forEach((item) => {
      const option = document.createElement('button')
      option.type = 'button'
      option.dataset.advanceEmployeeOption = clean(item.employee_username)
      const name = document.createElement('strong')
      name.textContent = clean(item.employee_name)
      const detail = document.createElement('small')
      detail.textContent = `${clean(item.department_label)} · ${clean(item.employee_username)}`
      option.append(name, detail)
      menu.appendChild(option)
    })
  }
  menu.hidden = false
}

function panelHtml(month) {
  return `
    <div class="advance-ledger-title">
      <div><h3>💵 NHÂN VIÊN ỨNG LƯƠNG</h3></div>
      <div class="advance-month-filters" role="group" aria-label="Lọc tháng ứng lương"><button type="button" class="secondary-button" data-advance-period="previous">Tháng trước</button><button type="button" class="secondary-button" data-advance-period="current">Tháng này</button><button type="button" class="secondary-button" data-advance-period="custom">Tuỳ chỉnh</button><input type="month" data-advance-filter-month aria-label="Tháng ứng lương tuỳ chỉnh" value="${month}" hidden></div>
      <div class="advance-ledger-controls"><button type="button" class="secondary-button" data-advance-toggle aria-expanded="false" aria-controls="vera-salary-advance-content">Hiện</button><button type="button" class="secondary-button" data-advance-refresh>↻ Làm mới</button></div>
    </div>
    <div id="vera-salary-advance-content" data-advance-content hidden>
    <div class="advance-ledger-summary">
      <span>Tổng ứng tháng<strong data-advance-total>0đ</strong></span>
      <span>Chờ trừ vào lương<strong data-advance-pending>0đ</strong></span>
      <span>Đã trừ vào lương<strong data-advance-settled>0đ</strong></span>
    </div>
    <form class="advance-ledger-form" data-advance-form>
      <label class="advance-employee-field">Tên nhân viên<input type="search" autocomplete="off" role="combobox" aria-autocomplete="list" aria-controls="vera-salary-advance-employees" aria-expanded="false" aria-label="Tìm kiếm tên nhân viên" placeholder="Tìm và chọn nhân viên trong danh sách…" data-advance-employee required><div class="advance-employee-options" id="vera-salary-advance-employees" data-advance-employee-options hidden></div></label>
      <label>Ngày<span data-advance-date></span></label>
      <label>Tháng trừ lương<input type="month" value="${month}" aria-label="Tháng trừ lương" data-advance-deduction-month required></label>
      <label>Số tiền<input type="text" inputmode="numeric" placeholder="0" data-advance-amount required></label>
      <label>Ghi chú<input type="text" maxlength="1000" placeholder="Nội dung ứng lương…" data-advance-note></label>
      <button type="submit" class="primary-button" data-advance-add>+ Thêm khoản ứng</button>
    </form>
    <div class="advance-ledger-message" data-advance-message></div>
    <div class="advance-ledger-table-wrap"><table><thead><tr><th>TT</th><th>Tên nhân viên</th><th>Ngày</th><th>Tháng trừ lương</th><th>Số tiền</th><th>Ghi chú</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody data-advance-tbody></tbody></table></div>
    </div>
  `
}

function ensurePanel() {
  const payrollPage = document.querySelector('.department-payroll-page:not(.department-payroll-config-page) .department-payroll-panel')
  if (!payrollPage) {
    dateRoot?.unmount()
    dateRoot = null
    return null
  }
  let panel = document.getElementById(PANEL_ID)
  if (panel && panel.closest('.department-payroll-panel') === payrollPage) return panel
  dateRoot?.unmount()
  dateRoot = null
  panel?.remove()
  const toolbar = payrollPage.querySelector('.department-payroll-toolbar')
  if (!toolbar) return null
  const month = selectedMonth()
  panel = document.createElement('section')
  panel.id = PANEL_ID
  panel.innerHTML = panelHtml(month)
  toolbar.insertAdjacentElement('afterend', panel)
  dateRoot = createRoot(panel.querySelector('[data-advance-date]'))
  renderAdvanceDate(month)

  panel.querySelector('[data-advance-toggle]').addEventListener('click', (event) => {
    const content = panel.querySelector('[data-advance-content]')
    content.hidden = !content.hidden
    event.currentTarget.textContent = content.hidden ? 'Hiện' : 'Ẩn'
    event.currentTarget.setAttribute('aria-expanded', String(!content.hidden))
  })
  panel.addEventListener('pointerdown', (event) => {
    if (event.target.closest('[data-advance-employee-option]')) event.preventDefault()
  })
  panel.querySelector('[data-advance-refresh]')?.addEventListener('click', () => scheduleRefresh(true))
  panel.querySelectorAll('[data-advance-period]').forEach(button => button.addEventListener('click', () => {
    const mode = button.dataset.advancePeriod
    const custom = panel.querySelector('[data-advance-filter-month]')
    custom.hidden = mode !== 'custom'
    ledgerFilterMonth = mode === 'previous' ? previousMonth() : mode === 'current' ? monthNow() : custom.value
    custom.value = ledgerFilterMonth
    panel.querySelectorAll('[data-advance-period]').forEach(item => item.classList.toggle('active', item === button))
    scheduleRefresh(true)
  }))
  panel.querySelector('[data-advance-filter-month]').addEventListener('change', event => {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(event.target.value)) return
    ledgerFilterMonth = event.target.value
    scheduleRefresh(true)
  })
  const employeeSearch = panel.querySelector('[data-advance-employee]')
  employeeSearch?.addEventListener('focus', () => {
    renderEmployeeSuggestions(panel, employeeSearch.value, true)
    employeeSearch.setAttribute('aria-expanded', 'true')
  })
  employeeSearch?.addEventListener('input', () => {
    employeeSearch.dataset.selectedUsername = ''
    renderEmployeeSuggestions(panel, employeeSearch.value)
    employeeSearch.setAttribute('aria-expanded', 'true')
  })
  employeeSearch?.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return
    panel.querySelector('[data-advance-employee-options]')?.setAttribute('hidden', '')
    employeeSearch.setAttribute('aria-expanded', 'false')
  })
  panel.querySelector('.advance-employee-field')?.addEventListener('focusout', (event) => {
    if (event.currentTarget.contains(event.relatedTarget)) return
    panel.querySelector('[data-advance-employee-options]')?.setAttribute('hidden', '')
    employeeSearch.setAttribute('aria-expanded', 'false')
  })
  panel.querySelector('[data-advance-amount]')?.addEventListener('input', (event) => {
    event.target.value = formatMoneyInput(event.target.value)
  })
  panel.querySelector('[data-advance-form]')?.addEventListener('submit', async (event) => {
    event.preventDefault()
    const employeeInput = panel.querySelector('[data-advance-employee]')
    const employee = resolveEmployee(employeeInput?.value, employeeInput?.dataset.selectedUsername)
    if (!employee) return showMessage('Vui lòng gõ và chọn đúng nhân viên trong danh sách.', 'error')
    const advanceDate = parseDisplayDate(panel.querySelector('[data-advance-date] input[type="text"]')?.value)
    const deductionMonth = panel.querySelector('[data-advance-deduction-month]')?.value
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(deductionMonth || '')) return showMessage('Vui lòng chọn tháng trừ lương hợp lệ.', 'error')
    const amount = Number(String(panel.querySelector('[data-advance-amount]')?.value || '').replace(/\D/g, ''))
    const note = panel.querySelector('[data-advance-note]')?.value || ''
    if (!advanceDate) return showMessage('Ngày ứng lương phải đúng định dạng dd-mm-yyyy.', 'error')
    if (!Number.isFinite(amount) || amount <= 0) return showMessage('Số tiền ứng phải lớn hơn 0.', 'error')
    const button = panel.querySelector('[data-advance-add]')
    button.disabled = true
    try {
      await apiRequest('/v2/department-payroll/advances', {
        method: 'POST',
        body: JSON.stringify({ employee_username: employee.employee_username, advance_date: advanceDate, deduction_month: deductionMonth, amount, note }),
      })
      if (employeeInput) {
        employeeInput.value = ''
        employeeInput.dataset.selectedUsername = ''
      }
      const amountInput = panel.querySelector('[data-advance-amount]')
      const noteInput = panel.querySelector('[data-advance-note]')
      if (amountInput) amountInput.value = ''
      if (noteInput) noteInput.value = ''
      showMessage('Đã thêm khoản ứng lương.', 'success')
      await refreshLedger(true)
      applyAdvancesToPayrollRows()
    } catch (error) {
      showMessage(error.message || 'Không thêm được khoản ứng lương.', 'error')
    } finally {
      button.disabled = false
    }
  })

  panel.addEventListener('click', async (event) => {
    const employeeOption = event.target.closest('[data-advance-employee-option]')
    if (employeeOption) {
      const employeeInput = panel.querySelector('[data-advance-employee]')
      const employee = resolveEmployee('', employeeOption.dataset.advanceEmployeeOption)
      if (employeeInput && employee) {
        employeeInput.value = employeeOptionLabel(employee)
        employeeInput.dataset.selectedUsername = clean(employee.employee_username)
        employeeInput.setAttribute('aria-expanded', 'false')
      }
      panel.querySelector('[data-advance-employee-options]')?.setAttribute('hidden', '')
      return
    }
    const button = event.target.closest('[data-advance-delete]')
    if (!button) return
    if (!window.confirm('Xóa khoản ứng lương này?')) return
    button.disabled = true
    try {
      await apiRequest(`/v2/department-payroll/advances/${encodeURIComponent(button.dataset.advanceDelete)}`, { method: 'DELETE' })
      showMessage('Đã xóa khoản ứng lương.', 'success')
      await refreshLedger(true)
      applyAdvancesToPayrollRows()
    } catch (error) {
      showMessage(error.message || 'Không xóa được khoản ứng lương.', 'error')
    } finally {
      button.disabled = false
    }
  })
  return panel
}

function showMessage(message, type = 'success') {
  const box = document.querySelector(`#${PANEL_ID} [data-advance-message]`)
  if (!box) return
  box.textContent = message
  box.className = `advance-ledger-message show ${type}`
  window.setTimeout(() => {
    if (box.textContent === message) box.className = 'advance-ledger-message'
  }, 5000)
}

function renderLedger() {
  const panel = ensurePanel()
  if (!panel) return
  const summary = currentPayload.summary || {}
  const setText = (selector, value) => { const node = panel.querySelector(selector); if (node) node.textContent = money(value) }
  setText('[data-advance-total]', summary.month_total)
  setText('[data-advance-pending]', summary.pending_total)
  setText('[data-advance-settled]', summary.settled_total)

  const body = panel.querySelector('[data-advance-tbody]')
  if (!body) return
  const items = currentPayload.items || []
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="8" class="advance-empty">Tháng này chưa có khoản ứng lương.</td></tr>'
    return
  }
  body.innerHTML = items.map((item, index) => {
    const settled = item.status === 'settled'
    const note = clean(item.note).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') || '—'
    const name = clean(item.employee_name).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const username = clean(item.employee_username).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const department = clean(item.department_label).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const deductionMonth = clean(item.deduction_month || item.payroll_month || String(item.advance_date || '').slice(0, 7))
    const deductionLabel = /^\d{4}-(0[1-9]|1[0-2])$/.test(deductionMonth) ? deductionMonth.split('-').reverse().join('-') : '—'
    return `<tr><td>${index + 1}</td><td><strong>${name}</strong><small>${username} · ${department}</small></td><td>${formatDate(item.advance_date)}</td><td>${deductionLabel}</td><td class="money">${money(item.amount)}</td><td>${note}</td><td><span class="advance-status ${settled ? 'settled' : 'pending'}">${settled ? 'Đã trừ lương' : 'Chờ trừ'}</span>${settled && item.payroll_month ? `<small>Tháng ${item.payroll_month.split('-').reverse().join('/')}</small>` : ''}</td><td>${settled ? '<small>Đã khóa</small>' : `<button type="button" class="danger-button compact" data-advance-delete="${item.id}">Xóa</button>`}</td></tr>`
  }).join('')
}

async function refreshLedger(force = false) {
  const month = ledgerMonth()
  const version = ++refreshVersion
  const payrollMonth = selectedMonth()
  if (!force && month === currentMonth && currentPayload.items?.length) {
    renderLedger()
    queueApply()
    return
  }
  const monthChanged = currentMonth !== month
  currentMonth = month
  const panel = ensurePanel()
  const deductionInput = panel?.querySelector('[data-advance-deduction-month]')
  if (monthChanged && deductionInput) deductionInput.value = month
  if (monthChanged) renderAdvanceDate(month)
  try {
    const [ledger, payroll] = await Promise.all([
      apiRequest(`/v2/department-payroll/advances?month=${encodeURIComponent(month)}`),
      month === payrollMonth ? Promise.resolve(null) : apiRequest(`/v2/department-payroll/advances?month=${encodeURIComponent(payrollMonth)}`),
    ])
    if (version !== refreshVersion) return
    currentPayload = ledger
    payrollSummary = (payroll || ledger).summary || {}
    renderLedger()
    queueApply()
  } catch (error) {
    showMessage(error.message || 'Không tải được bảng ứng lương.', 'error')
  }
}

function applyAdvancesToPayrollRows() {
  if (payrollSummary.month !== selectedMonth()) return
  window.dispatchEvent(new CustomEvent('vera-salary-advance-summary', {
    detail: { month: payrollSummary.month, byEmployee: payrollSummary.by_employee || {} },
  }))
}

function queueApply() {
  window.clearTimeout(applyTimer)
  applyTimer = window.setTimeout(applyAdvancesToPayrollRows, 90)
}

function scheduleRefresh(force = false) {
  window.clearTimeout(refreshTimer)
  refreshTimer = window.setTimeout(() => { void refreshLedger(force) }, 100)
}

function installCompleteSettlementHook() {
  if (window.__veraSalaryAdvanceFetchHookInstalled) return
  window.__veraSalaryAdvanceFetchHookInstalled = true
  const originalFetch = window.fetch.bind(window)
  window.fetch = async (input, init = {}) => {
    const response = await originalFetch(input, init)
    const url = typeof input === 'string' ? input : input?.url || ''
    const method = String(init?.method || (typeof input !== 'string' ? input?.method : '') || 'GET').toUpperCase()
    if (!response.ok || method !== 'POST' || !url.includes('/v2/department-payroll/combined/complete')) return response
    try {
      const result = await response.clone().json()
      const requestBody = typeof init.body === 'string' ? JSON.parse(init.body) : {}
      const employees = Array.from(new Set((requestBody.rows || []).map((row) => clean(row?.employee_username)).filter(Boolean)))
      const settleResponse = await originalFetch(`${API_BASE}/v2/department-payroll/advances/settle`, {
        method: 'POST',
        headers: init.headers,
        body: JSON.stringify({ month: requestBody.month, history_id: result.history_id || '', employees }),
      })
      if (!settleResponse.ok) {
        const payload = await settleResponse.json().catch(() => ({}))
        throw new Error(payload.detail || payload.message || `HTTP ${settleResponse.status}`)
      }
      window.dispatchEvent(new CustomEvent('vera-salary-advances-settled', { detail: { month: requestBody.month } }))
    } catch (error) {
      window.dispatchEvent(new CustomEvent('vera-salary-advances-settle-error', { detail: { message: error.message || 'Không cập nhật được trạng thái ứng lương.' } }))
    }
    return response
  }
}

export function startDepartmentSalaryAdvanceLedger() {
  if (window.__veraDepartmentSalaryAdvanceLedgerStarted) return
  window.__veraDepartmentSalaryAdvanceLedgerStarted = true
  ensureStyles()
  installCompleteSettlementHook()

  document.addEventListener('change', (event) => {
    if (event.target.matches('.department-payroll-toolbar input[type="month"]')) {
      currentPayload = { items: [], summary: {}, employee_catalog: currentPayload.employee_catalog || [] }
      scheduleRefresh(true)
    }
  }, true)

  window.addEventListener('vera-salary-advances-settled', () => scheduleRefresh(true))
  window.addEventListener('vera-salary-advances-settle-error', (event) => showMessage(`Bảng lương đã hoàn thành nhưng chưa cập nhật được trạng thái ứng lương: ${event.detail?.message || ''}`, 'error'))

  const observer = new MutationObserver((records) => {
    const existingPanel = document.getElementById(PANEL_ID)
    if (existingPanel && records.every((record) => existingPanel.contains(record.target))) return
    const panel = ensurePanel()
    if (!panel) return
    const month = ledgerMonth()
    if (month !== currentMonth || !currentPayload.summary?.month) scheduleRefresh(month !== currentMonth)
    queueApply()
  })
  observer.observe(document.body, { childList: true, subtree: true })
  scheduleRefresh(true)
}
