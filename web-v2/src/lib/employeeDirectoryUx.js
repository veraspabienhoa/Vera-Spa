const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim()
const searchKey = (value) => clean(value)
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd')
  .replace(/Đ/g, 'D')
  .toLocaleLowerCase('vi')

let dropdownId = 0
let scheduled = false

function setNativeValue(control, value) {
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
    .vera-typing-select input{width:100%;min-width:0;padding-right:30px!important;cursor:text}
    .vera-typing-select::after{content:'⌄';position:absolute;right:9px;top:50%;transform:translateY(-52%);font-size:14px;font-weight:900;color:#496158;pointer-events:none}
    .vera-typing-select input:disabled{opacity:.62;cursor:not-allowed}
    .vera-typing-menu{position:fixed;z-index:30000;display:none;overflow:auto;padding:5px;background:#fff;border:1px solid #c8d7d0;border-radius:10px;box-shadow:0 12px 34px rgba(11,42,29,.18)}
    .vera-typing-menu.open{display:block}
    .vera-typing-option{display:block;width:100%;border:0;background:#fff;color:#142a21;text-align:left;padding:9px 10px;border-radius:7px;font:inherit;line-height:1.25;cursor:pointer;white-space:normal}
    .vera-typing-option:hover,.vera-typing-option:focus{background:#eef6f2;outline:none}
    .vera-typing-option.selected{font-weight:800;background:#e8f3ed}
    .vera-typing-empty{padding:10px;color:#6c7d75;font-size:12px}
    .staff-table td .vera-typing-select input{font-size:10px;padding:6px 22px 6px 5px!important;min-height:31px}
    @media(max-width:700px){.vera-profile-header-actions{width:100%;display:grid;grid-template-columns:1fr 1fr}.vera-profile-header-actions .vera-profile-top-close{grid-column:1/-1;width:100%}.vera-list-name-search{margin-top:8px}.vera-typing-select{width:100%}.vera-typing-menu{max-width:calc(100vw - 16px)}}
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
  const key = searchKey(query)
  if (!key) return optionRows(select).find((item) => item.value === '') || null
  return optionRows(select).find((item) =>
    searchKey(item.label) === key || searchKey(item.value) === key) || null
}

function firstMatchingOption(select, query) {
  const key = searchKey(query)
  if (!key) return null
  return optionRows(select).find((item) => !item.disabled && (
    searchKey(item.label).includes(key) || searchKey(item.value).includes(key)
  )) || null
}

function commitOption(select, row, input) {
  if (!row || row.disabled) return false
  setNativeValue(select, row.value)
  if (input) input.value = row.label
  return true
}

function menuFor(wrapper) {
  let menu = wrapper.__veraTypingMenu
  if (menu?.isConnected) return menu
  menu = document.createElement('div')
  menu.className = 'vera-typing-menu'
  menu.dataset.veraTypingMenu = wrapper.dataset.veraTypingId || ''
  menu.addEventListener('pointerdown', (event) => event.preventDefault())
  document.body.appendChild(menu)
  wrapper.__veraTypingMenu = menu
  return menu
}

function closeMenu(wrapper) {
  if (!wrapper) return
  wrapper.classList.remove('vera-open')
  const menu = wrapper.__veraTypingMenu
  if (menu) menu.classList.remove('open')
  const input = wrapper.querySelector('input')
  if (input) input.setAttribute('aria-expanded', 'false')
}

function closeAllMenus(except = null) {
  document.querySelectorAll('.vera-typing-select.vera-open').forEach((wrapper) => {
    if (wrapper !== except) closeMenu(wrapper)
  })
}

function positionMenu(input, menu) {
  if (!input?.isConnected || !menu) return
  const rect = input.getBoundingClientRect()
  const gap = 4
  const below = Math.max(80, window.innerHeight - rect.bottom - gap - 8)
  const above = Math.max(80, rect.top - gap - 8)
  const useAbove = below < 150 && above > below
  const maxHeight = Math.min(280, useAbove ? above : below)
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - 168))
  menu.style.left = `${left}px`
  menu.style.width = `${Math.max(160, Math.min(rect.width, window.innerWidth - left - 8))}px`
  menu.style.maxHeight = `${maxHeight}px`
  if (useAbove) {
    menu.style.top = 'auto'
    menu.style.bottom = `${Math.max(8, window.innerHeight - rect.top + gap)}px`
  } else {
    menu.style.bottom = 'auto'
    menu.style.top = `${Math.min(window.innerHeight - 8, rect.bottom + gap)}px`
  }
}

function filteredRows(select, query) {
  const key = searchKey(query)
  const rows = optionRows(select).filter((row) => !row.disabled && row.label)
  if (!key) return rows
  return rows.filter((row) => searchKey(row.label).includes(key) || searchKey(row.value).includes(key))
}

function renderMenu(select, input, wrapper, query = input.value) {
  if (!select?.isConnected || !input?.isConnected || select.disabled) {
    closeMenu(wrapper)
    return
  }
  const menu = menuFor(wrapper)
  const rows = filteredRows(select, query)
  menu.textContent = ''

  if (!rows.length) {
    const empty = document.createElement('div')
    empty.className = 'vera-typing-empty'
    empty.textContent = 'Không có lựa chọn phù hợp.'
    menu.appendChild(empty)
  } else {
    rows.slice(0, 120).forEach((row) => {
      const button = document.createElement('button')
      button.type = 'button'
      button.className = `vera-typing-option${String(row.value) === String(select.value) ? ' selected' : ''}`
      button.textContent = row.label
      button.dataset.value = row.value
      button.addEventListener('click', () => {
        if (commitOption(select, row, input)) {
          closeMenu(wrapper)
          input.focus({ preventScroll: true })
          input.select()
        }
      })
      menu.appendChild(button)
    })
  }

  closeAllMenus(wrapper)
  wrapper.classList.add('vera-open')
  input.setAttribute('aria-expanded', 'true')
  menu.classList.add('open')
  positionMenu(input, menu)
}

function syncEnhancedSelect(select, input, wrapper) {
  if (!select?.isConnected) {
    wrapper.__veraTypingMenu?.remove()
    return
  }
  if (input.disabled !== select.disabled) input.disabled = select.disabled
  const placeholder = clean(select.getAttribute('aria-label')) || 'Gõ để tìm…'
  if (input.placeholder !== placeholder) input.placeholder = placeholder
  if (document.activeElement !== input && !wrapper.classList.contains('vera-open')) {
    const label = selectedLabel(select)
    if (input.value !== label) input.value = label
  }
}

function enhanceSelect(select) {
  if (!(select instanceof HTMLSelectElement)) return
  if (!select.closest('.staff-page') || select.multiple || Number(select.size || 0) > 1) return

  if (select.dataset.veraTypingSearch === '1') {
    const wrapper = select.__veraTypingWrapper || (select.nextElementSibling?.classList?.contains('vera-typing-select') ? select.nextElementSibling : null)
    const input = wrapper?.querySelector('input')
    if (input && wrapper) syncEnhancedSelect(select, input, wrapper)
    return
  }

  select.dataset.veraTypingSearch = '1'
  select.classList.add('vera-typing-select-source')
  const wrapper = document.createElement('span')
  wrapper.className = 'vera-typing-select'
  wrapper.dataset.veraTypingId = `vera-typing-select-${++dropdownId}`
  const input = document.createElement('input')
  input.type = 'search'
  input.autocomplete = 'off'
  input.spellcheck = false
  input.setAttribute('role', 'combobox')
  input.setAttribute('aria-autocomplete', 'list')
  input.setAttribute('aria-expanded', 'false')
  wrapper.appendChild(input)
  select.insertAdjacentElement('afterend', wrapper)
  select.__veraTypingWrapper = wrapper

  const sync = () => syncEnhancedSelect(select, input, wrapper)
  sync()

  wrapper.addEventListener('click', (event) => {
    if (event.target === wrapper && !input.disabled) input.focus()
  })
  input.addEventListener('focus', () => {
    sync()
    window.setTimeout(() => {
      input.select()
      renderMenu(select, input, wrapper, '')
    }, 0)
  })
  input.addEventListener('click', () => {
    if (!wrapper.classList.contains('vera-open')) renderMenu(select, input, wrapper, '')
  })
  input.addEventListener('input', () => renderMenu(select, input, wrapper, input.value))
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeMenu(wrapper)
      input.value = selectedLabel(select)
      return
    }
    if (event.key === 'ArrowDown' && !wrapper.classList.contains('vera-open')) {
      event.preventDefault()
      renderMenu(select, input, wrapper, input.value)
      return
    }
    if (event.key !== 'Enter') return
    const row = exactOption(select, input.value) || firstMatchingOption(select, input.value)
    if (!row) return
    event.preventDefault()
    if (commitOption(select, row, input)) {
      closeMenu(wrapper)
      input.select()
    }
  })
  input.addEventListener('blur', () => {
    window.setTimeout(() => {
      if (!wrapper.classList.contains('vera-open')) input.value = selectedLabel(select)
    }, 100)
  })
  select.addEventListener('change', () => {
    input.value = selectedLabel(select)
    closeMenu(wrapper)
  })
}

function enhanceAllSelects() {
  document.querySelectorAll('.staff-page select').forEach(enhanceSelect)
  document.querySelectorAll('.vera-typing-select').forEach((wrapper) => {
    const source = wrapper.previousElementSibling
    if (!(source instanceof HTMLSelectElement) || !source.isConnected) {
      wrapper.__veraTypingMenu?.remove()
      wrapper.remove()
    }
  })
}

function repositionOpenMenus() {
  document.querySelectorAll('.vera-typing-select.vera-open').forEach((wrapper) => {
    const input = wrapper.querySelector('input')
    const menu = wrapper.__veraTypingMenu
    if (input && menu?.classList.contains('open')) positionMenu(input, menu)
  })
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
  document.addEventListener('pointerdown', (event) => {
    const target = event.target instanceof Element ? event.target : null
    if (target?.closest('.vera-typing-select') || target?.closest('.vera-typing-menu')) return
    closeAllMenus()
  }, true)
  window.addEventListener('resize', repositionOpenMenus)
  window.addEventListener('scroll', repositionOpenMenus, true)
  window.setInterval(reconcile, 1200)
  schedule()
}
