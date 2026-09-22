import { useEffect, useSyncExternalStore } from 'react'
import { getCustomization, subscribeCustomization } from '../lib/uiCustomizationStore'
export default function UiCustomText({ uiKey, children }) {
  const { items } = useSyncExternalStore(subscribeCustomization, getCustomization, getCustomization)
  const label = items[uiKey]?.label
  useEffect(() => {
    if (!label) return undefined
    const nodes = [...document.querySelectorAll(`[data-ui-key="${uiKey}"]`)]
    const previous = nodes.map(node => [node, node.getAttribute('aria-label')])
    nodes.forEach(node => node.setAttribute('aria-label', label))
    return () => previous.forEach(([node, value]) => { if (value == null) node.removeAttribute('aria-label'); else node.setAttribute('aria-label', value) })
  }, [label, uiKey])
  return label || children
}
