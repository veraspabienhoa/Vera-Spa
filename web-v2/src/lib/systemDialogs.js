// One presentation layer for application feedback, confirmations and prompts.
// Passive notices queue; a user action can open a child dialog above its caller.
const managers = new WeakMap()
let sequence = 0
const titles = { info: 'Thông báo', success: 'Thành công', warning: 'Lưu ý', error: 'Không thể hoàn tất', confirm: 'Xác nhận', prompt: 'Nhập thông tin' }

function managerFor(doc) {
  if (!managers.has(doc)) managers.set(doc, { stack: [], queue: [], overflow: null })
  return managers.get(doc)
}

export function showSystemDialog(options = {}) {
  const doc = options.document || document
  const manager = managerFor(doc)
  const kind = options.kind || 'info'
  const interactive = kind === 'confirm' || kind === 'prompt'
  const opener = doc.activeElement
  let resolve, finished = false, dialog, cleanup = () => {}
  const result = new Promise(done => { resolve = done })
  const entry = { mount, close, result, get element() { return dialog } }

  function close(value = kind === 'prompt' ? null : false) {
    if (finished) return
    finished = true
    manager.queue = manager.queue.filter(item => item !== entry)
    const wasTop = manager.stack.at(-1) === entry
    manager.stack = manager.stack.filter(item => item !== entry)
    cleanup()
    if (dialog?.open && typeof dialog.close === 'function') dialog.close()
    dialog?.remove()
    resolve(value)
    if (!manager.stack.length) {
      if (manager.overflow !== null) { doc.body.style.overflow = manager.overflow; manager.overflow = null }
      if (dialog && opener?.isConnected) opener.focus({ preventScroll: true })
      manager.queue.shift()?.mount()
    } else if (wasTop) {
      const parent = manager.stack.at(-1).element
      ;(parent?.contains(opener) ? opener : parent)?.focus({ preventScroll: true })
    }
  }

  const dismiss = value => options.onDismiss ? options.onDismiss() : close(value)

  function mount() {
    if (finished) return
    manager.stack.push(entry)
    dialog = doc.createElement('dialog')
    dialog.className = `system-dialog system-dialog-${kind}`
    dialog.dataset.systemDialog = kind
    dialog.setAttribute('role', interactive ? 'alertdialog' : 'dialog')
    dialog.setAttribute('aria-modal', 'true')
    dialog.tabIndex = -1
    const title = doc.createElement('h2')
    title.id = `system-dialog-title-${++sequence}`
    title.textContent = options.title || titles[kind] || titles.info
    dialog.setAttribute('aria-labelledby', title.id)
    dialog.append(title)
    if (options.message) {
      const message = doc.createElement('p')
      message.className = 'system-dialog-message'
      message.id = `system-dialog-message-${sequence}`
      message.textContent = String(options.message)
      dialog.setAttribute('aria-describedby', message.id)
      dialog.append(message)
    }
    if (options.content) dialog.append(options.content)
    let input
    if (kind === 'prompt') {
      input = doc.createElement('input')
      input.className = 'system-dialog-input'
      input.setAttribute('aria-label', options.message || title.textContent)
      input.value = String(options.defaultValue ?? '')
      dialog.append(input)
    }
    const footer = doc.createElement('div')
    footer.className = 'system-dialog-actions'
    const button = (label, action, primary = false) => {
      const node = doc.createElement('button')
      node.type = 'button'; node.textContent = label
      node.className = primary ? 'primary-button' : 'secondary-button'
      node.addEventListener('click', action)
      footer.append(node)
      return node
    }
    for (const action of options.actions || []) {
      button(action.label, () => { close(); action.run?.() }).disabled = Boolean(action.disabled)
    }
    const cancel = interactive ? button('Hủy', () => dismiss()) : null
    const accept = button(interactive ? 'Xác nhận' : 'Đã hiểu', () => dismiss(input ? input.value : true), true)
    dialog.append(footer)
    doc.body.append(dialog)
    const onKeyDown = event => {
      if (manager.stack.at(-1) !== entry) return
      // Existing form dialogs also listen on document. Only the top modal acts.
      if (!['Escape', 'Tab', 'Enter'].includes(event.key)) return
      if (event.key === 'Enter' && event.target !== input) return
      event.stopImmediatePropagation()
      if (event.key === 'Escape') { event.preventDefault(); dismiss(); return }
      if (event.key === 'Enter') { event.preventDefault(); accept.click(); return }
      const controls = [...dialog.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]')].filter(node => !node.closest('[hidden]'))
      const first = controls[0], last = controls.at(-1)
      if (event.shiftKey && (!dialog.contains(doc.activeElement) || doc.activeElement === first || doc.activeElement === dialog)) {
        event.preventDefault(); (last || dialog).focus()
      } else if (!event.shiftKey && (!dialog.contains(doc.activeElement) || doc.activeElement === last || doc.activeElement === dialog)) {
        event.preventDefault(); (first || dialog).focus()
      }
    }
    const onCancel = event => { event.preventDefault(); dismiss() }
    doc.addEventListener('keydown', onKeyDown, true)
    dialog.addEventListener('cancel', onCancel)
    if (manager.overflow === null) manager.overflow = doc.body.style.overflow
    doc.body.style.overflow = 'hidden'
    cleanup = () => {
      doc.removeEventListener('keydown', onKeyDown, true)
      dialog.removeEventListener('cancel', onCancel)
    }
    if (typeof dialog.showModal === 'function') dialog.showModal()
    else {
      // Keep fallback dialogs modal as well, including embedded browsers.
      const background = [...doc.body.children].filter(node => node !== dialog).map(node => [node, node.hasAttribute('inert')])
      for (const [node] of background) node.setAttribute('inert', '')
      const originalCleanup = cleanup
      cleanup = () => { originalCleanup(); for (const [node, wasInert] of background) if (!wasInert) node.removeAttribute('inert') }
      dialog.classList.add('system-dialog-fallback')
      dialog.setAttribute('open', '')
    }
    ;(input || cancel || accept).focus({ preventScroll: true })
    input?.select()
  }

  if (!manager.stack.length || interactive || options.priority) mount()
  else manager.queue.push(entry)
  return entry
}

export const alertDialog = (message, options = {}) => showSystemDialog({ ...options, message, priority: true }).result
export const confirmDialog = message => showSystemDialog({ message, kind: 'confirm' }).result
export const promptDialog = (message, defaultValue = '') => showSystemDialog({ message, defaultValue, kind: 'prompt' }).result

export function clearSystemDialogs(doc = document) {
  const manager = managerFor(doc)
  // Cancel queued decisions first, so clearing cannot display another notice.
  for (const entry of [...manager.queue]) entry.close()
  for (const entry of [...manager.stack].reverse()) entry.close()
}
