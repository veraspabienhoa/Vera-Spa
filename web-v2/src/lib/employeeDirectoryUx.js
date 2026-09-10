const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim()
let scheduled = false

function ensureStyles() {
  if (document.getElementById('vera-employee-directory-ux-style')) return
  const style = document.createElement('style')
  style.id = 'vera-employee-directory-ux-style'
  style.textContent = `
    .vera-list-name-search{display:flex;align-items:center;gap:9px;margin:10px 0 4px;padding:9px 12px;border:1px solid #d7e1dc;border-radius:11px;background:#fff}
    .vera-list-name-search>span{font-size:15px;line-height:1}.vera-list-name-search input{width:100%;min-width:0;border:0!important;outline:0!important;box-shadow:none!important;background:transparent!important;padding:3px 0!important;font-weight:700}
    .vera-profile-header-actions{margin-left:auto;display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap}
    .vera-profile-header-actions .vera-profile-top-close{min-height:44px!important;padding:10px 18px!important;font-size:13px!important;font-weight:900!important;border-width:2px!important}
    .vera-profile-header-actions .vera-profile-save-top,.vera-profile-header-actions .vera-profile-refresh-top{min-height:42px!important;padding:9px 14px!important;font-size:12px!important;font-weight:900!important}
    @media(max-width:700px){.vera-profile-header-actions{width:100%;display:grid;grid-template-columns:1fr 1fr}.vera-profile-header-actions .vera-profile-top-close{grid-column:1/-1;width:100%}.vera-list-name-search{margin-top:8px}}
  `
  document.head.appendChild(style)
}

function ensureListSearch() {
  const panel = document.querySelector('.staff-list-panel')
  // EmployeePage owns one React-controlled search field in the toolbar.
  // Never inject a second input into React's list subtree: when filtering
  // removes rows, that unmanaged sibling can break DOM reconciliation and
  // leave the application on a blank screen.
  panel?.querySelector('.vera-list-name-search')?.remove()
}

function profilePanel() {
  return Array.from(document.querySelectorAll('.staff-form-panel')).find((panel) =>
    clean(panel.querySelector('h2')?.textContent).startsWith('SỬA HỒ SƠ ·')) || null
}

function employeeUsernameFromPanel(panel) {
  const title = clean(panel?.querySelector('h2')?.textContent)
  const marker = 'SỬA HỒ SƠ ·'
  return title.startsWith(marker) ? clean(title.slice(marker.length)) : ''
}

function actionButtonByText(root, pattern) {
  return Array.from(root?.querySelectorAll('button') || []).find((button) => pattern.test(clean(button.textContent))) || null
}

function waitFor(condition, timeoutMs = 9000) {
  return new Promise((resolve) => {
    const started = Date.now()
    const timer = window.setInterval(() => {
      let result = null
      try { result = condition() } catch { result = null }
      if (result || Date.now() - started >= timeoutMs) {
        window.clearInterval(timer)
        resolve(result || null)
      }
    }, 120)
  })
}

function editButtonForEmployee(username) {
  const wanted = clean(username)
  for (const row of document.querySelectorAll('.staff-table tbody tr')) {
    const name = clean(row.querySelector('td:nth-child(2) strong')?.textContent)
    if (name === wanted) return row.querySelector('.staff-edit-button')
  }
  for (const card of document.querySelectorAll('.staff-mobile-card')) {
    const name = clean(card.querySelector('.staff-mobile-head strong')?.textContent)
    if (name !== wanted) continue
    return Array.from(card.querySelectorAll('button')).find((button) => /Hồ sơ|Sửa/i.test(clean(button.textContent))) || null
  }
  return null
}

async function refreshOpenProfile(button, panel) {
  const username = employeeUsernameFromPanel(panel)
  if (!username || button.disabled) return
  const oldText = button.textContent
  button.disabled = true
  button.textContent = '↻ Đang làm mới…'
  try {
    const listPanel = document.querySelector('.staff-list-panel')
    const refresh = actionButtonByText(listPanel?.querySelector('.panel-title-row'), /^Làm mới$/i)
    if (!refresh) throw new Error('Không tìm thấy nút Làm mới danh sách.')
    refresh.click()
    await waitFor(() => refresh.disabled ? true : null, 1800)
    const finished = await waitFor(() => !refresh.disabled ? true : null, 9000)
    if (!finished) throw new Error('Quá thời gian tải lại danh sách nhân viên.')
    const edit = await waitFor(() => {
      const candidate = editButtonForEmployee(username)
      return candidate && !candidate.disabled ? candidate : null
    }, 2500)
    if (!edit) throw new Error(`Không tải lại được hồ sơ ${username}.`)
    edit.click()
    await waitFor(() => employeeUsernameFromPanel(profilePanel()) === username && profilePanel())
    profilePanel()?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  } catch (error) {
    window.alert(error?.message || 'Không làm mới được hồ sơ.')
  } finally {
    button.disabled = false
    button.textContent = oldText
  }
}

function ensureProfileHeaderActions() {
  const panel = profilePanel()
  if (!panel) return
  const header = panel.querySelector('.panel-title-row')
  const footer = panel.querySelector('.staff-form-actions')
  if (!header || !footer) return

  let actions = header.querySelector('.vera-profile-header-actions')
  if (!actions) {
    actions = document.createElement('div')
    actions.className = 'vera-profile-header-actions'
    header.appendChild(actions)
  }

  let close = header.querySelector('.vera-profile-top-close')
  if (!close) {
    close = document.createElement('button')
    close.type = 'button'
    close.className = 'secondary-button vera-profile-top-close'
    close.textContent = '✕ Đóng'
    close.addEventListener('click', () => {
      const cancel = actionButtonByText(footer, /^Hủy$|^Đóng$/i)
      cancel?.click()
    })
  }
  if (close.parentElement !== actions) actions.appendChild(close)
  close.textContent = '✕ Đóng'

  if (!actions.querySelector('.vera-profile-refresh-top')) {
    const refresh = document.createElement('button')
    refresh.type = 'button'
    refresh.className = 'secondary-button vera-profile-refresh-top'
    refresh.textContent = '↻ Làm mới'
    refresh.addEventListener('click', () => void refreshOpenProfile(refresh, profilePanel()))
    actions.insertBefore(refresh, close)
  }

  if (!actions.querySelector('.vera-profile-save-top')) {
    const save = document.createElement('button')
    save.type = 'button'
    save.className = 'primary-button vera-profile-save-top'
    save.textContent = '✓ Lưu hồ sơ'
    save.addEventListener('click', () => {
      const currentPanel = profilePanel()
      const originalSave = actionButtonByText(currentPanel?.querySelector('.staff-form-actions'), /Lưu hồ sơ/i)
      if (originalSave && !originalSave.disabled) originalSave.click()
    })
    actions.insertBefore(save, close)
  }

  const originalSave = actionButtonByText(footer, /Lưu hồ sơ/i)
  const topSave = actions.querySelector('.vera-profile-save-top')
  if (topSave) topSave.disabled = Boolean(originalSave?.disabled)
}

function reconcile() {
  ensureListSearch()
  ensureProfileHeaderActions()
}

export function startEmployeeDirectoryUx() {
  if (window.__veraEmployeeDirectoryUxStarted) return
  window.__veraEmployeeDirectoryUxStarted = true
  ensureStyles()

  const schedule = () => {
    if (scheduled) return
    scheduled = true
    window.requestAnimationFrame(() => {
      scheduled = false
      reconcile()
    })
  }

  const observer = new MutationObserver(schedule)
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['disabled', 'class', 'value'] })
  document.addEventListener('click', schedule, true)
  document.addEventListener('input', schedule, true)
  document.addEventListener('change', schedule, true)
  window.setInterval(reconcile, 1200)
  schedule()
}
