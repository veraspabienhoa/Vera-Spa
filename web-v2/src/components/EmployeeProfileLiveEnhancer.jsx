import { useEffect } from 'react'
import { getCurrentSession } from '../lib/supabase'

const API_BASE = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const REQUIRED_LABELS = new Set([
  'Họ và tên đầy đủ', 'Ngày sinh', 'Giới tính', 'Dân tộc', 'Điện thoại', 'Email',
  'Tỉnh/Thành phố', 'Phường/Xã', 'Địa chỉ cụ thể (Số nhà, tên đường...)', 'Địa chỉ cụ thể',
  'Tên ngân hàng', 'Số tài khoản ngân hàng', 'Số Căn cước', 'Số CCCD', 'Ngày cấp',
  'Ngày cấp CCCD', 'Nơi cấp', 'Nơi cấp CCCD',
])

async function referenceData(provinceCode = '', refresh = false) {
  if (!API_BASE) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const params = new URLSearchParams()
  if (provinceCode !== '' && provinceCode !== null && provinceCode !== undefined) params.set('province_code', provinceCode)
  if (refresh) params.set('refresh', 'true')
  const headers = new Headers({ Accept: 'application/json', 'Cache-Control': 'no-cache' })
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const response = await fetch(`${API_BASE}/v2/profile/reference-data${params.toString() ? `?${params}` : ''}`, { headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || payload?.message || 'Không cập nhật được danh mục.')
  return payload
}

function labelText(label) {
  return String(label?.childNodes?.[0]?.textContent || label?.textContent || '').trim().replace(/\s+/g, ' ')
}

function setReactInputValue(input, value) {
  if (!input) return
  const proto = input instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set
  if (setter) setter.call(input, value)
  else input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

function ensureStyle() {
  if (document.getElementById('vera-profile-live-enhancer-style')) return
  const style = document.createElement('style')
  style.id = 'vera-profile-live-enhancer-style'
  style.textContent = `
    label.vera-profile-missing{padding:8px;border:2px solid #e0a400!important;border-radius:10px;background:#fff4bf!important;color:#6b4b00!important}
    label.vera-profile-missing::after{content:'Còn thiếu thông tin';font-size:10px;font-weight:900;color:#a05a00;margin-top:2px}
    .vera-reference-wrap{display:grid;gap:6px}.vera-reference-row{display:flex;gap:6px;align-items:center}.vera-reference-row select{flex:1;min-width:0}
    .vera-reference-refresh{white-space:nowrap;min-height:36px;padding:0 9px;border:1px solid #b8c7c0;border-radius:8px;background:#fff;font-size:11px;font-weight:900;cursor:pointer}
    .vera-reference-refresh[disabled]{opacity:.55;cursor:wait}
    .employee-id-preview[data-vera-clickable='1']{cursor:zoom-in;outline:1px dashed transparent;transition:.15s ease}.employee-id-preview[data-vera-clickable='1']:hover{outline-color:#9bb4aa}
    .vera-cccd-viewer{position:fixed;inset:0;z-index:12000;background:rgba(5,15,12,.86);display:flex;align-items:center;justify-content:center;padding:16px}
    .vera-cccd-viewer-card{width:min(1100px,100%);max-height:96vh;overflow:auto;background:#fff;border-radius:18px;padding:14px;box-shadow:0 24px 70px rgba(0,0,0,.45)}
    .vera-cccd-viewer-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.vera-cccd-viewer-head strong{font-size:15px}
    .vera-cccd-viewer-image{display:flex;align-items:center;justify-content:center;min-height:280px;max-height:68vh;background:#101614;border-radius:12px;overflow:hidden}.vera-cccd-viewer-image img{display:block;max-width:100%;max-height:68vh;object-fit:contain}
    .vera-cccd-viewer-actions{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}.vera-cccd-viewer-actions button{min-height:36px}
    @media(max-width:700px){.vera-reference-row{align-items:stretch;flex-direction:column}.vera-reference-refresh{width:100%}.vera-cccd-viewer{padding:6px}.vera-cccd-viewer-card{border-radius:12px;padding:9px}}
  `
  document.head.appendChild(style)
}

function markMissingFields() {
  document.querySelectorAll('.profile-form label, .staff-form-panel .staff-form-grid label').forEach((label) => {
    const text = labelText(label)
    if (!REQUIRED_LABELS.has(text)) {
      label.classList.remove('vera-profile-missing')
      return
    }
    const control = label.querySelector('input:not([type="file"]), select, textarea')
    if (!control || control.disabled || control.type === 'password') return
    label.classList.toggle('vera-profile-missing', !String(control.value || '').trim())
  })
}

function sourceControl(label) {
  return label?.querySelector('input:not([type="file"]), select') || null
}

function makeSelectForLabel(label, kind, catalogs, onProvinceChanged) {
  if (!label || label.dataset.veraReferenceEnhanced === '1') return
  const original = sourceControl(label)
  if (!original) return
  const current = String(original.value || '').trim()
  const wrap = document.createElement('div')
  wrap.className = 'vera-reference-wrap'
  const row = document.createElement('div')
  row.className = 'vera-reference-row'
  const select = document.createElement('select')
  select.setAttribute('aria-label', labelText(label))
  const refresh = document.createElement('button')
  refresh.type = 'button'
  refresh.className = 'vera-reference-refresh'
  refresh.textContent = '↻ Cập nhật danh mục'
  row.append(select, refresh)
  wrap.append(row)
  original.style.display = 'none'
  original.insertAdjacentElement('afterend', wrap)
  label.dataset.veraReferenceEnhanced = '1'

  const render = (items) => {
    const selected = String(original.value || current || '').trim()
    select.innerHTML = ''
    const empty = document.createElement('option')
    empty.value = ''
    empty.textContent = kind === 'province' ? '-- Chọn Tỉnh/Thành phố --' : kind === 'ward' ? '-- Chọn Phường/Xã --' : '-- Chọn ngân hàng --'
    select.appendChild(empty)
    const values = kind === 'province'
      ? (items || []).map((item) => ({ value: item.name, text: item.name, code: item.code }))
      : (items || []).map((item) => ({ value: item, text: item }))
    if (selected && !values.some((item) => item.value === selected)) values.unshift({ value: selected, text: selected })
    values.forEach((item) => {
      const option = document.createElement('option')
      option.value = item.value
      option.textContent = item.text
      if (item.code !== undefined) option.dataset.code = item.code
      select.appendChild(option)
    })
    select.value = selected
  }

  if (kind === 'province') render(catalogs.provinces)
  if (kind === 'bank') render(catalogs.banks)
  if (kind === 'ward') render(catalogs.wards)

  select.addEventListener('change', async () => {
    setReactInputValue(original, select.value)
    if (kind === 'province') await onProvinceChanged?.(select.value)
    markMissingFields()
  })

  refresh.addEventListener('click', async () => {
    refresh.disabled = true
    const oldText = refresh.textContent
    refresh.textContent = 'Đang cập nhật…'
    try {
      const provinceSelect = Array.from(document.querySelectorAll('label')).find((item) => labelText(item) === 'Tỉnh/Thành phố')?.querySelector('.vera-reference-row select')
      const provinceName = provinceSelect?.value || ''
      const root = await referenceData('', true)
      if (kind === 'province') render(root.provinces || [])
      if (kind === 'bank') render(root.banks || [])
      if (kind === 'ward') {
        const province = (root.provinces || []).find((item) => item.name === provinceName)
        const wardData = province ? await referenceData(province.code, true) : { wards: [] }
        render(wardData.wards || [])
      }
    } catch (error) {
      window.alert(`Không cập nhật được danh mục: ${error.message}`)
    } finally {
      refresh.disabled = false
      refresh.textContent = oldText
    }
  })
}

async function enhanceReferenceDropdowns() {
  const labels = Array.from(document.querySelectorAll('.profile-form label, .staff-form-panel .staff-form-grid label'))
  const provinceLabels = labels.filter((label) => labelText(label) === 'Tỉnh/Thành phố')
  const wardLabels = labels.filter((label) => labelText(label) === 'Phường/Xã')
  const bankLabels = labels.filter((label) => labelText(label) === 'Tên ngân hàng')
  if (![...provinceLabels, ...wardLabels, ...bankLabels].some((label) => label.dataset.veraReferenceEnhanced !== '1')) return
  let catalogs
  try { catalogs = await referenceData() } catch { return }

  for (const provinceLabel of provinceLabels) {
    const original = sourceControl(provinceLabel)
    const currentProvince = String(original?.value || '').trim()
    let wardValues = []
    const currentMeta = (catalogs.provinces || []).find((item) => item.name === currentProvince)
    if (currentMeta) {
      try { wardValues = (await referenceData(currentMeta.code)).wards || [] } catch { wardValues = [] }
    }
    const scopedContainer = provinceLabel.closest('.staff-form-panel, .profile-form') || document
    const scopedWard = Array.from(scopedContainer.querySelectorAll('label')).find((label) => labelText(label) === 'Phường/Xã')
    makeSelectForLabel(provinceLabel, 'province', catalogs, async (name) => {
      const meta = (catalogs.provinces || []).find((item) => item.name === name)
      const wardSelect = scopedWard?.querySelector('.vera-reference-row select')
      const wardOriginal = sourceControl(scopedWard)
      if (!wardSelect || !wardOriginal) return
      setReactInputValue(wardOriginal, '')
      let wards = []
      if (meta) {
        try { wards = (await referenceData(meta.code)).wards || [] } catch { wards = [] }
      }
      wardSelect.innerHTML = '<option value="">-- Chọn Phường/Xã --</option>'
      wards.forEach((ward) => {
        const option = document.createElement('option'); option.value = ward; option.textContent = ward; wardSelect.appendChild(option)
      })
      markMissingFields()
    })
    if (scopedWard) makeSelectForLabel(scopedWard, 'ward', { wards: wardValues })
  }
  bankLabels.forEach((label) => makeSelectForLabel(label, 'bank', catalogs))
}

function openCccdViewer(sideCard, image) {
  document.querySelector('.vera-cccd-viewer')?.remove()
  const overlay = document.createElement('div')
  overlay.className = 'vera-cccd-viewer'
  const card = document.createElement('div')
  card.className = 'vera-cccd-viewer-card'
  const head = document.createElement('div')
  head.className = 'vera-cccd-viewer-head'
  const title = document.createElement('strong')
  title.textContent = `${sideCard.querySelector('.employee-id-side-head strong')?.textContent || 'CCCD'} · XEM ẢNH`
  const close = document.createElement('button')
  close.type = 'button'; close.className = 'secondary-button compact'; close.textContent = 'Đóng'
  close.onclick = () => overlay.remove()
  head.append(title, close)
  const imageBox = document.createElement('div')
  imageBox.className = 'vera-cccd-viewer-image'
  const large = document.createElement('img')
  large.src = image.src; large.alt = image.alt || 'CCCD'
  imageBox.appendChild(large)
  const actions = document.createElement('div')
  actions.className = 'vera-cccd-viewer-actions'
  sideCard.querySelectorAll('.employee-id-actions button').forEach((button) => {
    const clone = button.cloneNode(true)
    clone.disabled = button.disabled
    clone.onclick = () => { button.click(); if (/xóa/i.test(button.textContent || '')) overlay.remove() }
    actions.appendChild(clone)
  })
  card.append(head, imageBox, actions)
  overlay.appendChild(card)
  overlay.addEventListener('click', (event) => { if (event.target === overlay) overlay.remove() })
  document.body.appendChild(overlay)
}

function ensureCccdAlwaysVisible() {
  document.querySelectorAll('.employee-id-side').forEach((sideCard) => {
    const head = sideCard.querySelector('.employee-id-side-head strong')?.textContent || ''
    if (!/Mặt trước|Mặt sau/i.test(head)) return
    const preview = sideCard.querySelector('.employee-id-preview')
    if (!preview) return
    let image = preview.querySelector('img')
    const viewButton = Array.from(sideCard.querySelectorAll('.employee-id-actions button')).find((button) => /^\s*Xem\s*$/i.test(button.textContent || ''))
    if (!image && viewButton && !sideCard.dataset.veraAutoLoading) {
      sideCard.dataset.veraAutoLoading = '1'
      viewButton.click()
      window.setTimeout(() => { delete sideCard.dataset.veraAutoLoading }, 900)
      return
    }
    image = preview.querySelector('img')
    if (!image || preview.dataset.veraClickable === '1') return
    preview.dataset.veraClickable = '1'
    preview.title = 'Click để xem ảnh CCCD phóng to'
    preview.addEventListener('click', () => openCccdViewer(sideCard, image))
  })
}

export default function EmployeeProfileLiveEnhancer() {
  useEffect(() => {
    ensureStyle()
    let timer = null
    let busy = false
    const run = async () => {
      if (busy) return
      busy = true
      try {
        markMissingFields()
        await enhanceReferenceDropdowns()
        ensureCccdAlwaysVisible()
      } finally { busy = false }
    }
    const schedule = () => {
      if (timer) window.clearTimeout(timer)
      timer = window.setTimeout(() => void run(), 80)
    }
    const observer = new MutationObserver(schedule)
    observer.observe(document.body, { childList: true, subtree: true })
    document.addEventListener('input', schedule, true)
    document.addEventListener('change', schedule, true)
    void run()
    return () => {
      observer.disconnect()
      if (timer) window.clearTimeout(timer)
      document.removeEventListener('input', schedule, true)
      document.removeEventListener('change', schedule, true)
      document.querySelector('.vera-cccd-viewer')?.remove()
    }
  }, [])
  return null
}
