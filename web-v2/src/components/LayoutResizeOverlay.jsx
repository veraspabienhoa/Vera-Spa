import { useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { resizeDimensions } from '../lib/layoutMetrics'

// A portal avoids inserting handles into inputs/selects or React-owned business DOM.
export default function LayoutResizeOverlay({ selected, onResize, onMetrics }) {
  const [box, setBox] = useState(null)
  const gesture = useRef(null)
  const callbacks = useRef({ onResize, onMetrics }); callbacks.current = { onResize, onMetrics }
  useLayoutEffect(() => {
    if (!selected) return undefined
    let frame
    const measure = () => {
      window.cancelAnimationFrame(frame)
      frame = window.requestAnimationFrame(() => {
        if (!selected.isConnected) { setBox(null); return }
        const r=selected.getBoundingClientRect()
        setBox({ left:r.left,top:r.top,width:r.width,height:r.height })
        callbacks.current.onMetrics()
      })
    }
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    observer?.observe(selected)
    window.addEventListener('scroll', measure, true); window.addEventListener('resize', measure)
    measure()
    return () => { window.cancelAnimationFrame(frame); observer?.disconnect(); window.removeEventListener('scroll',measure,true);window.removeEventListener('resize',measure);gesture.current=null }
  }, [selected])
  const finish = (event, cancel=false) => {
    if (!gesture.current) return
    const g=gesture.current;gesture.current=null
    if(cancel) callbacks.current.onResize(null,'cancel')
    else callbacks.current.onResize(null,'end')
    if(event.currentTarget.hasPointerCapture?.(g.pointer)) event.currentTarget.releasePointerCapture(g.pointer)
  }
  if(!box || !selected?.isConnected)return null
  return createPortal(<div className="layout-resize-overlay" style={{left:box.left,top:box.top,width:box.width,height:box.height}}>
    <button className="layout-resize-handle" type="button" aria-label="Kéo góc để đổi kích thước" title="Kéo đổi kích thước; phím mũi tên ±1 px, Shift ±10 px; Esc hủy"
      onPointerDown={event=>{event.preventDefault();event.stopPropagation();event.currentTarget.focus();const rect=selected.getBoundingClientRect();gesture.current={pointer:event.pointerId,x:event.clientX,y:event.clientY,width:rect.width,height:rect.height,parentWidth:selected.parentElement?.clientWidth || window.innerWidth};callbacks.current.onResize(null,'start');event.currentTarget.setPointerCapture?.(event.pointerId)}}
      onPointerMove={event=>{const g=gesture.current;if(!g||g.pointer!==event.pointerId)return;event.preventDefault();callbacks.current.onResize(resizeDimensions(g.width,g.height,event.clientX-g.x,event.clientY-g.y,g.parentWidth),'move')}}
      onPointerUp={event=>finish(event)} onPointerCancel={event=>finish(event,true)} onLostPointerCapture={event=>finish(event,true)}
      onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();finish(event,true);return}if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();const n=event.shiftKey?10:1,r=selected.getBoundingClientRect();callbacks.current.onResize(resizeDimensions(r.width,r.height,event.key==='ArrowLeft'?-n:event.key==='ArrowRight'?n:0,event.key==='ArrowUp'?-n:event.key==='ArrowDown'?n:0,selected.parentElement?.clientWidth || window.innerWidth),'keyboard')}}>↘</button>
  </div>,document.body)
}
