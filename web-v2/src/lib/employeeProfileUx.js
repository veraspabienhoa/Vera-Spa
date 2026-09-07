const REQUIRED_PROFILE_LABELS = [
  'Họ và tên đầy đủ',
  'Ngày sinh',
  'Giới tính',
  'Dân tộc',
  'Điện thoại',
  'Email',
  'Tỉnh/Thành phố',
  'Phường/Xã',
  'Địa chỉ cụ thể',
  'Số tài khoản ngân hàng',
  'Tên ngân hàng',
  'Số Căn cước',
  'Ngày cấp',
  'Nơi cấp',
]

const normalizeText = (value) => String(value || '').replace(/\s+/g, ' ').trim()

const isProfileForm = (form) => {
  if (!form) return false
  if (form.classList.contains('profile-form')) return true
  const panel = form.closest('.staff-form-panel')
  return normalizeText(panel?.querySelector('h2')?.textContent).startsWith('SỬA HỒ SƠ ·')
}

const fieldValue = (label) => {
  const control = label.querySelector('input:not([type="hidden"]), select, textarea')
  if (!control) return null
  return normalizeText(control.value)
}

const requiredLabelName = (label) => {
  const text = normalizeText(label.childNodes?.[0]?.textContent || label.textContent)
  return REQUIRED_PROFILE_LABELS.find((name) => text.startsWith(name)) || ''
}

function refreshMissingProfileFields() {
  document.querySelectorAll('.profile-form, .staff-form-panel .staff-form-grid').forEach((form) => {
    if (!isProfileForm(form)) return
    form.querySelectorAll('label').forEach((label) => {
      const name = requiredLabelName(label)
      const value = name ? fieldValue(label) : null
      const missing = Boolean(name && value !== null && !value)
      label.classList.toggle('vera-profile-field-missing', missing)
      if (missing) {
        label.dataset.missingProfileField = name
        label.title = `Nhân viên còn thiếu: ${name}`
      } else if (label.dataset.missingProfileField) {
        delete label.dataset.missingProfileField
        label.removeAttribute('title')
      }
    })
  })
}

function ensureStyles() {
  if (document.getElementById('vera-profile-ux-style')) return
  const style = document.createElement('style')
  style.id = 'vera-profile-ux-style'
  style.textContent = `
    .vera-profile-field-missing{padding:8px;border:1px solid #e6b84d!important;border-radius:10px;background:#fff4c9!important;color:#6e4d00!important;box-shadow:0 0 0 2px rgba(230,184,77,.10)}
    .vera-profile-field-missing input,.vera-profile-field-missing select,.vera-profile-field-missing textarea{border-color:#d8a62d!important;background:#fffdf2!important}
    .vera-profile-field-missing::after{content:'Còn thiếu thông tin';font-size:10px;font-weight:900;color:#9a6200;letter-spacing:.01em}
    .employee-id-preview[data-vera-cccd-clickable="true"]{cursor:zoom-in;position:relative;outline:1px dashed rgba(21,74,54,.25);outline-offset:-4px}
    .employee-id-preview[data-vera-cccd-clickable="true"]::after{content:'Bấm ảnh để xem lớn';position:absolute;right:7px;bottom:7px;padding:4px 7px;border-radius:999px;background:rgba(8,31,23,.78);color:#fff;font-size:10px;font-weight:800;pointer-events:none}
    .vera-cccd-viewer{position:fixed;inset:0;z-index:12000;background:rgba(5,18,14,.88);display:flex;align-items:center;justify-content:center;padding:16px}
    .vera-cccd-viewer-card{width:min(1100px,100%);max-height:96vh;overflow:auto;border-radius:18px;background:#fff;padding:14px;box-shadow:0 28px 80px rgba(0,0,0,.45)}
    .vera-cccd-viewer-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.vera-cccd-viewer-head h3{margin:0;font-size:16px}.vera-cccd-viewer-close{border:1px solid #d6dfdb;background:#fff;border-radius:9px;padding:8px 12px;font-weight:800;cursor:pointer}
    .vera-cccd-viewer-image{min-height:260px;max-height:72vh;border-radius:13px;background:#101815;display:flex;align-items:center;justify-content:center;overflow:hidden}.vera-cccd-viewer-image img{display:block;max-width:100%;max-height:72vh;width:auto;height:auto;object-fit:contain}
    .vera-cccd-viewer-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.vera-cccd-viewer-actions button{min-height:36px;border:1px solid #ccd8d2;border-radius:9px;background:#fff;padding:7px 11px;font-weight:800;cursor:pointer}.vera-cccd-viewer-actions button.danger{border-color:#e6b4ae;color:#a62a20;background:#fff5f4}
    @media(max-width:700px){.vera-profile-field-missing{padding:7px}.vera-cccd-viewer{padding:6px}.vera-cccd-viewer-card{padding:10px;border-radius:13px}.vera-cccd-viewer-image{min-height:180px}.vera-cccd-viewer-actions{display:grid;grid-template-columns:1fr 1fr}.vera-cccd-viewer-actions button{width:100%}}
  `
  document.head.appendChild(style)
}

const actionText = (button) => normalizeText(button.textContent)

function closeViewer() {
  document.querySelector('.vera-cccd-viewer')?.remove()
}

function openViewer(card, image) {
  closeViewer()
  const title = normalizeText(card.querySelector('.employee-id-side-head strong')?.textContent) || 'CCCD'
  const overlay = document.createElement('div')
  overlay.className = 'vera-cccd-viewer'
  overlay.innerHTML = `
    <div class="vera-cccd-viewer-card" role="dialog" aria-modal="true" aria-label="Xem ảnh ${title}">
      <div class="vera-cccd-viewer-head"><h3>${title.toUpperCase()} · CCCD</h3><button type="button" class="vera-cccd-viewer-close">Đóng</button></div>
      <div class="vera-cccd-viewer-image"><img alt="${title} CCCD" /></div>
      <div class="vera-cccd-viewer-actions"></div>
    </div>
  `
  overlay.querySelector('.vera-cccd-viewer-image img').src = image.src
  overlay.querySelector('.vera-cccd-viewer-close').addEventListener('click', closeViewer)
  overlay.addEventListener('click', (event) => { if (event.target === overlay) closeViewer() })

  const actions = overlay.querySelector('.vera-cccd-viewer-actions')
  const originals = Array.from(card.querySelectorAll('.employee-id-actions button'))
    .filter((button) => !/^Xem$/i.test(actionText(button)))
  originals.forEach((original) => {
    const button = document.createElement('button')
    button.type = 'button'
    button.textContent = actionText(original)
    if (/Xóa/i.test(button.textContent)) button.classList.add('danger')
    button.disabled = original.disabled
    button.addEventListener('click', () => {
      original.click()
      if (!/Tải xuống/i.test(button.textContent)) closeViewer()
    })
    actions.appendChild(button)
  })
  document.body.appendChild(overlay)
}

function waitForCccdImage(card, timeoutMs = 4500) {
  const existing = card.querySelector('.employee-id-preview img')
  if (existing?.src) return Promise.resolve(existing)
  return new Promise((resolve) => {
    const started = Date.now()
    const timer = window.setInterval(() => {
      const image = card.querySelector('.employee-id-preview img')
      if (image?.src || Date.now() - started > timeoutMs) {
        window.clearInterval(timer)
        resolve(image || null)
      }
    }, 80)
  })
}

async function handleCccdPreviewClick(preview) {
  const card = preview.closest('.employee-id-side')
  if (!card || card.classList.contains('draft')) return
  let image = card.querySelector('.employee-id-preview img')
  if (!image?.src) {
    const viewButton = Array.from(card.querySelectorAll('.employee-id-actions button')).find((button) => /^Xem$/i.test(actionText(button)))
    if (!viewButton || viewButton.disabled) return
    viewButton.click()
    image = await waitForCccdImage(card)
  }
  if (image?.src) openViewer(card, image)
}

function refreshCccdCards() {
  document.querySelectorAll('.employee-id-side:not(.draft)').forEach((card) => {
    const preview = card.querySelector('.employee-id-preview')
    if (!preview) return
    const hasSavedImage = Array.from(card.querySelectorAll('.employee-id-actions button')).some((button) => /^Xem$/i.test(actionText(button)))
    if (hasSavedImage) preview.dataset.veraCccdClickable = 'true'
    else delete preview.dataset.veraCccdClickable
  })
}

let scheduled = false
function refresh() {
  if (scheduled) return
  scheduled = true
  window.requestAnimationFrame(() => {
    scheduled = false
    refreshMissingProfileFields()
    refreshCccdCards()
  })
}

export function startEmployeeProfileUxEnhancements() {
  if (window.__veraEmployeeProfileUxStarted) return
  window.__veraEmployeeProfileUxStarted = true
  ensureStyles()
  refresh()

  document.addEventListener('input', refresh, true)
  document.addEventListener('change', refresh, true)
  document.addEventListener('click', (event) => {
    const preview = event.target.closest?.('.employee-id-preview[data-vera-cccd-clickable="true"]')
    if (preview) void handleCccdPreviewClick(preview)
  }, true)

  const observer = new MutationObserver(refresh)
  observer.observe(document.body, { childList: true, subtree: true })
}
