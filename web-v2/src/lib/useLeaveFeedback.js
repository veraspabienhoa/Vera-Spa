import { useEffect, useMemo, useRef } from 'react'
import { showSystemDialog } from './systemDialogs'
import { feedbackCategory } from './systemFeedback'

// Own only this page's dialogs: navigation/account changes must not leave an
// old result or decision in the shared queue, or dismiss another module's work.
export default function useLeaveFeedback(routing = 'none') {
  const scope = useRef({ active: false, entries: new Map() })
  useEffect(() => {
    const state = scope.current
    state.active = true
    const close = () => {
      const entries = [...state.entries.values()]
      state.entries.clear()
      for (const entry of entries.reverse()) entry.close()
    }
    window.addEventListener('popstate', close)
    return () => { state.active = false; window.removeEventListener('popstate', close); close() }
  }, [])

  return useMemo(() => {
    const show = options => {
      const state = scope.current
      if (!state.active) return Promise.resolve(options.kind === 'prompt' ? null : false)
      const key = JSON.stringify([options.kind, options.title, options.message])
      if (state.entries.has(key)) return state.entries.get(key).result
      const entry = showSystemDialog({ ...options, dismissLabel: 'Đóng' })
      state.entries.set(key, entry)
      if (options.routeFeedback) window.dispatchEvent(new window.CustomEvent('vera-system-feedback', {
        detail: { category: options.routeCategory || feedbackCategory(options.kind, options.message || '') },
      }))
      void entry.result.then(() => { if (state.entries.get(key) === entry) state.entries.delete(key) })
      return entry.result
    }
    // Retain existing configured category routing only for feedback that used
    // the observer before. New check results are presentation-only notices.
    const notify = ({ status = 'info', ...options }) => show({
      routeFeedback: routing === 'all' || (routing === 'errors' && ['error', 'warning'].includes(status)),
      ...options, kind: status,
    })
    notify.confirm = message => show({ message, kind: 'confirm' })
    notify.prompt = (message, defaultValue = '') => show({ message, defaultValue, kind: 'prompt' })
    // Inspect validity without firing the global invalid listener: this page
    // must own validation notices too, so they cannot survive a role/route change.
    notify.validate = container => {
      const input = [...container.querySelectorAll('input,select,textarea')].find(node => node.willValidate && !node.validity.valid)
      if (!input) return true
      const label = input.getAttribute('aria-label') || input.labels?.[0]?.textContent?.trim() || 'Trường thông tin'
      const message = input.validity.valueMissing ? `Vui lòng nhập ${label.toLocaleLowerCase('vi-VN')}.` : `${label}: ${input.validationMessage}`
      void notify({ status: 'warning', message, routeFeedback: false }).then(() => {
        if (scope.current.active && input.isConnected && !document.querySelector('.system-dialog')) input.focus({ preventScroll: true })
      })
      return false
    }
    return notify
  }, [routing])
}
