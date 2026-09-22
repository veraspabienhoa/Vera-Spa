import { useEffect, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import { formatVeraDateTime } from '../lib/veraDate'
import { Bell } from 'lucide-react'
import './NotificationInbox.css'
export default function NotificationInbox() {
  const [items,setItems]=useState([]),[open,setOpen]=useState(false),[error,setError]=useState('')
  useEffect(()=>{let active=true;const load=()=>{if(document.hidden)return;veraApi.notificationInbox().then(result=>{if(active){setItems(result.notifications || []);setError('')}}).catch(()=>{})};load();const timer=setInterval(load,30000);document.addEventListener('visibilitychange',load);return()=>{active=false;clearInterval(timer);document.removeEventListener('visibilitychange',load)}},[])
  const root=useRef(null)
  useEffect(()=>{
    if(!open)return undefined
    const close=event=>{if(event.key==='Escape'){setOpen(false);root.current?.querySelector('button')?.focus()}else if(event.type==='pointerdown'&&!root.current?.contains(event.target))setOpen(false)}
    document.addEventListener('keydown',close);document.addEventListener('pointerdown',close)
    return ()=>{document.removeEventListener('keydown',close);document.removeEventListener('pointerdown',close)}
  },[open])
  const unread=items.filter(item=>!item.read_at).length
  return <section ref={root} className="notification-inbox"><button type="button" className="topbar-refresh-button topbar-open-tab-button notification-inbox-trigger" title={unread ? `${unread} thông báo chưa đọc` : 'Thông báo hệ thống'} aria-label={unread ? `Thông báo hệ thống, ${unread} chưa đọc` : 'Thông báo hệ thống'} aria-expanded={open} onClick={()=>setOpen(!open)}><Bell size={15}/><span>Thông báo hệ thống</span>{unread>0 && <span className="notification-unread-dot" aria-hidden="true"/>}</button>
    {open && <div className="panel" aria-label="Hộp thư thông báo">{error && <p role="alert">{error}</p>}{!items.length && <p>Chưa có thông báo.</p>}{items.map(item=><article key={item.id} style={{padding:12,borderBottom:'1px solid #b5cfc0'}}><strong>{item.payload.title}</strong><p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{item.payload.body}</p><small>{formatVeraDateTime(item.created_at)}</small>{!item.read_at && <button type="button" onClick={async()=>{try{await veraApi.readNotification(item.id);setItems(current=>current.map(row=>row.id===item.id?{...row,read_at:new Date().toISOString()}:row))}catch{setError('Chưa đánh dấu được thông báo. Vui lòng thử lại.')}}}>Đánh dấu đã đọc</button>}</article>)}</div>}
  </section>
}
