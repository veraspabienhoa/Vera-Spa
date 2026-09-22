import { useEffect, useRef, useState } from 'react'
const KEY='vera-layout-panel-frame-v1'
const fit = frame => {
 const width=Math.max(240,Math.min(frame.width,window.innerWidth-16)),height=Math.max(Math.min(340,window.innerHeight-16),Math.min(frame.height,window.innerHeight-16))
 return {width,height,left:Math.max(8,Math.min(frame.left,window.innerWidth-width-8)),top:Math.max(8,Math.min(frame.top,window.innerHeight-height-8))}
}
export default function useLayoutPanelFrame() {
 const [frame,setFrame]=useState(()=>{try{const item=JSON.parse(localStorage.getItem(KEY));return item && ['width','height','left','top'].every(k=>Number.isFinite(item[k]))?fit(item):null}catch{return null}})
 const gesture=useRef(null)
 useEffect(()=>{try{if(frame)localStorage.setItem(KEY,JSON.stringify(frame));else localStorage.removeItem(KEY)}catch{/* Private browsing may block local preferences. */}},[frame])
 useEffect(()=>{const resize=()=>setFrame(current=>current?fit(current):null);window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize)},[])
 const begin=(event,mode)=>{if(event.button!==0)return;event.preventDefault();event.currentTarget.focus();const rect=event.currentTarget.closest('.layout-designer').getBoundingClientRect();gesture.current={mode,x:event.clientX,y:event.clientY,original:frame,start:{width:rect.width,height:rect.height,left:rect.left,top:rect.top},pointer:event.pointerId};event.currentTarget.setPointerCapture?.(event.pointerId)}
 const move=event=>{const g=gesture.current;if(!g || g.pointer!==event.pointerId)return;const dx=event.clientX-g.x,dy=event.clientY-g.y;setFrame(fit(g.mode==='move'?{...g.start,left:g.start.left+dx,top:g.start.top+dy}:{...g.start,width:g.start.width+dx,height:g.start.height+dy}))}
 const end=(event,cancel=false)=>{const g=gesture.current;if(!g)return;gesture.current=null;if(cancel)setFrame(g.original);if(event.currentTarget.hasPointerCapture?.(g.pointer))event.currentTarget.releasePointerCapture(g.pointer)}
 const handlers=mode=>({onPointerDown:e=>begin(e,mode),onPointerMove:move,onPointerUp:e=>end(e),onPointerCancel:e=>end(e,true),onLostPointerCapture:e=>end(e,true),onKeyDown:e=>{if(e.key==='Escape'){end(e,true);return}if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();const r=e.currentTarget.closest('.layout-designer').getBoundingClientRect(),n=e.shiftKey?20:5,dx=e.key==='ArrowLeft'?-n:e.key==='ArrowRight'?n:0,dy=e.key==='ArrowUp'?-n:e.key==='ArrowDown'?n:0;setFrame(fit(mode==='move'?{left:r.left+dx,top:r.top+dy,width:r.width,height:r.height}:{left:r.left,top:r.top,width:r.width+dx,height:r.height+dy}))}})
 return {style:frame?{...frame,bottom:'auto',maxHeight:'calc(100dvh - 16px)',maxWidth:'calc(100vw - 16px)'}:undefined,move:handlers('move'),resize:handlers('resize'),reset:()=>{gesture.current=null;setFrame(null)}}
}
