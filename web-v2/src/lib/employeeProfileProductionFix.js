import { veraApi } from './api'
import { refreshProfileReferenceData } from './profileReferenceRefresh'

const REQUIRED_LABELS = new Set([
  'Họ và tên đầy đủ',
  'Ngày sinh',
  'Giới tính',
  'Dân tộc',
  'Điện thoại',
  'Email',
  'Tỉnh/Thành phố',
  'Phường/Xã',
  'Địa chỉ cụ thể (Số nhà, tên đường...)',
  'Địa chỉ cụ thể',
  'Tên ngân hàng',
  'Số tài khoản ngân hàng',
  'Số Căn cước',
  'Số CCCD',
  'Ngày cấp',
  'Ngày cấp CCCD',
  'Nơi cấp',
  'Nơi cấp CCCD',
])

const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim()

function labelName(label) {
  return clean(label?.childNodes?.[0]?.textContent || label?.textContent)
}

function profileRoots() {
  const roots = Array.from(document.querySelectorAll('.profile-form'))
  document.querySelectorAll('.staff-form-panel').forEach((panel) => {
    const heading = clean(panel.querySelector('h2')?.textContent)
    if (heading.startsWith('SỬA HỒ SƠ ·')) roots.push(panel)
  })
  return roots
}

function ensureStyles() {
  if (document.getElementById('vera-profile-production-fix-style')) return
  const style = document.createElement('style')
  style.id = 'vera-profile-production-fix-style'
  style.textContent = `
    .vera-required-missing{padding:8px!important;border:2px solid #e2a218!important;border-radius:10px!important;background:#fff0b3!important;color:#6e4d00!important;box-shadow:0 0 0 3px rgba(226,162,24,.12)!important}
    .vera-required-missing input,.vera-required-missing select,.vera-required-missing textarea{border:2px solid #d99600!important;background:#fff9dc!important;box-shadow:0 0 0 2px rgba(217,150,0,.10)!important}
    .vera-required-missing::after{content:'Thiếu: ' attr(data-vera-missing-label);display:block;margin-top:3px;font-size:10px;font-weight:900;color:#985f00}
    .vera-national-wrap{display:grid;gap:6px}.vera-national-row{display:flex;gap:6px;align-items:center}.vera-national-row select{flex:1;min-width:0}
    .vera-national-refresh{min-height:36px;padding:0 9px;border:1px solid #b8c7c0;border-radius:8px;background:#fff;font-size:11px;font-weight:900;white-space:nowrap;cursor:pointer}
    .vera-national-refresh[disabled]{opacity:.55;cursor:wait}
    @media(max-width:700px){.vera-national-row{flex-direction:column;align-items:stretch}.vera-national-refresh{width:100%}}
  `
  document.head.appendChild(style)
}

function originalControl(label) {
  if (!label) return null
  const explicit = label.querySelector('[data-vera-national-source="1"]')
  if (explicit) return explicit
  return label.querySelector('input:not([type="file"]):not([type="password"]), select:not([data-vera-national-select="1"]), textarea')
}

function setReactValue(control, value) {
  if (!control) return
  const prototype = control instanceof HTMLSelectElement
    ? HTMLSelectElement.prototype
    : control instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set
  if (setter) setter.call(control, value)
  else control.value = value
  control.dispatchEvent(new Event('input', { bubbles: true }))
  control.dispatchEvent(new Event('change', { bubbles: true }))
}

function removeDistrictField() {
  profileRoots().forEach((root) => {
    root.querySelectorAll('label').forEach((label) => {
      if (labelName(label).startsWith('Quận/Huyện')) label.remove()
    })
  })
}

function markMissingFields() {
  profileRoots().forEach((root) => {
    root.querySelectorAll('label').forEach((label) => {
      const name = labelName(label)
      if (!REQUIRED_LABELS.has(name)) {
        label.classList.remove('vera-required-missing')
        delete label.dataset.veraMissingLabel
        return
      }
      const control = originalControl(label)
      if (!control || control.disabled) return
      const missing = !clean(control.value)
      label.classList.toggle('vera-required-missing', missing)
      if (missing) label.dataset.veraMissingLabel = name
      else delete label.dataset.veraMissingLabel
    })
  })
}

function optionValues(kind, items) {
  if (kind === 'province') return (items || []).map((item) => ({ value: item.name, text: item.name, code: item.code }))
  return (items || []).map((item) => ({ value: item, text: item }))
}

function renderSelect(select, source, kind, items) {
  const selected = clean(source?.value)
  const values = optionValues(kind, items)
  if (selected && !values.some((item) => item.value === selected)) values.unshift({ value: selected, text: selected })
  select.textContent = ''
  const empty = document.createElement('option')
  empty.value = ''
  empty.textContent = kind === 'province'
    ? '-- Chọn Tỉnh/Thành phố --'
    : kind === 'ward'
      ? '-- Chọn Phường/Xã --'
      : '-- Chọn ngân hàng --'
  select.appendChild(empty)
  values.forEach((item) => {
    const option = document.createElement('option')
    option.value = item.value
    option.textContent = item.text
    if (item.code !== undefined) option.dataset.code = String(item.code)
    select.appendChild(option)
  })
  select.value = selected
}

function findLabel(root, name) {
  return Array.from(root.querySelectorAll('label')).find((label) => labelName(label) === name) || null
}

async function loadWardsForRoot(root, catalogs, provinceName, refresh = false) {
  const wardLabel = findLabel(root, 'Phường/Xã')
  if (!wardLabel) return []
  const province = (catalogs.provinces || []).find((item) => item.name === provinceName)
  if (!province) return []
  const data = refresh
    ? await refreshProfileReferenceData(province.code)
    : await veraApi.profileReferenceData(province.code)
  return data.wards || []
}

function ensureRefreshButton(row, kind, handler) {
  let button = row.querySelector(`[data-vera-national-refresh="${kind}"]`)
  if (button) return button
  button = document.createElement('button')
  button.type = 'button'
  button.className = 'vera-national-refresh'
  button.dataset.veraNationalRefresh = kind
  button.textContent = '↻ Cập nhật danh mục'
  button.addEventListener('click', async () => {
    if (button.disabled) return
    button.disabled = true
    const previous = button.textContent
    button.textContent = 'Đang cập nhật…'
    try { await handler() }
    catch (error) { window.alert(`Không cập nhật được danh mục: ${error?.message || 'lỗi không xác định'}`) }
    finally { button.disabled = false; button.textContent = previous }
  })
  row.appendChild(button)
  return button
}

async function enhanceReferenceRoot(root, catalogs) {
  const fields = [
    ['Tỉnh/Thành phố', 'province', catalogs.provinces || []],
    ['Phường/Xã', 'ward', []],
    ['Tên ngân hàng', 'bank', catalogs.banks || []],
  ]

  const provinceLabel = findLabel(root, 'Tỉnh/Thành phố')
  const provinceSource = originalControl(provinceLabel)
  const currentProvince = clean(provinceSource?.value)
  let wardItems = []
  if (currentProvince) {
    try { wardItems = await loadWardsForRoot(root, catalogs, currentProvince, false) }
    catch { wardItems = [] }
  }
  fields[1][2] = wardItems

  for (const [name, kind, items] of fields) {
    const label = findLabel(root, name)
    if (!label) continue

    // ProfilePage already renders a native controlled dropdown. Keep it and only
    // ensure its data refresh control remains present.
    const nativeSelect = label.querySelector('select:not([data-vera-national-select="1"])')
    if (nativeSelect && !label.querySelector('input[data-vera-national-source="1"]')) continue

    let source = originalControl(label)
    if (!source) continue
    source.dataset.veraNationalSource = '1'

    let wrap = label.querySelector('.vera-national-wrap')
    let select = label.querySelector('select[data-vera-national-select="1"]')
    if (!wrap) {
      wrap = document.createElement('div')
      wrap.className = 'vera-national-wrap'
      const row = document.createElement('div')
      row.className = 'vera-national-row'
      select = document.createElement('select')
      select.dataset.veraNationalSelect = '1'
      select.setAttribute('aria-label', name)
      row.appendChild(select)
      wrap.appendChild(row)
      source.style.display = 'none'
      source.insertAdjacentElement('afterend', wrap)
    }
    const row = wrap.querySelector('.vera-national-row')
    if (!select) select = row?.querySelector('select')
    if (!select || !row) continue

    renderSelect(select, source, kind, items)
    if (!select.dataset.veraNationalBound) {
      select.dataset.veraNationalBound = '1'
      select.addEventListener('change', async () => {
        setReactValue(source, select.value)
        if (kind === 'province') {
          const wardLabel = findLabel(root, 'Phường/Xã')
          const wardSource = originalControl(wardLabel)
          const wardSelect = wardLabel?.querySelector('select[data-vera-national-select="1"], .vera-reference-row select')
          if (wardSource) setReactValue(wardSource, '')
          if (wardSelect) {
            try {
              const latest = await veraApi.profileReferenceData()
              const wards = await loadWardsForRoot(root, latest, select.value, false)
              renderSelect(wardSelect, wardSource, 'ward', wards)
            } catch {
              renderSelect(wardSelect, wardSource, 'ward', [])
            }
          }
        }
        markMissingFields()
      })
    }

    ensureRefreshButton(row, kind, async () => {
      const latest = await refreshProfileReferenceData()
      if (kind === 'province') renderSelect(select, source, kind, latest.provinces || [])
      if (kind === 'bank') renderSelect(select, source, kind, latest.banks || [])
      if (kind === 'ward') {
        const currentProvinceName = clean(originalControl(findLabel(root, 'Tỉnh/Thành phố'))?.value)
        const wards = currentProvinceName ? await loadWardsForRoot(root, latest, currentProvinceName, true) : []
        renderSelect(select, source, kind, wards)
      }
      markMissingFields()
    })
  }
}

let catalogsPromise = null
function rootCatalogs() {
  if (!catalogsPromise) catalogsPromise = veraApi.profileReferenceData().catch((error) => {
    catalogsPromise = null
    throw error
  })
  return catalogsPromise
}

async function ensureReferenceDropdowns() {
  const roots = profileRoots()
  if (!roots.length) return
  let catalogs
  try { catalogs = await rootCatalogs() } catch { return }
  for (const root of roots) await enhanceReferenceRoot(root, catalogs)
}

const cccdLoadAttempts = new WeakMap()
function ensureCccdVisible() {
  document.querySelectorAll('.employee-id-side').forEach((card) => {
    const title = clean(card.querySelector('.employee-id-side-head strong')?.textContent)
    if (!/^Mặt trước$|^Mặt sau$/i.test(title)) return
    const savedText = clean(card.querySelector('.employee-id-side-head span')?.textContent)
    if (!savedText.startsWith('Đã lưu')) return
    if (card.querySelector('.employee-id-preview img')) return
    const viewButton = Array.from(card.querySelectorAll('.employee-id-actions button'))
      .find((button) => /^Xem$/i.test(clean(button.textContent)))
    if (!viewButton || viewButton.disabled) return
    const now = Date.now()
    const previous = cccdLoadAttempts.get(card) || 0
    if (now - previous < 1800) return
    cccdLoadAttempts.set(card, now)
    viewButton.click()
  })
}

let scheduled = false
async function refreshProductionProfileUi() {
  removeDistrictField()
  markMissingFields()
  ensureCccdVisible()
  await ensureReferenceDropdowns()
  removeDistrictField()
  markMissingFields()
  ensureCccdVisible()
}

export function startEmployeeProfileProductionFix() {
  if (window.__veraEmployeeProfileProductionFixStarted) return
  window.__veraEmployeeProfileProductionFixStarted = true
  ensureStyles()

  const schedule = () => {
    if (scheduled) return
    scheduled = true
    window.setTimeout(() => {
      scheduled = false
      void refreshProductionProfileUi()
    }, 50)
  }

  document.addEventListener('input', schedule, true)
  document.addEventListener('change', schedule, true)
  document.addEventListener('click', schedule, true)
  const observer = new MutationObserver(schedule)
  observer.observe(document.body, { childList: true, subtree: true })
  schedule()
}
