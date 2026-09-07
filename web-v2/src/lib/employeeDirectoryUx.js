const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim()

let dropdownId = 0
let scheduled = false

function setNativeValue(control, value) {
  if (!control) return
  const proto = control instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype
    : HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set
  if (setter) setter.call(control, value)
  else control.value = value
  control.dispatchEvent(new Event('input', { bubbles: true }))
  control.dispatchEvent(new Event('change', { bubbles: true }))
}

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
    .vera-typing-select-source{position:absolute!important;width:1px!important;height:1px!important;opacity:0!important;pointer-events:none!important;overflow:hidden!important}
    .vera-typing-select{position:relative;display:flex;align-items:center;flex:1;min-width:0}
    .vera-typing-select input{width:100%;min-width:0;padding-right:30px!important}
    .vera-typing-select::after{content:'⌄';position:absolute;right:9px;top:50%;transform:translateY(-52%);font-size:14px;font-weight:900;color:#496158;pointer-events:none}
    .vera-typing-select input:disabled{opacity:.62;cursor:not-allowed}
    .staff-table td .vera-typing-select input{font-size:10px;padding:6px 22px 6px 5px!important;min-height:31px}
    @media(max-width:700px){.vera-profile-header-actions{width:100%;display:grid;grid-template-columns:1fr 1fr}.vera-profile-header-actions .vera-profile-top-close{grid-column:1/-1;width:100%}.vera-list-name-search{margin-top:8px}.vera-typing-select{width:100%}}
  `
  document.head.appendChild(style)
}

function originalEmployeeSearch() {
  return document.querySelector('.staff-control-panel .staff-search input')
}

function ensureListSearch() {
  const panel = document.querySelector('.staff-list-panel')
  const original = originalEmployeeSearch()
  if (!panel || !original) return

  let wrap = panel.querySelector('.vera-list-name-search')
  if (!wrap) {
    wrap = document.createElement('label')
    wrap.className = 'vera-list-name-search'
    wrap.innerHTML = '<span aria-hidden="true">⌕</span><input type="search" autocomplete="off" placeholder="Tìm tên nhân viên hoặc họ tên ngay trong danh sách" aria-label="Tìm tên nhân viên trong danh sách">'
    const titleRow = panel.querySelector('.panel-title-row')
    if (titleRow) titleRow.insertAdjacentElement('afterend', wrap)
    else panel.prepend(wrap)

    const proxy = wrap.querySelector('input')
    proxy.addEventListener('input', () => setNativeValue(originalEmployeeSearch(), proxy.value))
    proxy.addEventListener('search', () => setNativeValue(originalEmployeeSearch(), proxy.value))
  }
  const proxy = wrap.querySelector('input')
  if (proxy && document.activeElement !== proxy && proxy.value !== original.value) proxy.value = original.value
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
    const edit = await waitFor(() => {
      const candidate = editButtonForEmployee(username)
      return candidate && !candidate.disabled ? candidate : null
    })
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

function optionRows(select) {
  return Array.from(select.options).map((option) => ({
    value: option.value,
    label: clean(option.textContent),
    disabled: option.disabled,
  }))
}

function selectedLabel(select) {
  const option = Array.from(select.options).find((item) => item.value === select.value)
  return clean(option?.textContent || select.value)
}

function exactOption(select, query) {
  const key = clean(query).toLocaleLowerCase('vi')
  if (!key) return optionRows(select).find((item) => item.value === '') || null
  return optionRows(select).find((item) =>
    item.label.toLocaleLowerCase('vi') === key || String(item.value).toLocaleLowerCase('vi') === key) || null
}

function firstMatchingOption(select, query) {
  const key = clean(query).toLocaleLowerCase('vi')
  if (!key) return null
  return optionRows(select).find((item) => !item.disabled && item.label.toLocaleLowerCase('vi').includes(key)) || null
}

function commitOption(select, row) {
  if (!row || row.disabled) return false
  select.value = row.value
  select.dispatchEvent(new Event('input', { bubbles: true }))
  select.dispatchEvent(new Event('change', { bubbles: true }))
  return true
}

function rebuildDatalist(select, input, datalist) {
  datalist.textContent = ''
  optionRows(select).forEach((row) => {
    if (!row.label) return
    const option = document.createElement('option')
    option.value = row.label
    if (row.value && row.value !== row.label) option.label = row.value
    datalist.appendChild(option)
  })
  input.disabled = select.disabled
  input.placeholder = clean(select.getAttribute('aria-label')) || 'Gõ để tìm…'
  if (document.activeElement !== input) input.value = selectedLabel(select)
}

function enhanceSelect(select) {
  if (!(select instanceof HTMLSelectElement)) return
  if (!select.closest('.staff-page') || select.multiple || Number(select.size || 0) > 1) return

  if (select.dataset.veraTypingSearch === '1') {
    const wrapper = select.nextElementSibling?.classList?.contains('vera-typing-select') ? select.nextElementSibling : null
    const input = wrapper?.querySelector('input')
    const datalist = wrapper?.querySelector('datalist')
    if (input && datalist) rebuildDatalist(select, input, datalist)
    return
  }

  select.dataset.veraTypingSearch = '1'
  select.classList.add('vera-typing-select-source')
  const wrapper = document.createElement('span')
  wrapper.className = 'vera-typing-select'
  const input = document.createElement('input')
  input.type = 'text'
  input.autocomplete = 'off'
  input.spellcheck = false
  input.setAttribute('role', 'combobox')
  input.setAttribute('aria-autocomplete', 'list')
  const datalist = document.createElement('datalist')
  const listId = `vera-typing-select-${++dropdownId}`
  datalist.id = listId
  input.setAttribute('list', listId)
  wrapper.append(input, datalist)
  select.insertAdjacentElement('afterend', wrapper)

  const sync = () => rebuildDatalist(select, input, datalist)
  sync()

  input.addEventListener('focus', () => {
    sync()
    window.setTimeout(() => input.select(), 0)
  })
  input.addEventListener('input', () => {
    const exact = exactOption(select, input.value)
    if (exact) commitOption(select, exact)
  })
  input.addEventListener('change', () => {
    const exact = exactOption(select, input.value)
    if (exact && commitOption(select, exact)) input.value = exact.label
  })
  input.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return
    const row = exactOption(select, input.value) || firstMatchingOption(select, input.value)
    if (!row) return
    event.preventDefault()
    if (commitOption(select, row)) {
      input.value = row.label
      input.blur()
    }
  })
  input.addEventListener('blur', () => {
    window.setTimeout(() => { input.value = selectedLabel(select) }, 80)
  })
  select.addEventListener('change', sync)
}

function enhanceAllSelects() {
  document.querySelectorAll('.staff-page select').forEach(enhanceSelect)
}

function reconcile() {
  ensureListSearch()
  ensureProfileHeaderActions()
  enhanceAllSelects()
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
