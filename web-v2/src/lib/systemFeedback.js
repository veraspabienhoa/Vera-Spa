import { showSystemDialog } from './systemDialogs'

const SELECTOR = '[role="alert"],.error-box,.success-box,.warning-box,.stable-feedback .setup-note,.stable-feedback [role="status"],.schedule-notice,.shift-break-error,.shift-break-message,.device-error,.employee-identity-notice,.leave-list-personal-summary-error,.payroll-timesoft-auto-notice,.past-violation-submit-notice,.live-penalty-preview.error,.vera-cccd-text-status,.vera-cccd-target-status,.advance-ledger-message,[data-system-feedback]'
const GUIDANCE = /(?:hãy|vui lòng|chưa chọn|chọn .*nhân viên|bộ lọc|không tìm thấy .*phù hợp)/i
export function feedbackCategory(kind, message) {
  return GUIDANCE.test(message) ? 'ui_guidance' : kind === 'success' ? 'ui_success' : kind === 'warning' ? 'ui_warning' : 'ui_error'
}

export function startSystemFeedback(doc = document) {
  const seen = new WeakMap(), notices = new Set(), invalidForms = new Set()
  const add = element => {
    if (!element.matches?.(SELECTOR)) {
      if (element.hasAttribute?.('data-feedback-presented')) { seen.get(element)?.notice.close(); seen.delete(element); element.removeAttribute('data-feedback-presented') }
      return
    }
    if (element.closest('[data-feedback-inline],.system-dialog-message,.action-success-dialog')) return
    if (element.parentElement?.closest(SELECTOR)) return
    // Ignore loading indicators and table data, which are not operation feedback.
    const message = String(element.textContent || '').replace(/\s+/g, ' ').trim()
    if (!message) { seen.get(element)?.notice.close(); seen.delete(element); element.removeAttribute('data-feedback-presented'); return }
    if (/^Đang (?:tải|lưu|xử lý|mở|tạo|cập nhật|xác minh|nhận dạng|đọc|trích xuất)/i.test(message)) {
      seen.get(element)?.notice.close(); seen.delete(element); element.removeAttribute('data-feedback-presented'); return
    }
    if (element.closest('[hidden]')) return
    if (seen.get(element)?.message === message) return
    seen.get(element)?.notice.close()
    const kind = /(?:error|danger)/.test(element.className) || element.getAttribute('role') === 'alert' ? 'error'
      : /success|(?:^|\s)ok(?:\s|$)/.test(element.className) ? 'success' : /warning|setup-note|(?:^|\s)warn(?:\s|$)/.test(element.className) ? 'warning' : 'info'
    const buttons = [...element.querySelectorAll('button,a[href]')]
    const actions = buttons.map(node => ({ disabled: Boolean(node.disabled), label: node.textContent.trim() || node.getAttribute('aria-label') || 'Mở', run: () => { if (node.isConnected && !node.disabled) node.click() } }))
    const copy = element.cloneNode(true)
    copy.querySelectorAll('button,a[href]').forEach(node => node.remove())
    const notice = showSystemDialog({ message: copy.textContent.trim() || message, kind, actions, priority: Boolean(element.closest('.system-dialog')) })
    notices.add(notice)
    void notice.result.then(() => notices.delete(notice))
    seen.set(element, { message, notice })
    element.setAttribute('data-feedback-presented', '')
    doc.defaultView.dispatchEvent(new doc.defaultView.CustomEvent('vera-system-feedback', { detail: { category: feedbackCategory(kind, message) } }))
  }
  const visit = node => {
    if (node.nodeType !== 1) return
    add(node)
    node.querySelectorAll(SELECTOR).forEach(add)
  }
  const onInvalid = event => {
    const input = event.target
    if (!input.validationMessage) return
    event.preventDefault()
    const form = input.form || input
    if (invalidForms.has(form)) return
    invalidForms.add(form)
    const label = input.getAttribute('aria-label') || input.labels?.[0]?.textContent?.trim() || 'Trường thông tin'
    const message = input.validity.valueMissing ? `Vui lòng nhập ${label.toLocaleLowerCase('vi-VN')}.` : `${label}: ${input.validationMessage}`
    const notice = showSystemDialog({ message, kind: 'warning', priority: true })
    notices.add(notice)
    void notice.result.then(() => { invalidForms.delete(form); notices.delete(notice); if (input.isConnected) input.focus({ preventScroll: true }) })
  }
  doc.addEventListener('invalid', onInvalid, true)
  visit(doc.body)
  const observer = new doc.defaultView.MutationObserver(mutations => {
    for (const mutation of mutations) {
      const parent = mutation.target.nodeType === 1 ? mutation.target : mutation.target.parentElement
      const target = parent?.closest(SELECTOR)
      if (target) add(target)
      if (mutation.type === 'attributes') visit(parent)
      mutation.addedNodes.forEach(visit)
    }
  })
  observer.observe(doc.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['hidden', 'class', 'role'] })
  return () => { observer.disconnect(); doc.removeEventListener('invalid', onInvalid, true); notices.forEach(notice => notice.close()) }
}
