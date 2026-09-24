import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { veraApi } from '../lib/api'
import { formatVeraDateTime } from '../lib/veraDate'
import { Bell, X } from 'lucide-react'
import './NotificationInbox.css'
const requested = () => { const id = new URLSearchParams(window.location.search).get('notification') || ''; return /^[1-9][0-9]{0,18}$/.test(id) ? id : '' }
export default function NotificationInbox({ showTrigger = true }) {
  const [items, setItems] = useState([]), [open, setOpen] = useState(() => Boolean(requested()))
  const [selected, setSelected] = useState(requested), [detail, setDetail] = useState(null)
  const [error, setError] = useState(''), [retry, setRetry] = useState(0)
  const dialog = useRef(null)
  useEffect(() => {
    if (!showTrigger) return undefined
    let active = true, running = false
    const load = async () => {
      if (document.hidden || running) return
      running = true
      try { const data = await veraApi.notificationInbox(); if (active) setItems(data.notifications || []) }
      catch { /* background failure does not interrupt current work */ }
      finally { running = false }
    }
    void load(); const timer = setInterval(load, 30000)
    document.addEventListener('visibilitychange', load)
    return () => { active = false; clearInterval(timer); document.removeEventListener('visibilitychange', load) }
  }, [showTrigger])
  useEffect(() => { if (open && dialog.current && !dialog.current.open) dialog.current.showModal() }, [open])
  useEffect(() => {
    if (!selected) return undefined
    let active = true
    veraApi.notificationDetail(selected).then(result => {
      if (!active) return
      setDetail(result)
      void veraApi.readNotification(selected).then(() => { if (active) setItems(rows => rows.map(row => String(row.id) === selected ? { ...row, read_at: new Date().toISOString() } : row)) }).catch(() => {})
    }).catch(err => { if (active) setError(err.message || 'Không tải được chi tiết thông báo.') })
    return () => { active = false }
  }, [selected, retry])
  const close = () => {
    setOpen(false); setSelected(''); setDetail(null); setError('')
    const url = new URL(window.location.href); url.searchParams.delete('notification'); window.history.replaceState({}, '', url)
  }
  const unread = items.filter(item => !item.read_at).length
  return <section className="notification-inbox">
    {showTrigger && <button type="button" className="topbar-refresh-button topbar-open-tab-button notification-inbox-trigger" aria-label={unread ? `Thông báo hệ thống, ${unread} chưa đọc` : 'Thông báo hệ thống'} aria-expanded={open} onClick={() => { setSelected(''); setError(''); setOpen(true) }}><Bell size={15}/><span>Thông báo hệ thống</span>{unread > 0 && <span className="notification-unread-dot" aria-hidden="true"/>}</button>}
    {open && createPortal(<dialog ref={dialog} className="notification-dialog" aria-labelledby="notification-heading" onCancel={close} onClick={event => { if (event.target === dialog.current) close() }}>
      <header><h2 id="notification-heading">{selected ? 'Chi tiết thông báo' : 'Thông báo hệ thống'}</h2><button type="button" aria-label="Đóng thông báo" onClick={close}><X size={20}/></button></header>
      <div className="notification-dialog-content">
        {error && <div role="alert"><p>{error}</p>{selected && <button type="button" onClick={() => { setError(''); setRetry(n => n + 1) }}>Thử lại</button>}</div>}
        {selected ? detail ? <article className="notification-detail"><h3>{detail.payload?.title}</h3><p>{detail.payload?.body}</p><small>{formatVeraDateTime(detail.created_at)}</small></article> : !error && <p role="status">Đang tải chi tiết…</p> : <>
          {!items.length && <p>Chưa có thông báo.</p>}
          {items.map(item => <button type="button" className={`notification-row ${item.read_at ? '' : 'unread'}`} key={item.id} onClick={() => { setDetail(null); setError(''); setSelected(String(item.id)) }} title={`${item.payload?.title || ''} — ${item.payload?.body || ''}`}><span className="notification-row-text"><strong>{item.payload?.title}</strong><span> — {item.payload?.body}</span></span><small>{formatVeraDateTime(item.created_at)}</small></button>)}
        </>}
      </div>
      {selected && showTrigger && <footer><button type="button" onClick={() => { setSelected(''); setDetail(null); setError('') }}>Về danh sách</button></footer>}
    </dialog>, document.body)}
  </section>
}
