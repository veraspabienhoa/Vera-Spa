import { useEffect } from 'react'
import './fitPayrollTables.css'

// Scale the whole table together: all columns and full amounts remain visible.
export function fitPayrollTable(table) {
  const available = table.parentElement?.clientWidth
  if (!available) return
  table.style.zoom = '1'
  const natural = table.scrollWidth
  table.style.zoom = String(natural > available ? available / natural : 1)
}

export default function useFitPayrollTables(ref) {
  useEffect(() => {
    const root = ref.current
    if (!root || typeof ResizeObserver === 'undefined') return
    let frame
    const fit = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => root.querySelectorAll('table').forEach(fitPayrollTable))
    }
    const resize = new ResizeObserver(fit)
    resize.observe(root)
    const mutation = new MutationObserver(fit)
    mutation.observe(root, { childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ['hidden'] })
    fit()
    return () => { cancelAnimationFrame(frame); resize.disconnect(); mutation.disconnect() }
  }, [ref])
}
