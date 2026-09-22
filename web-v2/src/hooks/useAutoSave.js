import { useEffect, useRef, useState } from 'react'

// One attempt per draft. A failed request is never retried in a render loop.
// Text/date/password fields finish on blur; selects and checkboxes save directly.
export default function useAutoSave({ signature, enabled, save, rootRef, lockRef, waitForExit = false }) {
  const latest = useRef(save)
  latest.current = save
  const attempted = useRef('')
  const [focusRevision, setFocusRevision] = useState(0)
  useEffect(() => {
    const root = rootRef.current
    const wake = () => setFocusRevision((value) => value + 1)
    root?.addEventListener('focusout', wake)
    return () => root?.removeEventListener('focusout', wake)
  })
  useEffect(() => {
    if (!signature) attempted.current = ''
    if (!enabled || !signature || attempted.current === signature) return undefined
    const timer = window.setTimeout(() => {
      const root = rootRef.current
      const active = document.activeElement
      if (!root || lockRef?.current || root.querySelector(':invalid')) return
      if (root.contains(active) && (waitForExit || active?.matches('textarea, input:not([type=checkbox]):not([type=radio])'))) return
      attempted.current = signature
      void latest.current()
    }, 900)
    return () => window.clearTimeout(timer)
  }, [signature, enabled, focusRevision, rootRef, lockRef, waitForExit])
}
