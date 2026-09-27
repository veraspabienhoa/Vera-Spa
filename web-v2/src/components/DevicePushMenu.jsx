import { useEffect, useState } from 'react'
import { BellRing, BellOff } from 'lucide-react'
import { readPushState, enablePushNotifications, disablePushNotifications } from '../lib/pushNotifications'
import './DevicePushMenu.css'

export default function DevicePushMenu() {
  const [state, setState] = useState({ loading: true, subscribed: false })
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  useEffect(() => {
    let active = true
    const changed = event => { if (active) setState({ ...event.detail, loading: false }) }
    window.addEventListener('vera-device-push-changed', changed)
    readPushState().then(value => { if (active) setState({ ...value, loading: false }) })
      .catch(() => { if (active) setState({ loading: false, supported: false, reason: 'Chưa đọc được cài đặt thông báo của thiết bị.' }) })
    return () => { active = false; window.removeEventListener('vera-device-push-changed', changed) }
  }, [])
  const toggle = async () => {
    if (busy) return
    setBusy(true); setError('')
    try {
      const value = await (state.subscribed ? disablePushNotifications() : enablePushNotifications())
      setState({ ...value, loading: false })
    } catch (err) { setError(err.message || 'Chưa cập nhật được thông báo của thiết bị.') }
    finally { setBusy(false) }
  }
  const enabled = Boolean(state.subscribed)
  const hint = error || state.reason || (state.permission === 'denied'
    ? 'Thông báo đang bị chặn trong Cài đặt điện thoại hoặc trình duyệt.' : '')
  return <section className="device-push-menu" aria-label="Thông báo thiết bị này">
    <button type="button" role="switch" aria-checked={enabled} aria-label="Thông báo màn hình khóa trên thiết bị này"
      className="nav-item device-push-switch" title="Thông báo trên thiết bị này" onClick={toggle}
      disabled={state.loading || busy || state.supported === false}>
      {enabled ? <BellRing size={19}/> : <BellOff size={19}/>}
      <span>Thông báo màn hình khóa</span>
      <b>{busy || state.loading ? '…' : enabled ? 'Bật' : 'Tắt'}</b>
    </button>
    {hint && <p>{hint}</p>}
    {error && <span className="sr-only" role="alert">{error}</span>}
  </section>
}
