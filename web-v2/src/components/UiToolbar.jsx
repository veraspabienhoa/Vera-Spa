import { createPortal } from 'react-dom'
import { getLayoutTargets, subscribeLayoutTargets, registerLayoutTarget, canRelocate } from '../lib/uiLayoutTargets'
import { Children, cloneElement, forwardRef, useImperativeHandle, isValidElement, useSyncExternalStore, useEffect, useRef } from 'react'
import { getCustomization, subscribeCustomization } from '../lib/uiCustomizationStore'
export default forwardRef(function UiToolbar({ children, ...props }, forwardedRef) {
  const { items, editing } = useSyncExternalStore(subscribeCustomization, getCustomization, getCustomization)
  const config = items[props['data-ui-key']] || {}
  const ref = useRef(null)
  const slot = useRef(null)
  const targets = useSyncExternalStore(subscribeLayoutTargets, getLayoutTargets, getLayoutTargets)
  const groupKey = props['data-ui-key']
  useEffect(() => registerLayoutTarget(groupKey, ref.current, slot.current), [groupKey])
  useImperativeHandle(forwardedRef, () => ref.current)
  const raw = Children.toArray(children)
  const prepared = raw.map(child => {
    const base = child?.props?.['data-ui-key']
    if (!base || raw.filter(node => node?.props?.['data-ui-key'] === base).length < 2) return child
    let hash=2166136261
    for(const char of String(child.props.id || child.key)) hash=Math.imul(hash ^ char.charCodeAt(0),16777619)
    const key = `${base}--${(hash>>>0).toString(36)}`
    return cloneElement(child, { 'data-ui-key':key }, items[key]?.label || child.props.children)
  })
  const nodes = prepared.map((child,index)=>({child,index})).sort((a,b)=>
    (items[a.child?.props?.['data-ui-key']]?.order ?? a.index) - (items[b.child?.props?.['data-ui-key']]?.order ?? b.index)).map(item=>item.child)
  const rendered = nodes.map(child => {
    const key = child?.props?.['data-ui-key']
    if (!key || !isValidElement(child)) return child
    const node = cloneElement(child, { 'data-ui-origin': groupKey })
    const destination = targets[items[key]?.move_to]
    // A missing/hidden destination falls back to the original location.
    if (!destination || destination.element === ref.current || !canRelocate(ref.current, destination.element)) return node
    return createPortal(node, destination.slot, key)
  })
  const hasRelocation = nodes.some(child => items[child?.props?.['data-ui-key']]?.move_to)
  const canGroup = props.role !== 'tablist' && nodes.every(child=>isValidElement(child) && ['button','a'].includes(child.type))
  useEffect(()=>{
    const element=ref.current
    if(!element || config.rows == null)return undefined
    const resize=()=>element.style.setProperty('--ui-columns',String(Math.max(1,Math.min(Math.ceil(nodes.length/(config.rows||2)),Math.floor(element.clientWidth/100)||1))))
    resize()
    const observer=typeof ResizeObserver==='undefined'?null:new ResizeObserver(resize)
    observer?.observe(element)
    window.addEventListener('resize',resize)
    return ()=>{observer?.disconnect();window.removeEventListener('resize',resize)}
  },[config.rows,nodes.length])
  useEffect(() => {
    const close = event => { if (event.key === 'Escape' || (event.type === 'pointerdown' && !ref.current?.contains(event.target))) ref.current?.querySelectorAll('details[open]').forEach(menu => menu.removeAttribute('open')) }
    document.addEventListener('keydown',close); document.addEventListener('pointerdown',close)
    return () => {document.removeEventListener('keydown',close);document.removeEventListener('pointerdown',close)}
  }, [])
  return <div {...props} data-ui-dropzone={groupKey} data-ui-layout-editing={editing || undefined} ref={ref}>
    {config.mode === 'group' && canGroup && !hasRelocation && !editing && nodes.length>3 ? <>{nodes.slice(0,2)}<details className="ui-more-actions"><summary>Thao tác khác</summary><div>{nodes.slice(2)}</div></details></> : rendered}
    <div ref={slot} data-ui-drop-slot={groupKey} style={{ display: 'contents' }} />
  </div>
})
