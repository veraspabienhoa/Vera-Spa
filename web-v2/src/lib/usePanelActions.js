import { useLayoutEffect, useMemo, useRef } from 'react'

// Event props stay stable across timer ticks while using the latest committed state.
export default function usePanelActions(actions) {
  const latest = useRef(actions)
  useLayoutEffect(() => { latest.current = actions })
  const names = Object.keys(actions).join(',')
  return useMemo(() => Object.fromEntries(names.split(',').map(name => [name, (...args) => latest.current[name](...args)])), [names])
}
