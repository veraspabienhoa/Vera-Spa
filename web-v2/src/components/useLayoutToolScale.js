import { useEffect, useState } from 'react'
const KEY = 'vera-layout-tool-scale-v1'
export default function useLayoutToolScale() {
  const [value, setValue] = useState(() => {
    try {
      const stored = Number(localStorage.getItem(KEY))
      return Number.isFinite(stored) && stored >= 70 && stored <= 110 ? stored : 100
    } catch { return 100 }
  })
  useEffect(() => { try { localStorage.setItem(KEY, String(value)) } catch { /* Optional browser preference. */ } }, [value])
  return { value, setValue, style: {
    '--layout-tool-font': `${Math.max(11, 13 * value / 100)}px`,
    '--layout-tool-height': `${Math.max(28, 40 * value / 100)}px`,
    '--layout-tool-padding-y': `${8 * value / 100}px`,
    '--layout-tool-padding-x': `${10 * value / 100}px`,
    '--layout-tool-gap': `${8 * value / 100}px`,
  } }
}
