import NotificationModal from './NotificationModal'
import TrainingNoticeDetail from './TrainingNoticeDetail'
import { canSeeMissingCheckins } from '../lib/missingCheckinAudience'
import UiCustomText from './UiCustomText'
import { useEffect, useRef, useState } from 'react'
import { BellRing, CheckCircle2, CircleAlert, Info, X } from 'lucide-react'
import { veraApi } from '../lib/api'
import { createVisiblePoller } from '../lib/visiblePoller'
import { subscribeNotificationFeed, refreshNotificationFeed } from '../lib/notificationFeed'


export default function PopupNotifications({ user }) {
  const [items, setItems] = useState([])
  const [trainingDetail, setTrainingDetail] = useState(null)
  const settings = useRef({})
  const seenTraining = useRef(new Set())
  const seenRouted = useRef(new Set())
  useEffect(() => {
    let active = true
    const loadTrainingNotifications = () => veraApi.trainingNotifications('popup').then((result) => {
      if (!active) return
      if (settings.current.training_completed?.enabled === false || settings.current.training_completed?.channel_enabled?.popup === false) return
      const fresh = (result.notifications || []).filter(item => !item.is_read && !seenTraining.current.has(item.id))
      fresh.forEach(item => seenTraining.current.add(item.id))
      if (fresh.length) setItems(current => [...current, ...fresh.map(item => ({
        id: `training-${item.id}`, notificationId: item.id, message: `${item.title} · ${item.body}`,
        type: 'info', category: 'training_completed', persistent: true,
      }))])
    }).catch(() => {})
    const trainingPoller = createVisiblePoller(loadTrainingNotifications, { interval: 60000 })
    const unsubscribeFeed = subscribeNotificationFeed(result => {
      if (!active) return
      settings.current = Object.fromEntries((result.settings || []).map((item) => [item.key, item]))
      const fresh = (result.popup || []).filter(item => !seenRouted.current.has(item.id)
        && item.payload?.kind !== 'live_tour_booking'
        && !(canSeeMissingCheckins(user?.role) && item.payload?.kind === 'missing-scheduled-checkin'))
      fresh.forEach(item => seenRouted.current.add(item.id))
      if (fresh.length) setItems(current => [...current, ...fresh.map(item => ({
        id: `route-${item.id}`, routeId: item.id, message: `${item.payload?.title || 'Thông báo'} · ${item.payload?.body || ''}`,
        type:'info', category:'routed_popup', persistent:true,
      }))])
    })
    const onSettingsChanged = (event) => {
      const item = event?.detail
      if (item?.key) settings.current = { ...settings.current, [item.key]: item }
      else void refreshNotificationFeed()
    }
    window.addEventListener('vera-notification-settings-changed', onSettingsChanged)
    const routeFeedback = event => {
      const category = event.detail?.category
      if (category && settings.current[category]?.has_rules) void veraApi.routeLocalNotification(category).catch(() => {})
    }
    window.addEventListener('vera-system-feedback', routeFeedback)
    return () => {
      active = false
      trainingPoller.stop()
      unsubscribeFeed()
      window.removeEventListener('vera-system-feedback', routeFeedback)
      window.removeEventListener('vera-notification-settings-changed', onSettingsChanged)
    }
  }, [user?.role])
  const openTrainingDetail = async (item) => {
    if (!item.notificationId) return
    try {
      setTrainingDetail(await veraApi.trainingNotificationDetail(item.notificationId))
      setItems(current => current.filter(row => row.id !== item.id))
    } catch { /* Leave the notification available to retry. */ }
  }
  const dismiss = item => {
    setItems(current => current.filter(row => row.id !== item.id))
    if (item.routeId) void veraApi.readNotification(item.routeId).catch(() => {})
  }
  if (!items.length && !trainingDetail) return null
  return <>
    {!!items.length && !trainingDetail && <NotificationModal key={items[0].id} onClose={() => dismiss(items[0])}><div className="popup-notification-stack" aria-label="Thông báo trên màn hình">{items.slice(0, 1).map(item => <div key={item.id} className={`popup-notification ${item.type}`} role="status">
      {item.notificationId ? <BellRing size={19}/> : item.type === 'success' ? <CheckCircle2 size={19}/> : item.type === 'error' ? <CircleAlert size={19}/> : <Info size={19}/>} {item.notificationId ? <button data-ui-key="u-0455df928cb2" type="button" className="popup-notification-open" onClick={() => openTrainingDetail(item)}>{item.message}<small>Bấm để xem chi tiết</small></button> : <span>{item.message}</span>}<button data-ui-key="u-733434ac2d70" type="button" aria-label="Đóng thông báo" onClick={() => dismiss(item)}><X size={16}/></button>
    </div>)}</div></NotificationModal>}
    {trainingDetail && <TrainingNoticeDetail notice={trainingDetail} onClose={() => setTrainingDetail(null)} />}
  </>
}
