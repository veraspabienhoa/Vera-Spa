import StableFeedback from './StableFeedback'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { veraApi } from '../lib/api'
import { subscribeNotificationFeed } from '../lib/notificationFeed'
import { formatVeraDateTime } from '../lib/veraDate'
import { Bell, Check, X } from 'lucide-react'
import './NotificationInbox.css'
const requested = () => { const id = new URLSearchParams(window.location.search).get('notification') || ''; return /^[1-9][0-9]{0,18}$/.test(id) ? id : '' }
const cleanTitle = title => String(title || 'Thông báo').replace(/^VERA SPA(?:\s*[·:–-]\s*|\s+)/i, '') || 'Thông báo'
export default function NotificationInbox({ showTrigger = true }) {
  const [items, setItems] = useState([]), [open, setOpen] = useState(() => Boolean(requested()))
  const [selected, setSelected] = useState(requested), [detail, setDetail] = useState(null)
  const [error, setError] = useState(''), [retry, setRetry] = useState(0)
  const [marking, setMarking] = useState('')
  const dialog = useRef(null)
  useEffect(() => {
    if (!showTrigger) return undefined
    return subscribeNotificationFeed(data => setItems(data.inbox || []))
  }, [showTrigger])
  useEffect(() => { if (open && dialog.current && !dialog.current.open) dialog.current.showModal() }, [open])
  useEffect(() => {
    if (!selected) return undefined
    let active = true
    veraApi.notificationDetail(selected).then(result => {
      if (!active) return
      setDetail(result)
    }).catch(err => { if (active) setError(err.message || 'Không tải được chi tiết thông báo.') })
    return () => { active = false }
  }, [selected, retry])
  const close = () => {
    setOpen(false); setSelected(''); setDetail(null); setError('')
    const url = new URL(window.location.href); url.searchParams.delete('notification'); window.history.replaceState({}, '', url)
  }
  const markViewed = async id => {
    setMarking(String(id)); setError('')
    try {
      await veraApi.readNotification(id)
      setItems(rows => rows.filter(row => String(row.id) !== String(id)))
      if (selected === String(id)) { setSelected(''); setDetail(null) }
    } catch (err) { setError(err.message || 'Chưa đánh dấu được thông báo. Vui lòng thử lại.') }
    finally { setMarking('') }
  }
  const unread = items.filter(item => !item.read_at).length
  return <section className="notification-inbox">
    {showTrigger && <button type="button" className="topbar-refresh-button topbar-open-tab-button notification-inbox-trigger" aria-label={unread ? `Thông báo hệ thống, ${unread} chưa đọc` : 'Thông báo hệ thống'} aria-expanded={open} onClick={() => { setSelected(''); setError(''); setOpen(true) }}><Bell size={15}/><span>Thông báo hệ thống</span>{unread > 0 && <span className="notification-unread-dot" aria-hidden="true"/>}</button>}
    {open && createPortal(<dialog ref={dialog} className="notification-dialog" aria-labelledby="notification-heading" onCancel={close} onClick={event => { if (event.target === dialog.current) close() }}>
      <header><div className="notification-heading"><span className="notification-heading-icon"><Bell size={20}/></span><div><small>TRUNG TÂM THÔNG BÁO</small><h2 id="notification-heading">{selected ? 'Chi tiết thông báo' : 'Thông báo hệ thống'}</h2></div></div><button type="button" aria-label="Đóng thông báo" onClick={close}><X size={20}/></button></header>
      <div className="notification-dialog-content">
        <StableFeedback>{error && <div role="alert"><p>{error}</p>{selected && <button type="button" onClick={() => { setError(''); setRetry(n => n + 1) }}>Thử lại</button>}</div>}</StableFeedback>
        {selected ? detail ? <article className="notification-detail"><h3>{cleanTitle(detail.payload?.title)}</h3><p>{detail.payload?.body}</p><small>{formatVeraDateTime(detail.created_at)}</small>{showTrigger && <button type="button" className="notification-viewed" disabled={Boolean(marking)} onClick={() => markViewed(detail.id)}><Check size={16}/> Đã xem</button>}</article> : !error && <p role="status">Đang tải chi tiết…</p> : <>
          {!items.length && <p>Chưa có thông báo.</p>}
          {items.map(item => <div className="notification-entry" key={item.id}><button type="button" className="notification-row unread" onClick={() => { setDetail(null); setError(''); setSelected(String(item.id)) }} title={`${cleanTitle(item.payload?.title)} — ${item.payload?.body || ''}`}><span className="notification-row-text"><strong>{cleanTitle(item.payload?.title)}</strong><span> — {item.payload?.body}</span></span><small>{formatVeraDateTime(item.created_at)}</small></button><button type="button" className="notification-viewed" disabled={marking===String(item.id)} onClick={() => markViewed(item.id)} aria-label={`Đã xem ${cleanTitle(item.payload?.title)}`}><Check size={15}/><span>Đã xem</span></button></div>)}
        </>}
      </div>
      {selected && showTrigger && <footer><button type="button" onClick={() => { setSelected(''); setDetail(null); setError('') }}>Về danh sách</button></footer>}
    </dialog>, document.body)}
  </section>
}
