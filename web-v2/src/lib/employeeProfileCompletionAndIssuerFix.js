import { veraApi } from './api'
import { refreshProfileReferenceData } from './profileReferenceRefresh'

const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim()
const DEPRECATED_REQUIRED_FIELDS = new Set(['Quận/Huyện'])
const CENTRAL_ISSUERS = [
  'Bộ Công an',
  'Cục Cảnh sát quản lý hành chính về trật tự xã hội, Bộ Công an',
  'Trung tâm dữ liệu quốc gia về dân cư, Cục Cảnh sát quản lý hành chính về trật tự xã hội, Bộ Công an',
  'Cục Cảnh sát đăng ký, quản lý cư trú và dữ liệu quốc gia về dân cư, Bộ Công an',
]
const CENTRAL_CITIES = new Set([
  'Hà Nội', 'Hải Phòng', 'Huế', 'Đà Nẵng', 'Cần Thơ', 'Hồ Chí Minh',
])

function normalizeProvinceName(value) {
  return clean(value).replace(/^Tỉnh\s+/i, '').replace(/^Thành phố\s+/i, '')
}

function profileRoots() {
  const roots = Array.from(document.querySelectorAll('.profile-form'))
  document.querySelectorAll('.staff-form-panel').forEach((panel) => {
    const title = clean(panel.querySelector('h2')?.textContent)
    if (title.startsWith('SỬA HỒ SƠ ·')) roots.push(panel)
  })
  return roots
}

function labelName(label) {
  return clean(label?.childNodes?.[0]?.textContent || label?.textContent)
}

function findLabel(root, wanted) {
  return Array.from(root.querySelectorAll('label')).find((label) => labelName(label).startsWith(wanted)) || null
}

function visibleOrSourceControl(label) {
  if (!label) return null
  return label.querySelector('[data-vera-issuer-source="1"]')
    || label.querySelector('[data-vera-national-source="1"]')
    || label.querySelector('input:not([type="file"]):not([type="password"]), select, textarea')
}

function currentFieldValue(root, labelText) {
  const label = findLabel(root, labelText)
  if (!label) return ''
  const source = label.querySelector('[data-vera-national-source="1"]')
  const select = label.querySelector('select[data-vera-national-select="1"], .vera-reference-row select')
  return clean(source?.value || select?.value || visibleOrSourceControl(label)?.value)
}

function setReactValue(control, value) {
  if (!control) return
  const proto = control instanceof HTMLSelectElement
    ? HTMLSelectElement.prototype
    : control instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set
  if (setter) setter.call(control, value)
  else control.value = value
  control.dispatchEvent(new Event('input', { bubbles: true }))
  control.dispatchEvent(new Event('change', { bubbles: true }))
}

function parseMissingTitle(item) {
  const title = clean(item?.getAttribute('title'))
  if (!title.startsWith('Hồ sơ còn thiếu:')) return []
  const seen = new Set()
  return title
    .slice('Hồ sơ còn thiếu:'.length)
    .split(',')
    .map(clean)
    .filter((field) => field && !DEPRECATED_REQUIRED_FIELDS.has(field))
    .filter((field) => {
      if (seen.has(field)) return false
      seen.add(field)
      return true
    })
}

function reconcileIncompleteSummary() {
  const panel = document.querySelector('.staff-list-panel')
  const summary = panel?.querySelector('.panel-title-row p')
  if (!summary) return

  const rows = Array.from(panel.querySelectorAll('.staff-table tbody tr')).filter((row) => row.offsetParent !== null)
  const mobileCards = Array.from(panel.querySelectorAll('.staff-mobile-card')).filter((card) => card.offsetParent !== null)
  const items = rows.length ? rows : mobileCards
  const incomplete = items.filter((item) => {
    const badge = item.querySelector('.staff-incomplete-badge')
    return badge && !badge.hidden && clean(badge.textContent).startsWith('Thiếu:')
  }).length

  const base = clean(summary.textContent).replace(/\s*·\s*\d+\s+hồ sơ chưa đầy đủ \(dòng vàng\)\.?$/i, '')
  summary.textContent = incomplete
    ? `${base} · ${incomplete} hồ sơ chưa đầy đủ (dòng vàng).`
    : base
}

function reconcileMissingBadges() {
  document.querySelectorAll('.staff-table tbody tr, .staff-mobile-card').forEach((item) => {
    const badge = item.querySelector('.staff-incomplete-badge')
    if (!badge) return
    const missing = parseMissingTitle(item)
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
  })
  reconcileIncompleteSummary()
}

function policeAuthorityForProvince(name) {
  const raw = clean(name)
  const province = normalizeProvinceName(raw)
  if (!province) return ''
  const isCity = /^Thành phố\s+/i.test(raw) || CENTRAL_CITIES.has(province)
  return isCity ? `Công an thành phố ${province}` : `Công an tỉnh ${province}`
}

function localPoliceAuthority(wardName) {
  const ward = clean(wardName)
  return ward ? `Công an ${ward}` : ''
}

function issuerValues(catalogs, wards, currentValue = '') {
  const values = [
    ...CENTRAL_ISSUERS,
    ...(catalogs?.provinces || []).map((item) => policeAuthorityForProvince(item?.name)),
    ...(wards || []).map(localPoliceAuthority),
  ].filter(Boolean)
  const unique = Array.from(new Set(values))
  if (currentValue && !unique.includes(currentValue)) unique.unshift(currentValue)
  return unique
}

async function wardsForRoot(root, catalogs, refresh = false) {
  const provinceName = normalizeProvinceName(currentFieldValue(root, 'Tỉnh/Thành phố'))
  if (!provinceName) return []
  const province = (catalogs?.provinces || []).find((item) => normalizeProvinceName(item?.name) === provinceName)
  if (!province?.code) return []
  const data = refresh
    ? await refreshProfileReferenceData(province.code)
    : await veraApi.profileReferenceData(province.code)
  return data?.wards || []
}

function renderIssuerSelect(select, source, values) {
  const current = clean(source?.value)
  select.textContent = ''
  const empty = document.createElement('option')
  empty.value = ''
  empty.textContent = '-- Chọn Nơi cấp --'
  select.appendChild(empty)
  values.forEach((value) => {
    const option = document.createElement('option')
    option.value = value
    option.textContent = value
    select.appendChild(option)
  })
  select.value = current
}

function ensureStyles() {
  if (document.getElementById('vera-profile-completion-issuer-style')) return
  const style = document.createElement('style')
  style.id = 'vera-profile-completion-issuer-style'
  style.textContent = `
    .vera-issuer-wrap{display:grid;gap:6px}
    .vera-issuer-row{display:flex;gap:6px;align-items:center}
    .vera-issuer-row select{flex:1;min-width:0}
    .vera-issuer-refresh{min-height:36px;padding:0 9px;border:1px solid #b8c7c0;border-radius:8px;background:#fff;font-size:11px;font-weight:900;white-space:nowrap;cursor:pointer}
    .vera-issuer-refresh[disabled]{opacity:.55;cursor:wait}
    @media(max-width:700px){.vera-issuer-row{flex-direction:column;align-items:stretch}.vera-issuer-refresh{width:100%}}
  `
  document.head.appendChild(style)
}

async function enhanceIssuerRoot(root, force = false) {
  const label = findLabel(root, 'Nơi cấp')
  if (!label) return

  let source = label.querySelector('[data-vera-issuer-source="1"]')
  if (!source) {
    source = label.querySelector('input:not([type="file"]):not([type="password"]), textarea')
    if (!source) return
    source.dataset.veraIssuerSource = '1'
    source.style.display = 'none'
  }

  let wrap = label.querySelector('.vera-issuer-wrap')
  if (!wrap) {
    wrap = document.createElement('div')
    wrap.className = 'vera-issuer-wrap'
    const row = document.createElement('div')
    row.className = 'vera-issuer-row'
    const select = document.createElement('select')
    select.dataset.veraIssuerSelect = '1'
    select.setAttribute('aria-label', 'Nơi cấp CCCD')
    row.appendChild(select)
    wrap.appendChild(row)
    source.insertAdjacentElement('afterend', wrap)

    select.addEventListener('change', () => {
      setReactValue(source, select.value)
    })

    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'vera-issuer-refresh'
    button.textContent = '↻ Cập nhật nơi cấp'
    button.addEventListener('click', async () => {
      if (button.disabled) return
      button.disabled = true
      const original = button.textContent
      button.textContent = 'Đang cập nhật…'
      try {
        await enhanceIssuerRoot(root, true)
      } catch (error) {
        window.alert(`Không cập nhật được danh mục Nơi cấp: ${error?.message || 'lỗi không xác định'}`)
      } finally {
        button.disabled = false
        button.textContent = original
      }
    })
    row.appendChild(button)
  }

  const select = wrap.querySelector('select[data-vera-issuer-select="1"]')
  if (!select) return
  const catalogs = force ? await refreshProfileReferenceData() : await veraApi.profileReferenceData()
  let wards = []
  try { wards = await wardsForRoot(root, catalogs, force) } catch { wards = [] }
  renderIssuerSelect(select, source, issuerValues(catalogs, wards, clean(source.value)))
}

let scheduled = false
async function refreshUi() {
  reconcileMissingBadges()
  for (const root of profileRoots()) {
    try { await enhanceIssuerRoot(root, false) } catch { /* Keep manual input usable if catalog fetch fails. */ }
  }
  reconcileMissingBadges()
}

export function startEmployeeProfileCompletionAndIssuerFix() {
  if (window.__veraEmployeeProfileCompletionAndIssuerFixStarted) return
  window.__veraEmployeeProfileCompletionAndIssuerFixStarted = true
  ensureStyles()

  const schedule = () => {
    if (scheduled) return
    scheduled = true
    window.setTimeout(() => {
      scheduled = false
      void refreshUi()
    }, 80)
  }

  const observer = new MutationObserver(schedule)
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['title', 'class', 'value'],
  })
  document.addEventListener('input', schedule, true)
  document.addEventListener('change', schedule, true)
  document.addEventListener('click', schedule, true)
  window.setInterval(reconcileMissingBadges, 900)
  schedule()
}
