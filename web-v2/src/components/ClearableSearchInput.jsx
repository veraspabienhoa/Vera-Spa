import { forwardRef, useRef } from 'react'
import './ClearableSearchInput.css'

const ClearableSearchInput = forwardRef(function ClearableSearchInput({ onClear, ...props }, forwardedRef) {
  const input = useRef(null)
  const clear = () => {
    const node = input.current
    if (!node) return
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(node, '')
    node.dispatchEvent(new node.ownerDocument.defaultView.Event('input', { bubbles: true }))
    node.focus()
    onClear?.()
  }
  return <span className="clearable-search-input"><input {...props} ref={node => {
    input.current = node
    if (typeof forwardedRef === 'function') forwardedRef(node)
    else if (forwardedRef) forwardedRef.current = node
  }}/>{Boolean(props.value) && <button type="button" className="search-clear-button" disabled={props.disabled || props.readOnly} aria-label={`Clear ${props['aria-label'] || props.placeholder || ''}`} onClick={clear}>Clear</button>}</span>
})

export default ClearableSearchInput
