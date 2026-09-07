import { staffSecurityApi } from './staffSecurityApi'

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

const parseMissingFromTitle = (element) => {
  const title = normalizeText(element?.getAttribute('title'))
  if (!title.startsWith('Hồ sơ còn thiếu:')) return []
  return title
    .slice('Hồ sơ còn thiếu:'.length)
    .split(',')
    .map((item) => normalizeText(item))
    .filter((item) => item && item !== 'Quận/Huyện')
}

function refreshMissingBadges() {
  document.querySelectorAll('.staff-table tbody tr, .staff-mobile-card').forEach((item) => {
    const badge = item.querySelector('.staff-incomplete-badge')
    if (!badge) return
    const missing = parseMissingFromTitle(item)
    if (!missing.length) {
      badge.hidden = true
      item.classList.remove('staff-incomplete-row', 'incomplete')
      return
    }
    badge.hidden = false
    badge.textContent = `Thiếu: ${missing.join(', ')}`
    badge.title = `Hồ sơ còn thiếu: ${missing.join(', ')}`
    item.setAttribute('title', badge.title)
  })
}

function ensureStyles() {
  if (document.getElementById('vera-profile-ux-style')) return
  const style = document.createElement('style')
  style.id = 'vera-profile-ux-style'
  style.textContent = `
    .vera-profile-field-missing{padding:8px;border:2px solid #e1a51f!important;border-radius:10px;background:#fff0b3!important;color:#6e4d00!important;box-shadow:0 0 0 3px rgba(225,165,31,.12)}
    .vera-profile-field-missing input,.vera-profile-field-missing select,.vera-profile-field-missing textarea{border:2px solid #d89a12!important;background:#fff9df!important;box-shadow:0 0 0 2px rgba(216,154,18,.10)!important}
    .vera-profile-field-missing::after{content:'Thiếu: ' attr(data-missing-profile-field);font-size:10px;font-weight:900;color:#9a6200;letter-spacing:.01em}
    .staff-incomplete-badge{display:block!important;max-width:280px;margin-top:3px;white-space:normal;line-height:1.25;background:#ffe59a!important;color:#6f4b00!important;border:1px solid #e2b13a;border-radius:6px;padding:2px 5px;font-size:10px;font-weight:900}
    .employee-id-preview[data-vera-cccd-clickable="true"]{cursor:zoom-in;position:relative;outline:1px dashed rgba(21,74,54,.25);outline-offset:-4px}
    .employee-id-preview[data-vera-cccd-clickable="true"]::after{content:'Bấm ảnh để xem lớn';position:absolute;right:7px;bottom:7px;padding:4px 7px;border-radius:999px;background:rgba(8,31,23,.78);color:#fff;font-size:10px;font-weight:800;pointer-events:none}
    .vera-cccd-viewer{position:fixed;inset:0;z-index:12000;background:rgba(5,18,14,.88);display:flex;align-items:center;justify-content:center;padding:16px}
    .vera-cccd-viewer-card{width:min(1100px,100%);max-height:96vh;overflow:auto;border-radius:18px;background:#fff;padding:14px;box-shadow:0 28px 80px rgba(0,0,0,.45)}
    .vera-cccd-viewer-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.vera-cccd-viewer-head h3{margin:0;font-size:16px}.vera-cccd-viewer-close{border:1px solid #d6dfdb;background:#fff;border-radius:9px;padding:8px 12px;font-weight:800;cursor:pointer}
    .vera-cccd-viewer-image{min-height:260px;max-height:72vh;border-radius:13px;background:#101815;display:flex;align-items:center;justify-content:center;overflow:hidden}.vera-cccd-viewer-image img{display:block;max-width:100%;max-height:72vh;width:auto;height:auto;object-fit:contain}
    .vera-cccd-viewer-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.vera-cccd-viewer-actions button{min-height:36px;border:1px solid #ccd8d2;border-radius:9px;background:#fff;padding:7px 11px;font-weight:800;cursor:pointer}.vera-cccd-viewer-actions button.danger{border-color:#e6b4ae;color:#a62a20;background:#fff5f4}
    .vera-cccd-text-panel{display:grid;gap:8px;margin-top:12px;padding:12px;border:1px solid #cfdcd6;border-radius:12px;background:#f6faf8}.vera-cccd-text-panel strong{font-size:12px;color:#173d2f}.vera-cccd-text-panel textarea{width:100%;min-height:160px;resize:vertical;border:1px solid #c8d6d0;border-radius:9px;background:#fff;padding:10px;font:500 13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#17251f;user-select:text;-webkit-user-select:text}.vera-cccd-text-panel-actions{display:flex;justify-content:flex-end;gap:8px}.vera-cccd-text-status{font-size:11px;color:#4c6259}.vera-cccd-text-status.ok{color:#17603b;font-weight:800}.vera-cccd-text-status.error{color:#a62a20;font-weight:800}
    @media(max-width:700px){.vera-profile-field-missing{padding:7px}.staff-incomplete-badge{max-width:100%}.vera-cccd-viewer{padding:6px}.vera-cccd-viewer-card{padding:10px;border-radius:13px}.vera-cccd-viewer-image{min-height:180px}.vera-cccd-viewer-actions{display:grid;grid-template-columns:1fr 1fr}.vera-cccd-viewer-actions button{width:100%}.vera-cccd-text-panel textarea{min-height:130px}.vera-cccd-text-panel-actions{display:grid;grid-template-columns:1fr}.vera-cccd-text-panel-actions button{width:100%}}
  `
  document.head.appendChild(style)
}

const actionText = (button) => normalizeText(button.textContent)

async function copyPlainText(value) {
  const text = String(value || '')
  if (!text) return false
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // Fall back to the legacy copy path below (Safari/private browsing can deny clipboard access).
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;'
  document.body.appendChild(textarea)
  textarea.select()
  let copied = false
  try { copied = document.execCommand('copy') } catch { copied = false }
  textarea.remove()
  return copied
}

function renderImageTextPanel(overlay, text, statusText, statusType = '') {
  const card = overlay.querySelector('.vera-cccd-viewer-card')
  if (!card) return
  let panel = card.querySelector('.vera-cccd-text-panel')
  if (!panel) {
    panel = document.createElement('div')
    panel.className = 'vera-cccd-text-panel'
    card.appendChild(panel)
  }
  panel.textContent = ''

  const heading = document.createElement('strong')
  heading.textContent = 'CHỮ NHẬN DẠNG TỪ ẢNH'
  const status = document.createElement('div')
  status.className = `vera-cccd-text-status ${statusType}`.trim()
  status.textContent = statusText
  panel.append(heading, status)

  if (!text) return
  const textarea = document.createElement('textarea')
  textarea.readOnly = true
  textarea.value = text
  textarea.setAttribute('aria-label', 'Chữ nhận dạng từ ảnh CCCD')
  textarea.addEventListener('focus', () => textarea.select())

  const actions = document.createElement('div')
  actions.className = 'vera-cccd-text-panel-actions'
  const copyButton = document.createElement('button')
  copyButton.type = 'button'
  copyButton.textContent = 'Sao chép toàn bộ'
  copyButton.addEventListener('click', async () => {
    const copied = await copyPlainText(text)
    status.className = `vera-cccd-text-status ${copied ? 'ok' : 'error'}`
    status.textContent = copied
      ? 'Đã sao chép toàn bộ chữ vào clipboard.'
      : 'Không tự sao chép được. Hãy chọn văn bản phía trên rồi dùng Ctrl/Cmd+C.'
    textarea.focus()
  })
  actions.appendChild(copyButton)
  panel.append(textarea, actions)
}

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
  const textButton = document.createElement('button')
  textButton.type = 'button'
  textButton.textContent = 'Sao chép chữ'
  textButton.title = 'Nhận dạng chữ trên ảnh CCCD, cho phép chọn và sao chép trực tiếp'
  textButton.addEventListener('click', async () => {
    const originalText = textButton.textContent
    textButton.disabled = true
    textButton.textContent = 'Đang đọc chữ…'
    renderImageTextPanel(overlay, '', 'Đang nhận dạng chữ trên ảnh…')
    try {
      const response = await fetch(image.src)
      if (!response.ok) throw new Error(`Không đọc được ảnh (HTTP ${response.status}).`)
      const blob = await response.blob()
      const result = await staffSecurityApi.extractImageText(blob)
      const text = String(result?.text || '').trim()
      if (!text) {
        renderImageTextPanel(overlay, '', 'Không nhận dạng được chữ. Hãy thử ảnh rõ hơn hoặc crop sát CCCD hơn.', 'error')
        return
      }
      const copied = await copyPlainText(text)
      renderImageTextPanel(
        overlay,
        text,
        copied ? 'Đã nhận dạng và sao chép toàn bộ chữ vào clipboard.' : 'Đã nhận dạng. Có thể chọn từng phần văn bản bên dưới để sao chép.',
        copied ? 'ok' : '',
      )
    } catch (error) {
      renderImageTextPanel(overlay, '', `Không đọc được chữ từ ảnh: ${error?.message || 'lỗi OCR'}`, 'error')
    } finally {
      textButton.disabled = false
      textButton.textContent = originalText
    }
  })
  actions.appendChild(textButton)

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
    refreshMissingBadges()
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
