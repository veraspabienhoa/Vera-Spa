import { BellRing, Check, LoaderCircle, Power, PowerOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { veraApi } from '../lib/api'

export default function NotificationSettingsPage({ user }) {
  const [items, setItems] = useState([])
  const [busyKey, setBusyKey] = useState('')
  const [error, setError] = useState('')
  const [savedKey, setSavedKey] = useState('')
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'

  useEffect(() => {
    let active = true
    veraApi.notificationSettings()
      .then((result) => { if (active) setItems(result.settings || []) })
      .catch((err) => { if (active) setError(err.message || 'Không tải được cấu hình thông báo.') })
    return () => { active = false }
  }, [])

  const toggle = async (item) => {
    if (!isAdmin || busyKey) return
    setBusyKey(item.key); setError(''); setSavedKey('')
    try {
      const result = await veraApi.updateNotificationSetting(item.key, !item.enabled)
      setItems((current) => current.map((entry) => entry.key === item.key ? result.setting : entry))
      setSavedKey(item.key)
      window.setTimeout(() => setSavedKey(''), 1800)
    } catch (err) {
      setError(err.message || 'Không lưu được cấu hình thông báo.')
    } finally { setBusyKey('') }
  }

  return <div className="notification-settings-page">
    <style>{`
      .notification-settings-page{display:grid;gap:14px}.notification-settings-head{display:flex;align-items:center;gap:12px}.notification-settings-head svg{color:#205a46}.notification-settings-head h2{margin:0;font-size:22px}.notification-settings-head p{margin:3px 0 0;color:#65756e;font-size:13px}.notification-settings-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.notification-setting-card{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;padding:16px;border:1px solid #ccddd5;border-radius:16px;background:#fff}.notification-setting-card h3{margin:0 0 5px;font-size:16px}.notification-setting-card p{margin:0 0 9px;color:#5f6f68;font-size:13px;line-height:1.45}.notification-setting-meta{display:flex;gap:7px;flex-wrap:wrap}.notification-setting-meta span{padding:4px 8px;border-radius:999px;background:#eef5f1;color:#345a4c;font-size:11px}.notification-switch{display:flex;align-items:center;gap:8px;min-width:112px;justify-content:center;padding:10px 12px;border:1px solid #b84a4a;border-radius:12px;background:#fff;color:#a42626;font-weight:800;cursor:pointer}.notification-switch.on{border-color:#25634c;background:#205a46;color:#fff}.notification-switch:disabled{opacity:.58;cursor:not-allowed}.notification-settings-error{padding:10px 12px;border-radius:10px;background:#fff0f0;color:#aa2727}.notification-settings-empty{padding:24px;text-align:center;color:#66756f}@media(max-width:760px){.notification-settings-grid{grid-template-columns:1fr}.notification-setting-card{padding:13px}.notification-switch{min-width:96px;padding:9px}.notification-settings-head h2{font-size:19px}}
    `}</style>
    <section className="panel notification-settings-head"><BellRing size={28}/><div><h2>QUẢN LÝ THÔNG BÁO</h2><p>Admin có thể bật hoặc tắt riêng từng loại thông báo cho toàn hệ thống.</p></div></section>
    {error && <div className="notification-settings-error" role="alert">{error}</div>}
    <section className="notification-settings-grid">
      {items.map((item) => <article className="notification-setting-card" key={item.key}>
        <div><h3>{item.label}</h3><p>{item.description}</p><div className="notification-setting-meta"><span>Người nhận: {item.audience}</span><span>Kênh: {item.channel}</span>{savedKey === item.key && <span><Check size={11}/> Đã lưu</span>}</div></div>
        <button type="button" className={`notification-switch ${item.enabled ? 'on' : ''}`} disabled={!isAdmin || Boolean(busyKey)} onClick={() => toggle(item)} aria-pressed={item.enabled}>
          {busyKey === item.key ? <LoaderCircle size={17}/> : item.enabled ? <Power size={17}/> : <PowerOff size={17}/>} {item.enabled ? 'Đang bật' : 'Đã tắt'}
        </button>
      </article>)}
    </section>
    {!items.length && !error && <div className="panel notification-settings-empty">Đang tải danh sách thông báo…</div>}
  </div>
}
