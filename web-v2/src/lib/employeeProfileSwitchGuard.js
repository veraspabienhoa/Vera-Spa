const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim()

function ensureStyles() {
  if (document.getElementById('vera-profile-switch-guard-style')) return
  const style = document.createElement('style')
  style.id = 'vera-profile-switch-guard-style'
  style.textContent = `
    .vera-profile-top-close{margin-left:auto;white-space:nowrap}
    .vera-media-switching{position:relative}
    .vera-media-switching img{visibility:hidden!important}
    .vera-media-switching::after{content:'Đang tải đúng ảnh nhân viên…';position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:12px;text-align:center;background:#eef3f1;color:#53645d;font-size:11px;font-weight:900;z-index:2}
    .vera-media-current-empty{position:relative}
    .vera-media-current-empty img{display:none!important}
    .employee-portrait-preview.vera-media-current-empty::after{content:'CHƯA CÓ ẢNH 3:4';display:flex;align-items:center;justify-content:center;width:100%;height:100%;color:#9aa6a1;font-size:11px;font-weight:900;letter-spacing:.08em}
    .employee-id-preview.vera-media-current-empty::after{content:'CHƯA CÓ ẢNH CCCD';display:flex;align-items:center;justify-content:center;width:100%;height:100%;color:#9aa6a1;font-size:11px;font-weight:900;letter-spacing:.08em}
  `
  document.head.appendChild(style)
}

function activeProfilePanel() {
  return Array.from(document.querySelectorAll('.staff-form-panel')).find((panel) => {
    const title = clean(panel.querySelector('h2')?.textContent)
    return title.startsWith('SỬA HỒ SƠ ·')
  }) || null
}

function profileUsername(panel) {
  const title = clean(panel?.querySelector('h2')?.textContent)
  const marker = 'SỬA HỒ SƠ ·'
  return title.startsWith(marker) ? clean(title.slice(marker.length)) : ''
}

function ensureTopClose(panel) {
  const header = panel?.querySelector('.panel-title-row')
  if (!header || header.querySelector('.vera-profile-top-close')) return
  const button = document.createElement('button')
  button.type = 'button'
  button.className = 'secondary-button compact vera-profile-top-close'
  button.textContent = '✕ Đóng'
  button.addEventListener('click', () => {
    const cancel = Array.from(panel.querySelectorAll('.staff-form-actions button'))
      .find((item) => /^Hủy$/i.test(clean(item.textContent)))
    cancel?.click()
  })
  header.appendChild(button)
}

function mediaPreview(card) {
  return card.querySelector('.employee-portrait-preview, .employee-id-preview')
}

function mediaStatus(card) {
  return clean(card.querySelector('.employee-id-side-head span')?.textContent)
}

function viewButton(card) {
  return Array.from(card.querySelectorAll('.employee-id-actions button'))
    .find((button) => /^Xem$/i.test(clean(button.textContent))) || null
}

function resetCardForEmployee(card, username) {
  card.dataset.veraProfileOwner = username
  delete card.dataset.veraProfileRequestFor
  delete card.dataset.veraProfilePreviousSrc
  delete card.dataset.veraProfileRequestedAt
  delete card.dataset.veraProfileReady

  const preview = mediaPreview(card)
  const currentSrc = preview?.querySelector('img')?.src || ''
  if (currentSrc) card.dataset.veraProfilePreviousSrc = currentSrc
  preview?.classList.remove('vera-media-current-empty')
  preview?.classList.add('vera-media-switching')
}

function reconcileMediaCard(card, username) {
  if (!username) return
  if (card.dataset.veraProfileOwner !== username) resetCardForEmployee(card, username)

  const preview = mediaPreview(card)
  if (!preview) return
  const status = mediaStatus(card)
  const saved = status.startsWith('Đã lưu')
  const image = preview.querySelector('img')

  if (!saved) {
    preview.classList.remove('vera-media-switching')
    preview.classList.add('vera-media-current-empty')
    card.dataset.veraProfileReady = '1'
    return
  }

  preview.classList.remove('vera-media-current-empty')

  const previousSrc = card.dataset.veraProfilePreviousSrc || ''
  const currentSrc = image?.src || ''
  const requestedFor = card.dataset.veraProfileRequestFor || ''
  const requestedAt = Number(card.dataset.veraProfileRequestedAt || 0)
  const ready = card.dataset.veraProfileReady === '1'

  if (ready) {
    preview.classList.remove('vera-media-switching')
    return
  }

  // A new object URL means the current employee's image request completed.
  if (currentSrc && requestedFor === username && (!previousSrc || currentSrc !== previousSrc)) {
    card.dataset.veraProfileReady = '1'
    preview.classList.remove('vera-media-switching')
    return
  }

  preview.classList.add('vera-media-switching')
  const button = viewButton(card)
  const now = Date.now()
  const canRetry = requestedFor !== username || !requestedAt || now - requestedAt > 5000
  if (button && !button.disabled && canRetry) {
    card.dataset.veraProfileRequestFor = username
    card.dataset.veraProfileRequestedAt = String(now)
    button.click()
  }
}

function reconcileProfile() {
  const panel = activeProfilePanel()
  if (!panel) return
  const username = profileUsername(panel)
  if (!username) return
  ensureTopClose(panel)
  panel.querySelectorAll('.employee-portrait-side, .employee-id-side').forEach((card) => {
    reconcileMediaCard(card, username)
  })
}

export function startEmployeeProfileSwitchGuard() {
  if (window.__veraEmployeeProfileSwitchGuardStarted) return
  window.__veraEmployeeProfileSwitchGuardStarted = true
  ensureStyles()

  let timer = null
  const schedule = () => {
    if (timer) window.clearTimeout(timer)
    timer = window.setTimeout(reconcileProfile, 60)
  }

  const observer = new MutationObserver(schedule)
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['src', 'class'] })
  document.addEventListener('click', schedule, true)
  const interval = window.setInterval(reconcileProfile, 700)
  schedule()

  window.addEventListener('beforeunload', () => {
    observer.disconnect()
    window.clearInterval(interval)
    if (timer) window.clearTimeout(timer)
  }, { once: true })
}
