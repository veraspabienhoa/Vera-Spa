import { getCurrentSession } from './supabase'

const API_BASE = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const PANEL_ID = 'vera-department-salary-advance-ledger'
const STYLE_ID = 'vera-department-salary-advance-ledger-style'

let currentPayload = { items: [], summary: {}, employee_catalog: [] }
let currentMonth = ''
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
  const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return match ? `${match[3]}/${match[2]}/${match[1]}` : clean(value) || '—'
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
    #${PANEL_ID}{display:grid;gap:12px;margin:14px 0;padding:16px;border:1px solid #e4d6b7;border-radius:14px;background:#fffaf0}
    #${PANEL_ID} .advance-ledger-title{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap}
    #${PANEL_ID} h3{margin:0;color:#72551c;font-size:18px}#${PANEL_ID} p{margin:4px 0 0;color:#746b5b;font-size:12px}
    #${PANEL_ID} .advance-ledger-summary{display:flex;gap:8px;flex-wrap:wrap}#${PANEL_ID} .advance-ledger-summary span{display:grid;gap:2px;min-width:145px;padding:9px 12px;border:1px solid #eadfc8;border-radius:10px;background:#fff;color:#746b5b;font-size:11px;font-weight:700}#${PANEL_ID} .advance-ledger-summary strong{font-size:16px;color:#193d31}
    #${PANEL_ID} .advance-ledger-form{display:grid;grid-template-columns:minmax(220px,1.4fr) 160px 180px minmax(220px,1.5fr) auto;gap:8px;align-items:end}
    #${PANEL_ID} .advance-ledger-form label{display:grid;gap:5px;font-size:11px;font-weight:800;color:#4d5f56}#${PANEL_ID} .advance-ledger-form input{width:100%;min-height:38px;padding:8px 10px;border:1px solid #cfdad4;border-radius:9px;background:#fff;color:#1f342b;font:inherit}
    #${PANEL_ID} .advance-ledger-form button{min-height:38px}
    #${PANEL_ID} .advance-ledger-table-wrap{max-width:100%;overflow:auto;border:1px solid #eadfc8;border-radius:10px;background:#fff}
    #${PANEL_ID} table{width:100%;min-width:900px;border-collapse:collapse}#${PANEL_ID} th,#${PANEL_ID} td{padding:8px 9px;border-bottom:1px solid #eee7d8;text-align:left;vertical-align:middle;font-size:12px}#${PANEL_ID} th{position:sticky;top:0;background:#f6f1e7;color:#5a5142;font-size:10px;text-transform:uppercase;letter-spacing:.03em}#${PANEL_ID} td.money{text-align:right;font-weight:900;color:#193d31}#${PANEL_ID} td small{display:block;color:#7b857f;margin-top:2px}
    #${PANEL_ID} .advance-status{display:inline-flex;padding:4px 7px;border-radius:999px;font-size:10px;font-weight:900;white-space:nowrap}.advance-status.pending{background:#fff0c2;color:#815b00}.advance-status.settled{background:#dcf2e7;color:#216346}
    #${PANEL_ID} .advance-ledger-message{display:none;padding:8px 10px;border-radius:9px;font-size:12px;font-weight:700}#${PANEL_ID} .advance-ledger-message.show{display:block}#${PANEL_ID} .advance-ledger-message.error{background:#fff0ef;color:#a13831}#${PANEL_ID} .advance-ledger-message.success{background:#eaf6ef;color:#246246}
    #${PANEL_ID} .advance-empty{padding:18px;text-align:center;color:#7b857f;font-size:12px}
    .department-payroll-panel .salary-advance-panel{display:none!important}
    @media(max-width:950px){#${PANEL_ID} .advance-ledger-form{grid-template-columns:1fr 1fr}#${PANEL_ID} .advance-ledger-form label:first-child,#${PANEL_ID} .advance-ledger-form label:nth-child(4){grid-column:1/-1}#${PANEL_ID} .advance-ledger-form button{grid-column:1/-1}}
    @media(max-width:620px){#${PANEL_ID} .advance-ledger-form{grid-template-columns:1fr}#${PANEL_ID} .advance-ledger-form>*{grid-column:1!important}#${PANEL_ID} .advance-ledger-summary span{flex:1;min-width:120px}}
  `
  document.head.appendChild(style)
}

function employeeOptionLabel(item) {
  return `${clean(item.employee_name)} · ${clean(item.department_label)} · ${clean(item.employee_username)}`
}

function resolveEmployee(value) {
  const needle = clean(value)
  return (currentPayload.employee_catalog || []).find((item) => employeeOptionLabel(item) === needle)
    || (currentPayload.employee_catalog || []).find((item) => clean(item.employee_username) === needle)
}

function panelHtml(month) {
  return `
    <div class="advance-ledger-title">
      <div><h3>💵 NHÂN VIÊN ỨNG LƯƠNG</h3><p>Mỗi lần ứng là một giao dịch riêng. Khi hoàn thành bảng lương, các khoản đang chờ sẽ tự chuyển sang Đã trừ lương.</p></div>
      <button type="button" class="secondary-button" data-advance-refresh>↻ Làm mới</button>
    </div>
    <div class="advance-ledger-summary">
      <span>Tổng ứng tháng<strong data-advance-total>0đ</strong></span>
      <span>Chờ trừ vào lương<strong data-advance-pending>0đ</strong></span>
      <span>Đã trừ vào lương<strong data-advance-settled>0đ</strong></span>
    </div>
    <form class="advance-ledger-form" data-advance-form>
      <label>Tên nhân viên<input type="text" list="vera-salary-advance-employees" autocomplete="off" placeholder="Gõ tên nhân viên…" data-advance-employee required><datalist id="vera-salary-advance-employees"></datalist></label>
      <label>Ngày<input type="date" value="${defaultAdvanceDate(month)}" data-advance-date required></label>
      <label>Số tiền<input type="number" min="1" step="1000" inputmode="numeric" placeholder="0" data-advance-amount required></label>
      <label>Ghi chú<input type="text" maxlength="1000" placeholder="Nội dung ứng lương…" data-advance-note></label>
      <button type="submit" class="primary-button" data-advance-add>+ Thêm khoản ứng</button>
    </form>
    <div class="advance-ledger-message" data-advance-message></div>
    <div class="advance-ledger-table-wrap"><table><thead><tr><th>TT</th><th>Tên nhân viên</th><th>Ngày</th><th>Số tiền</th><th>Ghi chú</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody data-advance-tbody></tbody></table></div>
  `
}

function ensurePanel() {
  const payrollPage = document.querySelector('.department-payroll-page:not(.department-payroll-config-page) .department-payroll-panel')
  if (!payrollPage) return null
  let panel = document.getElementById(PANEL_ID)
  if (panel && panel.closest('.department-payroll-panel') === payrollPage) return panel
  panel?.remove()
  const toolbar = payrollPage.querySelector('.department-payroll-toolbar')
  if (!toolbar) return null
  const month = selectedMonth()
  panel = document.createElement('section')
  panel.id = PANEL_ID
  panel.innerHTML = panelHtml(month)
  toolbar.insertAdjacentElement('afterend', panel)

  panel.querySelector('[data-advance-refresh]')?.addEventListener('click', () => scheduleRefresh(true))
  panel.querySelector('[data-advance-form]')?.addEventListener('submit', async (event) => {
    event.preventDefault()
    const employeeInput = panel.querySelector('[data-advance-employee]')
    const employee = resolveEmployee(employeeInput?.value)
    if (!employee) return showMessage('Vui lòng gõ và chọn đúng nhân viên trong danh sách.', 'error')
    const advanceDate = panel.querySelector('[data-advance-date]')?.value
    const amount = Number(panel.querySelector('[data-advance-amount]')?.value || 0)
    const note = panel.querySelector('[data-advance-note]')?.value || ''
    if (!advanceDate || amount <= 0) return showMessage('Vui lòng nhập ngày và số tiền ứng lớn hơn 0.', 'error')
    const button = panel.querySelector('[data-advance-add]')
    button.disabled = true
    try {
      await apiRequest('/v2/department-payroll/advances', {
        method: 'POST',
        body: JSON.stringify({ employee_username: employee.employee_username, advance_date: advanceDate, amount, note }),
      })
      if (employeeInput) employeeInput.value = ''
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

  const list = panel.querySelector('#vera-salary-advance-employees')
  if (list) list.innerHTML = (currentPayload.employee_catalog || []).map((item) => `<option value="${employeeOptionLabel(item).replace(/&/g, '&amp;').replace(/"/g, '&quot;')}"></option>`).join('')

  const body = panel.querySelector('[data-advance-tbody]')
  if (!body) return
  const items = currentPayload.items || []
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="7" class="advance-empty">Tháng này chưa có khoản ứng lương.</td></tr>'
    return
  }
  body.innerHTML = items.map((item, index) => {
    const settled = item.status === 'settled'
    const note = clean(item.note).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') || '—'
    const name = clean(item.employee_name).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const username = clean(item.employee_username).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const department = clean(item.department_label).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    return `<tr><td>${index + 1}</td><td><strong>${name}</strong><small>${username} · ${department}</small></td><td>${formatDate(item.advance_date)}</td><td class="money">${money(item.amount)}</td><td>${note}</td><td><span class="advance-status ${settled ? 'settled' : 'pending'}">${settled ? 'Đã trừ lương' : 'Chờ trừ'}</span>${settled && item.payroll_month ? `<small>Tháng ${item.payroll_month.split('-').reverse().join('/')}</small>` : ''}</td><td>${settled ? '<small>Đã khóa</small>' : `<button type="button" class="danger-button compact" data-advance-delete="${item.id}">Xóa</button>`}</td></tr>`
  }).join('')
}

async function refreshLedger(force = false) {
  const month = selectedMonth()
  if (!force && month === currentMonth && currentPayload.items?.length) {
    renderLedger()
    queueApply()
    return
  }
  currentMonth = month
  const panel = ensurePanel()
  const dateInput = panel?.querySelector('[data-advance-date]')
  if (dateInput && !String(dateInput.value || '').startsWith(`${month}-`)) dateInput.value = defaultAdvanceDate(month)
  try {
    currentPayload = await apiRequest(`/v2/department-payroll/advances?month=${encodeURIComponent(month)}`)
    renderLedger()
    queueApply()
  } catch (error) {
    showMessage(error.message || 'Không tải được bảng ứng lương.', 'error')
  }
}

function payrollRowsAndInputs() {
  const panel = document.querySelector('.department-payroll-panel')
  const grid = panel?.querySelector('.salary-advance-grid')
  const rows = Array.from(panel?.querySelectorAll('.department-payroll-table tbody tr') || [])
  const inputs = Array.from(grid?.querySelectorAll('label input[type="number"]') || [])
  return { rows, inputs }
}

function usernameFromPayrollRow(row) {
  const text = clean(row?.querySelector('td:nth-child(3) small')?.textContent)
  return clean(text.split('·')[0])
}

function setReactInputValue(input, value) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  if (setter) setter.call(input, String(value))
  else input.value = String(value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

function applyAdvancesToPayrollRows() {
  const { rows, inputs } = payrollRowsAndInputs()
  if (!rows.length || !inputs.length) return
  const byEmployee = currentPayload.summary?.by_employee || {}
  rows.forEach((row, index) => {
    const input = inputs[index]
    if (!input) return
    const username = usernameFromPayrollRow(row)
    const amount = Number(byEmployee?.[username]?.payroll_total || 0)
    if (Number(input.value || 0) !== amount) setReactInputValue(input, amount)
  })
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
      currentMonth = event.target.value
      scheduleRefresh(true)
    }
  }, true)

  window.addEventListener('vera-salary-advances-settled', () => scheduleRefresh(true))
  window.addEventListener('vera-salary-advances-settle-error', (event) => showMessage(`Bảng lương đã hoàn thành nhưng chưa cập nhật được trạng thái ứng lương: ${event.detail?.message || ''}`, 'error'))

  const observer = new MutationObserver(() => {
    const panel = ensurePanel()
    if (!panel) return
    const month = selectedMonth()
    if (month !== currentMonth || !currentPayload.summary?.month) scheduleRefresh(month !== currentMonth)
    queueApply()
  })
  observer.observe(document.body, { childList: true, subtree: true })
  scheduleRefresh(true)
}
