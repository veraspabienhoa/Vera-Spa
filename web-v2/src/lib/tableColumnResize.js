// Presentation-only enhancement: React retains ownership of table data/headers.
export function headerColumnMap(table) {
  const rows = Array.from(table.tHead?.rows || table.rows).filter(row => row.parentElement?.tagName !== 'TFOOT' && [...row.cells].some(cell => cell.tagName === 'TH')).filter(row => row.closest('table') === table)
  const occupied = [], cells = []
  rows.forEach((row, y) => {
    occupied[y] ||= []
    let x = 0
    for (const cell of row.cells) {
      while (occupied[y][x]) x++
      const span = cell.colSpan || 1
      cells.push({ cell, start: x, end: x + span, row: y })
      const height = cell.rowSpan === 0 ? rows.length - y : cell.rowSpan || 1
      for (let dy = 0; dy < height; dy++) {
        occupied[y + dy] ||= []
        for (let dx = 0; dx < span; dx++) occupied[y + dy][x + dx] = true
      }
      x += span
    }
  })
  const count = Math.max(0, ...occupied.map(row => row.length))
  // Prefer the lowest header ending at each internal column boundary.
  const boundaries = Array.from({ length: Math.max(0, count - 1) }, (_, index) =>
    cells.filter(item => item.end === index + 1).sort((a, b) => b.row - a.row)[0])
  return { cells, boundaries, count }
}

export function resizeColumnPair(widths, index, delta, minimum = 32) {
  const next = [...widths], total = widths[index] + widths[index + 1]
  const leftMin = Math.min(minimum, widths[index]), rightMin = Math.min(minimum, widths[index + 1])
  next[index] = Math.max(leftMin, Math.min(total - rightMin, widths[index] + delta))
  next[index + 1] = total - next[index]
  return next
}

export function startTableColumnResize(doc = document) {
  const win = doc.defaultView
  if (win.__veraTableColumnResizeStop) return win.__veraTableColumnResizeStop
  const states = new Map(), pending = new Set()
  const storageKey = state => {
    const identity = state.table.dataset.tableResizeKey || state.table.dataset.veraNode || state.table.id
    if (!identity) return null
    const schema = state.map.cells.map(({ cell, start, end }) => [cell.textContent.trim(), start, end])
    return `vera:column-widths:v1:${JSON.stringify([identity, win.innerWidth <= 640 ? 'mobile' : 'desktop', schema])}`
  }
  const remember = session => {
    const key = storageKey(session.state)
    if (!key || !session.latestWidths) return
    const total = session.latestWidths.reduce((sum, width) => sum + width, 0)
    try { win.localStorage.setItem(key, JSON.stringify(session.latestWidths.map(width => width / total))) } catch { /* Storage may be unavailable. Dragging still works. */ }
  }
  const recall = state => {
    const key = storageKey(state)
    if (!key) return
    try {
      const ratios = JSON.parse(win.localStorage.getItem(key))
      if (!Array.isArray(ratios) || ratios.length !== state.map.count || ratios.some(n => !Number.isFinite(n) || n <= 0 || n >= 1) || Math.abs(ratios.reduce((a,b) => a+b,0)-1) > .001) return
      const session = prepare(state)
      if (!session) return
      const total = session.widths.reduce((a,b) => a+b,0)
      paint(session, ratios.map(n => n * total))
    } catch { /* Ignore invalid or unavailable saved preferences. */ }
  }
  let active = null, frame = 0, suppressClick = false, clickTimer = 0
  const restoreStyle = (node, value) => value === null ? node.removeAttribute('style') : node.setAttribute('style', value)
  const saveStyle = node => node.getAttribute('style')
  const set = (node, key, value) => node.style.setProperty(key, value, 'important')
  const restoreSizing = state => {
    if (!state.sizing) return
    const { tableStyle, cols, colStyles, created } = state.sizing
    restoreStyle(state.table, tableStyle)
    if (created) created.remove()
    else cols.forEach((col, index) => restoreStyle(col, colStyles[index]))
    state.table.classList.remove('vera-columns-sized')
    state.sizing = null
  }
  const remove = state => {
    if (active?.state === state) finish(true)
    state.grips.forEach(grip => grip.remove())
    state.positioned.forEach(cell => cell.style.removeProperty('position'))
    restoreSizing(state)
    states.delete(state.table)
  }
  function prepare(state) {
    const { table, map } = state, rect = table.getBoundingClientRect()
    if (!rect.width || !table.offsetWidth || win.getComputedStyle(table).display !== 'table') return null
    const scale = rect.width / table.offsetWidth, edges = new Map()
    for (const item of map.cells) {
      const box = item.cell.getBoundingClientRect()
      if (!box.width) continue
      edges.set(item.start, box.left)
      edges.set(item.end, box.right)
    }
    const positions = Array.from({ length: map.count + 1 }, (_, index) => edges.get(index))
    if (positions.some(value => !Number.isFinite(value))) return null
    const widths = positions.slice(1).map((right, index) => (right - positions[index]) / scale)
    if (widths.some(value => value <= 0)) return null
    const initial = !state.sizing
    if (!state.sizing) {
      let group = table.querySelector(':scope > colgroup'), created = null
      // VERA colgroups have one col per logical column. Do not replace React nodes.
      if (group && (group.children.length !== map.count || [...group.children].some(col => col.span > 1))) return null
      if (!group) {
        group = doc.createElement('colgroup'); created = group
        for (let index = 0; index < map.count; index++) group.append(doc.createElement('col'))
        table.insertBefore(group, table.tHead)
      }
      const cols = [...group.children]
      state.sizing = { tableStyle: saveStyle(table), cols, colStyles: cols.map(saveStyle), created }
    }
    const priorTable = saveStyle(table), priorCols = state.sizing.cols.map(saveStyle)
    table.classList.add('vera-columns-sized')
    for (const property of ['width', 'min-width', 'max-width']) set(table, property, `${rect.width / scale}px`)
    set(table, 'table-layout', 'fixed')
    return { state, widths, scale, priorTable, priorCols, initial }
  }
  function paint(session, widths) {
    session.latestWidths = widths
    const total = widths.reduce((sum, width) => sum + width, 0)
    session.state.sizing.cols.forEach((col, index) => {
      set(col, 'width', `${widths[index] / total * 100}%`)
      set(col, 'min-width', '0'); set(col, 'max-width', 'none')
    })
  }
  function finish(cancel = false) {
    if (!active) return
    const session = active; active = null
    if (cancel) {
      restoreStyle(session.state.table, session.priorTable)
      session.state.sizing.cols.forEach((col, index) => restoreStyle(col, session.priorCols[index]))
      if (session.initial) restoreSizing(session.state)
    }
    if (!cancel) remember(session)
    doc.body.classList.remove('vera-column-resizing')
    clickTimer = win.setTimeout(() => { suppressClick = false }, 0)
  }
  function scan(table) {
    if (!table.isConnected || table.closest('[data-table-resize="off"]')) return
    const map = headerColumnMap(table), old = states.get(table)
    if (old && old.map.count === map.count && old.map.cells.length === map.cells.length && old.map.cells.every((item, i) => item.cell === map.cells[i].cell && item.start === map.cells[i].start && item.end === map.cells[i].end) && old.grips.every(grip => grip.isConnected)) return
    if (old) remove(old)
    if (map.count < 2) return
    const state = { table, map, grips: [], positioned: [], sizing: null }
    map.boundaries.forEach((item, index) => {
      if (!item) return
      const { cell } = item, grip = doc.createElement('span')
      if (win.getComputedStyle(cell).position === 'static') {
        cell.style.position = 'relative'; state.positioned.push(cell)
      }
      grip.className = 'vera-column-resize-handle'
      grip.dataset.columnBoundary = String(index)
      grip.setAttribute('data-html2canvas-ignore', 'true')
      grip.tabIndex = 0; grip.setAttribute('role', 'separator'); grip.setAttribute('aria-orientation', 'vertical')
      grip.setAttribute('aria-label', `Điều chỉnh độ rộng cột ${index + 1} và ${index + 2}`)
      grip.title = 'Kéo để chỉnh cột · Phím ← → để điều chỉnh'
      cell.append(grip); state.grips.push(grip)
    })
    states.set(table, state)
    recall(state)
  }
  function onDown(event) {
    const grip = event.target.closest?.('.vera-column-resize-handle')
    if (!grip || event.button !== 0 || active) return
    const state = states.get(grip.closest('table'))
    if (!state) return
    const session = prepare(state)
    if (!session) return
    event.preventDefault(); event.stopPropagation()
    win.clearTimeout(clickTimer); suppressClick = true
    active = { ...session, index: Number(grip.dataset.columnBoundary), pointerId: event.pointerId, startX: event.clientX }
    paint(active, active.widths)
    doc.body.classList.add('vera-column-resizing')
  }
  function onMove(event) {
    if (!active || event.pointerId !== active.pointerId) return
    event.preventDefault()
    paint(active, resizeColumnPair(active.widths, active.index, (event.clientX - active.startX) / active.scale))
  }
  function onUp(event) { if (active && event.pointerId === active.pointerId) finish(event.type === 'pointercancel') }
  function onKey(event) {
    if (event.key === 'Escape' && active) { event.preventDefault(); event.stopPropagation(); finish(true); return }
    const grip = event.target.closest?.('.vera-column-resize-handle')
    if (!grip || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return
    event.preventDefault(); event.stopPropagation()
    const state = states.get(grip.closest('table')), session = state && prepare(state)
    if (session) {
      paint(session, resizeColumnPair(session.widths, Number(grip.dataset.columnBoundary), (event.key === 'ArrowRight' ? 1 : -1) * (event.shiftKey ? 20 : 8)))
      remember(session)
    }
  }
  function onClick(event) {
    if (suppressClick || event.target.closest?.('.vera-column-resize-handle')) { event.preventDefault(); event.stopPropagation(); suppressClick = false }
  }
  const onBlur = () => finish(true)
  const onResize = () => { finish(true); states.forEach(state => { restoreSizing(state); recall(state) }) }
  const listeners = [[doc, 'pointerdown', onDown], [doc, 'pointermove', onMove], [doc, 'pointerup', onUp], [doc, 'pointercancel', onUp], [doc, 'keydown', onKey], [doc, 'click', onClick], [doc, 'dblclick', onClick], [win, 'blur', onBlur], [win, 'resize', onResize]]
  listeners.forEach(([target, name, handler]) => target.addEventListener(name, handler, true))
  const flush = () => {
    frame = 0
    states.forEach(state => { if (!state.table.isConnected) remove(state) })
    pending.forEach(scan); pending.clear()
  }
  const observer = new win.MutationObserver(records => {
    for (const record of records) {
      const owner = record.target.closest?.('table')
      if (owner && (record.target.closest?.('thead') || record.type === 'attributes')) pending.add(owner)
      for (const node of record.addedNodes) {
        if (node.nodeType !== 1 || node.matches('.vera-column-resize-handle,colgroup,col')) continue
        if (node.matches('table')) pending.add(node)
        node.querySelectorAll('table').forEach(table => pending.add(table))
      }
    }
    if (!frame) frame = win.requestAnimationFrame(flush)
  })
  doc.querySelectorAll('table').forEach(scan)
  observer.observe(doc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['colspan', 'rowspan'] })
  const stop = () => {
    finish(true); observer.disconnect(); win.cancelAnimationFrame(frame); win.clearTimeout(clickTimer)
    listeners.forEach(([target, name, handler]) => target.removeEventListener(name, handler, true))
    states.forEach(remove); pending.clear(); delete win.__veraTableColumnResizeStop
  }
  win.__veraTableColumnResizeStop = stop
  return stop
}
