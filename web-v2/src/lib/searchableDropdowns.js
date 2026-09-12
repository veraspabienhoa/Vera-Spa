// Keep React-owned controls in place. A single floating search menu works for
// native selects, including controls created later by profile/leave enhancers.
import { searchTextMatches, scrollSearchOption } from './searchText.js'

export function dropdownOptions(control, query = '', options = control.options || control.list?.options || []) {
  return Array.from(options).map((option, index) => ({
    index, value: option.value, label: option.label || option.textContent || option.value || '',
    group: option.parentElement?.tagName === 'OPTGROUP' ? option.parentElement.label : '',
    disabled: option.disabled || option.parentElement?.disabled,
    hidden: option.hidden || option.parentElement?.hidden,
  })).filter((row) => !row.hidden && searchTextMatches([row.label, row.value, row.group], query))
}

export function startSearchableDropdowns(doc = document) {
  const win = doc.defaultView
  if (win.__veraSearchableDropdownsStop) return win.__veraSearchableDropdownsStop
  let active = null
  let restoringFocus = false
  const isSelect = (node) => node instanceof win.HTMLSelectElement && !node.multiple && Number(node.size || 0) <= 1
  const isDatalist = (node) => node instanceof win.HTMLInputElement && Boolean(node.getAttribute('list') || (active?.source === node && active.listId))
  const available = (node) => (isSelect(node) || isDatalist(node)) && node.isConnected && !node.matches(':disabled') && !node.readOnly
  const optionsFor = (state, query = '') => dropdownOptions(state.source, query, state.listId ? doc.getElementById(state.listId)?.options || [] : state.source.options)
  const listen = (node, type, handler, options) => {
    node.addEventListener(type, handler, options)
    return () => node.removeEventListener(type, handler, options)
  }
  const close = (restoreFocus = false) => {
    if (!active) return
    const state = active
    active = null
    state.observer.disconnect()
    state.removeInputListener()
    state.menu.remove()
    for (const [key, value] of Object.entries(state.attributes)) {
      if (value === null) state.source.removeAttribute(key)
      else state.source.setAttribute(key, value)
    }
    if (restoreFocus && available(state.source)) {
      restoringFocus = true
      state.source.focus({ preventScroll: true })
      restoringFocus = false
    }
  }
  const position = () => {
    if (!active) return
    if (!available(active.source)) { close(); return }
    const rect = active.source.getBoundingClientRect()
    const view = win.visualViewport
    const width = view?.width || win.innerWidth
    const height = view?.height || win.innerHeight
    const offsetTop = view?.offsetTop || 0
    const offsetLeft = view?.offsetLeft || 0
    const roomBelow = offsetTop + height - rect.bottom - 8
    const roomAbove = rect.top - offsetTop - 8
    // Choose a side once per opening. Filtering cannot flip or move the input.
    active.above ??= roomBelow < 200 && roomAbove > roomBelow
    const sideRoom = active.above ? roomAbove : roomBelow
    const menuHeight = Math.max(0, Math.min(active.listId ? 260 : 340, Math.max(active.listId ? 0 : 96, sideRoom), height - 16))
    const menuWidth = Math.max(0, Math.min(Math.max(rect.width, 240), width - 16))
    const preferredTop = active.above ? rect.top - menuHeight - 4 : rect.bottom + 4
    const top = Math.max(offsetTop + 8, Math.min(preferredTop, offsetTop + height - menuHeight - 8))
    Object.assign(active.menu.style, {
      left: `${Math.max(offsetLeft + 8, Math.min(rect.left, offsetLeft + width - menuWidth - 8))}px`,
      width: `${menuWidth}px`, height: `${menuHeight}px`, maxHeight: `${menuHeight}px`, top: `${top}px`,
    })
  }

  const highlight = (index) => {
    if (!active) return
    active.index = index
    const buttons = [...active.list.querySelectorAll('[role="option"]')]
    buttons.forEach((button, i) => button.classList.toggle('highlighted', i === index))
    if (buttons[index]) {
      active.input.setAttribute('aria-activedescendant', buttons[index].id)
      scrollSearchOption(active.list, buttons[index])
    } else active.input.removeAttribute('aria-activedescendant')
  }
  const choose = (row) => {
    if (!active || !row || row.disabled || !available(active.source)) return
    const source = active.source
    const current = optionsFor(active).find((item) => item.index === row.index && item.value === row.value)
    if (!current || current.disabled) return
    close(true)
    if (source.value === row.value) return
    Object.getOwnPropertyDescriptor(isSelect(source) ? win.HTMLSelectElement.prototype : win.HTMLInputElement.prototype, 'value').set.call(source, row.value)
    source.dispatchEvent(new win.Event('input', { bubbles: true }))
    source.dispatchEvent(new win.Event('change', { bubbles: true }))
  }
  const render = () => {
    if (!active) return
    active.rows = optionsFor(active, active.input.value)
    active.list.replaceChildren()
    active.rows.forEach((row, index) => {
      const button = doc.createElement('button')
      button.type = 'button'
      button.tabIndex = -1
      button.id = `vera-dropdown-option-${index}`
      button.setAttribute('role', 'option')
      button.setAttribute('aria-selected', String(row.value === active.source.value))
      button.setAttribute('aria-disabled', String(Boolean(row.disabled)))
      button.disabled = Boolean(row.disabled)
      button.textContent = row.label || 'Để trống'
      button.addEventListener('click', () => choose(row))
      active.list.appendChild(button)
    })
    if (!active.rows.length) {
      const empty = doc.createElement('p')
      empty.setAttribute('role', 'status')
      empty.textContent = 'Không có kết quả phù hợp.'
      active.list.appendChild(empty)
    }
    const selected = active.rows.findIndex((row) => !row.disabled && row.value === active.source.value)
    position()
    highlight(selected >= 0 ? selected : active.rows.findIndex((row) => !row.disabled))
  }
  const open = (source, query = '') => {
    if (!available(source)) return
    if (active?.source === source) { if (!active.listId) active.input.focus({ preventScroll: true }); return }
    close()
    const menu = doc.createElement('div')
    menu.className = 'vera-searchable-dropdown'
    const listId = isDatalist(source) ? source.getAttribute('list') : null
    const input = listId ? source : doc.createElement('input')
    if (!listId) {
      input.type = 'search'
      input.autocomplete = 'off'
      input.spellcheck = false
      input.placeholder = 'Gõ để tìm…'
      input.value = query
    }
    const labelNode = source.labels?.[0]?.cloneNode(true)
    labelNode?.querySelectorAll('select, input, button, textarea').forEach((node) => node.remove())
    const label = source.getAttribute('aria-label') || labelNode?.textContent?.trim() || 'Lựa chọn'
    const attributes = Object.fromEntries(['aria-expanded', 'aria-controls', ...(listId ? ['list', 'role', 'aria-autocomplete', 'aria-activedescendant'] : [])].map((key) => [key, source.getAttribute(key)]))
    if (!listId) input.setAttribute('aria-label', `Tìm kiếm: ${label}`)
    input.setAttribute('role', 'combobox')
    input.setAttribute('aria-autocomplete', 'list')
    input.setAttribute('aria-expanded', 'true')
    input.setAttribute('aria-controls', 'vera-dropdown-options')
    const list = doc.createElement('div')
    list.id = 'vera-dropdown-options'
    list.className = 'vera-searchable-dropdown-options'
    list.setAttribute('role', 'listbox')
    list.setAttribute('aria-label', label)
    if (!listId) {
      const search = doc.createElement('div')
      search.className = 'vera-dropdown-search-line'
      const clear = doc.createElement('button')
      clear.type = 'button'
      clear.textContent = 'Clear'
      clear.className = 'vera-dropdown-clear'
      clear.setAttribute('aria-label', `Clear ${label}`)
      clear.addEventListener('click', () => {
        input.value = ''
        input.dispatchEvent(new win.Event('input', { bubbles: true }))
        input.focus({ preventScroll: true })
      })
      search.append(input, clear)
      menu.append(search)
    }
    menu.append(list)
    // The host is outside React-owned children; never insert proxy siblings in
    // keyed table rows (filtering/removing rows must remain safe).
    ;(source.closest('dialog[open]') || doc.body).appendChild(menu)
    source.setAttribute('aria-expanded', 'true')
    source.setAttribute('aria-controls', list.id)
    if (listId) source.removeAttribute('list')
    const sourceOptions = () => listId ? doc.getElementById(listId)?.options || [] : source.options
    const signature = () => JSON.stringify([source.value, dropdownOptions(source, '', sourceOptions())])
    let previous = signature()
    const observer = new win.MutationObserver(() => {
      if (!available(source)) { close(); return }
      const next = signature()
      if (next !== previous) { previous = next; render() }
    })
    active = { source, menu, input, list, listId, rows: [], index: -1, observer, attributes, removeInputListener: listen(input, 'input', render) }
    menu.addEventListener('pointerdown', (event) => { if (event.pointerType !== 'touch' && event.target.closest('button')) event.preventDefault() })
    observer.observe(doc.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['disabled', 'hidden', 'value', 'label', 'selected'] })
    render()
    if (!listId) input.focus({ preventScroll: true })
  }
  const pointerdown = (event) => {
    if (active?.menu.contains(event.target)) return
    if (available(event.target)) { if (isSelect(event.target)) event.preventDefault(); open(event.target); return }
    close()
  }
  const click = (event) => {
    if (!available(event.target)) return
    // Also handles label activation and assistive-technology clicks.
    if (isSelect(event.target)) event.preventDefault()
    open(event.target)
  }
  const keydown = (event) => {
    if (active && (active.menu.contains(event.target) || event.target === active.source)) {
      if (event.isComposing) return
      if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); close(true); return }
      if (event.key === 'Tab') { close(true); return }
      if (event.key === 'Enter') { event.preventDefault(); event.stopImmediatePropagation(); choose(active.rows[active.index]); return }
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault()
        const enabled = active.rows.map((row, i) => row.disabled ? -1 : i).filter((i) => i >= 0)
        let next = enabled.indexOf(active.index) + (event.key === 'ArrowUp' ? -1 : 1)
        if (event.key === 'Home') next = 0
        if (event.key === 'End') next = enabled.length - 1
        highlight(enabled[Math.max(0, Math.min(enabled.length - 1, next))] ?? -1)
      }
      return
    }
    if (!isSelect(event.target) || !available(event.target) || event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return
    const typing = event.key.length === 1 && event.key !== ' '
    if (typing || ['Enter', ' ', 'ArrowDown', 'ArrowUp'].includes(event.key)) {
      event.preventDefault()
      open(event.target, typing ? event.key : '')
    }
  }
  const cleanup = [
    listen(doc, 'pointerdown', pointerdown, true), listen(doc, 'click', click, true),
    listen(doc, 'keydown', keydown, true), listen(win, 'resize', position),
    listen(doc, 'scroll', position, true),
    listen(doc, 'focusin', (event) => {
      if (active && !active.menu.contains(event.target) && event.target !== active.source) close()
      if (!restoringFocus && isDatalist(event.target) && available(event.target)) open(event.target)
    }),
    listen(doc, 'change', (event) => { if (event.target === active?.source) render() }),
    listen(doc, 'reset', () => close()),
  ]
  if (win.visualViewport) cleanup.push(listen(win.visualViewport, 'resize', position), listen(win.visualViewport, 'scroll', position))
  win.__veraSearchableDropdownsStop = () => { close(); cleanup.forEach((stop) => stop()); delete win.__veraSearchableDropdownsStop }
  return win.__veraSearchableDropdownsStop
}
