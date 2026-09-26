import { useEffect, useRef, useSyncExternalStore } from 'react'
import { getCustomization, subscribeCustomization } from '../lib/uiCustomizationStore'
export default function UiCustomText({ uiKey, children }) {
  const label = useSyncExternalStore(subscribeCustomization,
    () => getCustomization().items[uiKey]?.label || '', () => '')
  const text = useRef(null)
  useEffect(() => {
    if (!label) return undefined
    // Repeated row actions share a uiKey. Resolve only this label's owner;
    // querying the whole document once per row makes tab changes quadratic.
    let node = text.current?.parentElement
    while (node && node.dataset.uiKey !== uiKey) node = node.parentElement
    if (!node) return undefined
    const previous = node.getAttribute('aria-label')
    node.setAttribute('aria-label', label)
    return () => { if (previous == null) node.removeAttribute('aria-label'); else node.setAttribute('aria-label', previous) }
  }, [label, uiKey])
  return label ? <span ref={text}>{label}</span> : children
}
