import { veraApi } from './api'

const REQUIRED_FIELDS = [
  ['full_name', 'Họ và tên đầy đủ'],
  ['birth_date', 'Ngày sinh'],
  ['gender', 'Giới tính'],
  ['ethnicity', 'Dân tộc'],
  ['phone', 'Điện thoại'],
  ['email', 'Email'],
  ['province', 'Tỉnh/Thành phố'],
  ['ward', 'Phường/Xã'],
  ['address_detail', 'Địa chỉ cụ thể'],
  ['bank_account', 'Số tài khoản ngân hàng'],
  ['bank_name', 'Tên ngân hàng'],
  ['cccd_number', 'Số CCCD'],
  ['cccd_issue_date', 'Ngày cấp CCCD'],
  ['cccd_issue_place', 'Nơi cấp CCCD'],
]

const clean = (value) => String(value ?? '').replace(/\s+/g, ' ').trim()

function missingFields(employee) {
  return REQUIRED_FIELDS
    .filter(([field]) => !clean(employee?.[field]))
    .map(([, label]) => label)
}

function usernameForItem(item) {
  if (item.matches('.staff-table tbody tr')) {
    return clean(item.querySelector('td:nth-child(2) strong')?.textContent)
  }
  return clean(item.querySelector('.staff-mobile-head strong')?.textContent)
}

function applyItemState(item, employee) {
  const badge = item.querySelector('.staff-incomplete-badge')
  if (!badge || !employee) return

  const missing = missingFields(employee)
  if (!missing.length) {
    badge.hidden = true
    badge.textContent = ''
    badge.removeAttribute('title')
    item.classList.remove('staff-incomplete-row', 'incomplete')
    item.removeAttribute('title')
    return
  }

  const text = `Thiếu: ${missing.join(', ')}`
  badge.hidden = false
  badge.textContent = text
  badge.title = text
  item.setAttribute('title', `Hồ sơ còn thiếu: ${missing.join(', ')}`)
  if (item.matches('tr')) item.classList.add('staff-incomplete-row')
  else item.classList.add('incomplete')
}

function updateSummary(items) {
  const panel = document.querySelector('.staff-list-panel')
  const summary = panel?.querySelector('.panel-title-row p')
  if (!summary) return

  const incomplete = items.filter((item) => {
    const badge = item.querySelector('.staff-incomplete-badge')
    return badge && !badge.hidden && clean(badge.textContent).startsWith('Thiếu:')
  }).length

  const base = clean(summary.textContent)
    .replace(/\s*·\s*\d+\s+hồ sơ chưa đầy đủ \(dòng vàng\)\.?$/i, '')

  summary.textContent = incomplete
    ? `${base} · ${incomplete} hồ sơ chưa đầy đủ (dòng vàng).`
    : base
}

let scheduled = false
let running = false
let rerun = false
let lastSnapshotAt = 0
let staffByUsername = new Map()

async function loadStaffSnapshot(force = false) {
  const now = Date.now()
  if (!force && staffByUsername.size && now - lastSnapshotAt < 1500) return staffByUsername
  const payload = await veraApi.staff()
  staffByUsername = new Map((payload?.employees || []).map((employee) => [clean(employee.username), employee]))
  lastSnapshotAt = Date.now()
  return staffByUsername
}

async function reconcile(force = false) {
  if (running) {
    rerun = true
    return
  }
  running = true
  try {
    const staff = await loadStaffSnapshot(force)
    const desktop = Array.from(document.querySelectorAll('.staff-table tbody tr')).filter((item) => item.offsetParent !== null)
    const mobile = Array.from(document.querySelectorAll('.staff-mobile-card')).filter((item) => item.offsetParent !== null)
    const visibleItems = desktop.length ? desktop : mobile

    document.querySelectorAll('.staff-table tbody tr, .staff-mobile-card').forEach((item) => {
      const username = usernameForItem(item)
      if (!username) return
      applyItemState(item, staff.get(username))
    })
    updateSummary(visibleItems)
  } catch {
    // Keep the existing UI usable if the staff endpoint is temporarily unavailable.
  } finally {
    running = false
    if (rerun) {
      rerun = false
      void reconcile(false)
    }
  }
}

export function startEmployeeMissingProfileFix() {
  if (window.__veraEmployeeMissingProfileFixStarted) return
  window.__veraEmployeeMissingProfileFixStarted = true

  const schedule = (force = false) => {
    if (scheduled) return
    scheduled = true
    window.setTimeout(() => {
      scheduled = false
      void reconcile(force)
    }, 120)
  }

  const observer = new MutationObserver(() => schedule(false))
  observer.observe(document.body, { childList: true, subtree: true })

  document.addEventListener('click', (event) => {
    const text = clean(event.target?.closest?.('button')?.textContent)
    schedule(/Làm mới|Lưu hồ sơ|Sửa|Hồ sơ/i.test(text))
  }, true)
  document.addEventListener('input', () => schedule(false), true)
  document.addEventListener('change', () => schedule(false), true)

  window.setInterval(() => void reconcile(true), 5000)
  schedule(true)
}
