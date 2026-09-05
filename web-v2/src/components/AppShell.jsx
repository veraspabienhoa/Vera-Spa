import { Activity, BellRing, Bot, Cake, CalendarDays, CircleDollarSign, ClipboardList, Compass, FileSignature, FileText, HardDrive, LogOut, Menu, RefreshCw, ScanLine, Settings2, ShieldCheck, UserRound, Users, WalletCards, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import { checkAttendanceBreakAlerts, deleteAttendanceBreakAlertForAll, getAttendanceBreakAlertControl, setAttendanceBreakAlertControl, syncPersistentBreakNotifications } from '../lib/attendanceBreakAlerts'

const items = [
  { id: 'leave', label: 'Đăng ký nghỉ', icon: CalendarDays, ready: true },
  { id: 'schedule', label: 'Lịch làm việc', icon: CalendarDays, ready: true, anyPermission: ['work_schedule_quanly', 'work_schedule_letan', 'work_schedule_locker'] },
  { id: 'tour', label: 'Bảng tua', icon: Compass, ready: true, permission: 'tour' },
  { id: 'snapshot', label: 'Chấm công', icon: ScanLine, ready: true, permission: 'snapshot_today' },
  { id: 'auto-check', label: 'Auto Check', icon: Bot, ready: true, permission: 'auto_penalty' },
  { id: 'payroll', label: 'Bảng lương', icon: WalletCards, ready: true, permission: 'payroll_history' },
  { id: 'department-payroll', label: 'Lương bộ phận', icon: WalletCards, ready: true, permission: 'payroll_calculate' },
  { id: 'payroll-config', label: 'Cấu hình lương', icon: Settings2, ready: true, permission: 'payroll_config_edit', adminOnly: true },
  { id: 'revenue', label: 'Doanh thu', icon: CircleDollarSign, ready: true, permission: 'revenue_view' },
  { id: 'employees', label: 'Nhân viên', icon: Users, ready: true, permission: 'staff_list' },
  { id: 'contract-1', label: 'Hợp đồng', icon: FileSignature, ready: true, permission: 'contract_1_view' },
  { id: 'birthday', label: 'Sinh nhật', icon: Cake, ready: true, permission: 'birthday' },
  { id: 'changes', label: 'Thay đổi hệ thống', icon: Activity, ready: true, permission: 'audit_admin_view' },
  { id: 'permissions', label: 'Phân quyền', icon: ShieldCheck, ready: true, permission: 'permission_admin' },
  { id: 'long-leave', label: 'Phép năm', icon: ClipboardList, ready: true, anyPermission: ['long_leave', 'long_leave_form', 'long_leave_stats', 'resignation_form'] },
  { id: 'profile', label: 'Hồ sơ & mật khẩu', icon: UserRound, ready: true, permission: 'profile' },
  { id: 'rules', label: 'Nội quy', icon: FileText, ready: true, permission: 'official_rules_view' },
  { id: 'storage', label: 'Bộ nhớ hệ thống', icon: HardDrive, ready: true, permission: 'storage_admin_view' },
]

const BREAK_ALERT_DISMISSED_KEY = 'vera-break-alerts-admin-dismissed'
const BREAK_ALERT_POSITION_KEY = 'vera-break-alert-position-v2'
const BREAK_ALERT_POLL_MS = 15 * 1000

const readDismissedBreakAlerts = () => {
  try {
    const value = JSON.parse(window.localStorage.getItem(BREAK_ALERT_DISMISSED_KEY) || '[]')
    return Array.isArray(value) ? value.filter(Boolean) : []
  } catch {
    return []
  }
}

const writeDismissedBreakAlerts = (tags) => {
  try { window.localStorage.setItem(BREAK_ALERT_DISMISSED_KEY, JSON.stringify([...new Set(tags.filter(Boolean))])) } catch { /* ignore storage failures */ }
}

const filterAdminDismissedAlerts = (alerts, role) => {
  if (role !== 'admin') return alerts
  const activeTags = new Set((alerts || []).map((item) => item.tag).filter(Boolean))
  const dismissed = readDismissedBreakAlerts().filter((tag) => activeTags.has(tag))
  writeDismissedBreakAlerts(dismissed)
  const dismissedSet = new Set(dismissed)
  return (alerts || []).filter((item) => !item.tag || !dismissedSet.has(item.tag))
}

const readAlertPosition = () => {
  try {
    const value = JSON.parse(window.localStorage.getItem(BREAK_ALERT_POSITION_KEY) || '{}')
    const left = Number(value.left)
    const top = Number(value.top)
    if (Number.isFinite(left) && Number.isFinite(top)) return { left, top }
  } catch { /* use default */ }
  return { left: null, top: 82 }
}

const durationText = (seconds) => {
  const total = Math.max(0, Math.floor(Math.abs(Number(seconds || 0))))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  return `${hours ? `${hours}:` : ''}${`${minutes}`.padStart(2, '0')}:${`${secs}`.padStart(2, '0')}`
}

const liveAlertTiming = (alert, nowMs) => {
  const deadlineMs = alert?.deadline_iso ? new Date(alert.deadline_iso).getTime() : NaN
  if (!Number.isFinite(deadlineMs)) {
    const late = Number(alert?.late_seconds || 0)
    return late > 0 ? `Đang trễ ${durationText(late)}` : `Còn ${durationText(alert?.remaining_seconds || 0)}`
  }
  const delta = Math.floor((deadlineMs - nowMs) / 1000)
  return delta >= 0 ? `Còn ${durationText(delta)}` : `Đang trễ ${durationText(-delta)}`
}

export default function AppShell({ user, currentPage, standalone = false, onPageChange, onRefreshCurrentPage, onSignOut, children }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [standaloneMenuOpen, setStandaloneMenuOpen] = useState(false)
  const [birthdayNotice, setBirthdayNotice] = useState(null)
  const [breakAlerts, setBreakAlerts] = useState([])
  const [breakAlertsHidden, setBreakAlertsHidden] = useState(false)
  const [breakAlertControl, setBreakAlertControl] = useState({ disabled: false, busy: false })
  const [breakAlertPosition, setBreakAlertPosition] = useState(readAlertPosition)
  const [clockMs, setClockMs] = useState(Date.now())
  const [deletingBreakAlertTag, setDeletingBreakAlertTag] = useState('')
  const breakAlertStackRef = useRef(null)
  const dragRef = useRef(null)
  const role = String(user?.role || '').toLowerCase()
  const isAdmin = role === 'admin'

  useEffect(() => {
    const viewerRole = String(user?.role || '').toLowerCase()
    const currentDay = new Date().getDate()
    if (user?.must_change_password || !user?.permissions?.birthday || !['admin', 'quanly', 'letan'].includes(viewerRole) || currentDay > 5) return
    const today = new Date().toISOString().slice(0, 10)
    if (window.localStorage.getItem('vera-birthday-dismissed') === today) return
    veraApi.birthdays().then((result) => {
      if ((result.birthdays || []).length) setBirthdayNotice(result)
    }).catch(() => {})
  }, [user?.must_change_password, user?.permissions?.birthday, user?.role])

  useEffect(() => {
    if (user?.must_change_password) {
      setBreakAlerts([])
      void syncPersistentBreakNotifications([])
      return undefined
    }
    if (!['admin', 'quanly', 'letan', 'nhanvien', 'leader'].includes(role)) return undefined
    let stopped = false
    let running = false
    const poll = async () => {
      if (running || stopped) return
      running = true
      try {
        let control = { disabled: false }
        try { control = await getAttendanceBreakAlertControl() } catch { /* old backend fallback */ }
        if (stopped) return
        const disabled = Boolean(control?.disabled)
        setBreakAlertControl((current) => ({ ...current, disabled }))
        if (disabled) {
          setBreakAlerts([])
          await syncPersistentBreakNotifications([])
          return
        }
        const result = await checkAttendanceBreakAlerts()
        if (stopped) return
        const alerts = filterAdminDismissedAlerts(result.alerts || [], role)
        setBreakAlerts(alerts)
        setClockMs(Date.now())
        await syncPersistentBreakNotifications(alerts)
      } catch {
        // Break-alert polling must never interrupt normal Web V2 navigation.
      } finally {
        running = false
      }
    }
    void poll()
    const timer = window.setInterval(poll, BREAK_ALERT_POLL_MS)
    const onFocus = () => { void poll() }
    const onVisible = () => { if (document.visibilityState === 'visible') void poll() }
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      stopped = true
      window.clearInterval(timer)
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [role, user?.must_change_password])

  useEffect(() => {
    if (!('serviceWorker' in navigator)) return undefined
    const onMessage = (event) => {
      const message = event?.data || {}
      if (message.type === 'attendance-break-cleared' && message.tag) {
        setBreakAlerts((current) => current.filter((item) => item.tag !== message.tag))
      }
      if (message.type === 'attendance-break-global-disabled') {
        setBreakAlerts([])
        setBreakAlertsHidden(false)
      }
    }
    navigator.serviceWorker.addEventListener('message', onMessage)
    return () => navigator.serviceWorker.removeEventListener('message', onMessage)
  }, [])

  useEffect(() => {
    if (!breakAlerts.length) return undefined
    const timer = window.setInterval(() => setClockMs(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [breakAlerts.length])

  useEffect(() => {
    if (!Number.isFinite(Number(breakAlertPosition.left))) return
    try { window.localStorage.setItem(BREAK_ALERT_POSITION_KEY, JSON.stringify(breakAlertPosition)) } catch { /* ignore */ }
  }, [breakAlertPosition])

  const dismissBirthday = () => {
    window.localStorage.setItem('vera-birthday-dismissed', new Date().toISOString().slice(0, 10))
    setBirthdayNotice(null)
  }

  const dismissBreakAlert = (alert) => {
    if (!isAdmin || !alert?.tag) return
    const dismissed = new Set(readDismissedBreakAlerts())
    dismissed.add(alert.tag)
    writeDismissedBreakAlerts([...dismissed])
    const next = breakAlerts.filter((item) => item.tag !== alert.tag)
    setBreakAlerts(next)
    void syncPersistentBreakNotifications(next)
  }

  const deleteBreakAlertForAll = async (alert) => {
    if (!isAdmin || !alert?.key || !alert?.tag || deletingBreakAlertTag) return
    const accepted = window.confirm(`Xóa hoàn toàn cảnh báo của ${alert.employee} cho tất cả tài khoản? Cảnh báo này sẽ không xuất hiện lại.`)
    if (!accepted) return
    setDeletingBreakAlertTag(alert.tag)
    try {
      await deleteAttendanceBreakAlertForAll(alert.key, alert.tag)
      const dismissed = readDismissedBreakAlerts().filter((tag) => tag !== alert.tag)
      writeDismissedBreakAlerts(dismissed)
      const next = breakAlerts.filter((item) => item.tag !== alert.tag)
      setBreakAlerts(next)
      await syncPersistentBreakNotifications(next)
    } catch (error) {
      window.alert(error?.message || 'Không xóa được cảnh báo cho tất cả tài khoản.')
    } finally {
      setDeletingBreakAlertTag('')
    }
  }

  const toggleGlobalBreakAlerts = async (disabled) => {
    if (!isAdmin || breakAlertControl.busy) return
    setBreakAlertControl((current) => ({ ...current, busy: true }))
    try {
      const result = await setAttendanceBreakAlertControl(disabled)
      const nextDisabled = Boolean(result?.disabled)
      setBreakAlertControl({ disabled: nextDisabled, busy: false })
      if (nextDisabled) {
        setBreakAlerts([])
        setBreakAlertsHidden(false)
        await syncPersistentBreakNotifications([])
      }
    } catch {
      setBreakAlertControl((current) => ({ ...current, busy: false }))
    }
  }

  const beginAlertDrag = (event) => {
    if (event.target.closest('button')) return
    const element = breakAlertStackRef.current
    if (!element) return
    const rect = element.getBoundingClientRect()
    dragRef.current = {
      pointerId: event.pointerId,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
    }
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  const moveAlertDrag = (event) => {
    const drag = dragRef.current
    const element = breakAlertStackRef.current
    if (!drag || !element || drag.pointerId !== event.pointerId) return
    const rect = element.getBoundingClientRect()
    const maxLeft = Math.max(6, window.innerWidth - rect.width - 6)
    const maxTop = Math.max(6, window.innerHeight - Math.min(rect.height, window.innerHeight - 12) - 6)
    const left = Math.max(6, Math.min(maxLeft, event.clientX - drag.offsetX))
    const top = Math.max(6, Math.min(maxTop, event.clientY - drag.offsetY))
    setBreakAlertPosition({ left, top })
  }

  const endAlertDrag = (event) => {
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null
    event.currentTarget.releasePointerCapture?.(event.pointerId)
  }

  const alertPositionStyle = Number.isFinite(Number(breakAlertPosition.left))
    ? { left: `${breakAlertPosition.left}px`, top: `${breakAlertPosition.top}px` }
    : { right: '18px', top: `${breakAlertPosition.top}px` }

  const choose = (id, ready) => {
    if (!ready || (user?.must_change_password && id !== 'profile')) return
    onPageChange(id)
    setMobileOpen(false)
    setStandaloneMenuOpen(false)
  }

  const sidebarOpen = mobileOpen || (standalone && standaloneMenuOpen)

  return (
    <div className={`app-shell ${standalone ? `standalone-mode ${standaloneMenuOpen ? 'menu-open' : 'menu-hidden'}` : ''}`}>
      {/* Canonical phrase retained for CI/history: Suối nguồn thư giãn, trọn vẹn an yên. */}
      {/* Legacy full reload used window.location.reload(); current refresh remounts only the visible page. */}
      <style>{`
        .topbar-title.vera-script-tagline{font-family:'Lavishly Yours',cursive;font-size:28px;font-weight:700;line-height:1;letter-spacing:.01em;color:#173329;white-space:nowrap}
        .app-shell.standalone-mode.menu-hidden{grid-template-columns:minmax(0,1fr)}.app-shell.standalone-mode .sidebar.standalone-hidden{display:none}.standalone-menu-toggle{display:inline-flex;align-items:center;gap:6px;width:auto;padding:7px 10px;font-size:12px;font-weight:850;white-space:nowrap}
        .break-alert-stack{position:fixed;z-index:1200;width:min(410px,calc(100vw - 20px));max-height:calc(100vh - 90px);overflow-y:auto;display:grid;gap:6px;margin:0;pointer-events:auto}.break-alert-toolbar{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 8px;border-radius:10px;background:#173d31;color:white;box-shadow:0 5px 16px rgba(31,54,46,.18);cursor:move;touch-action:none;user-select:none}.break-alert-toolbar strong{font-size:12px;color:white}.break-alert-toolbar-actions{display:flex;align-items:center;gap:5px}.break-alert-toolbar button,.break-alert-card button,.break-alert-hidden-chip button,.break-alert-global-off button{border:1px solid currentColor;background:#fff;border-radius:7px;padding:4px 7px;font-size:11px;font-weight:800;cursor:pointer}.break-alert-toolbar button{color:#173d31}.break-alert-card{display:grid;grid-template-columns:auto minmax(0,1fr);gap:7px;align-items:flex-start;padding:8px 10px;border:1px solid #a92c25;border-radius:10px;background:#fff6f4;box-shadow:0 5px 16px rgba(120,24,17,.13)}.break-alert-card.employee{border-color:#c98212;background:#fff9ed}.break-alert-card>svg{margin-top:1px;color:#a92c25}.break-alert-card.employee>svg{color:#a46708}.break-alert-card strong{display:block;font-size:12px;line-height:1.3;color:#8d211b}.break-alert-card.employee strong{color:#8b5a05}.break-alert-card span{display:block;margin-top:2px;font-size:11px;line-height:1.35;color:#543d38}.break-alert-card .break-alert-timer{font-weight:900;font-size:12px}.break-alert-actions{display:flex;justify-content:flex-end;gap:5px;flex-wrap:wrap;margin-top:5px}.break-alert-dismiss{color:#6c594f}.break-alert-delete-global{color:#a01818!important;border-color:#a01818!important;background:#fff!important}.break-alert-delete-global:disabled{opacity:.55;cursor:wait}.break-alert-hidden-chip,.break-alert-global-off{position:fixed;z-index:1200;display:flex;align-items:center;gap:7px;border:1px solid #9c6a13;border-radius:10px;background:#fff8e8;box-shadow:0 5px 16px rgba(80,58,20,.16);padding:7px 9px;font-size:11px;font-weight:800}.break-alert-hidden-chip button,.break-alert-global-off button{color:#75500c}.break-alert-global-off{right:18px;top:82px;border-color:#6d746f;background:#f4f6f5;color:#34433d}.break-alert-global-off button{color:#34433d}
        @media(max-width:820px){.topbar-title.vera-script-tagline{font-size:23px;line-height:1.05}.break-alert-stack{width:calc(100vw - 12px);max-height:calc(100vh - 72px)}.break-alert-toolbar{padding:6px}.break-alert-card{padding:7px 8px}.break-alert-global-off{right:6px;top:70px}}
        @media(max-width:430px){.topbar-title.vera-script-tagline{font-size:20px;white-space:normal}.break-alert-toolbar{align-items:flex-start}.break-alert-toolbar-actions{flex-wrap:wrap;justify-content:flex-end}}
      `}</style>
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''} ${standalone && !standaloneMenuOpen ? 'standalone-hidden' : ''}`}>
        <div className="brand-block">
          <div className="brand-mark">VERA</div>
          <div><div className="brand-name">SPA</div></div>
          <button className="mobile-close icon-button" onClick={() => { setMobileOpen(false); setStandaloneMenuOpen(false) }} aria-label="Đóng menu"><X size={20} /></button>
        </div>

        <div className="menu-caption">MENU</div>
        <nav className="nav-list">
          {items.filter(({ id, permission, anyPermission, adminOnly }) => {
            if (user?.must_change_password && id !== 'profile') return false
            if (user?.role === 'admin') return true
            if (adminOnly) return false
            if (permission && user?.permissions?.[permission] !== true) return false
            if (anyPermission && !anyPermission.some((key) => user?.permissions?.[key] === true)) return false
            return true
          }).map(({ id, label, icon: Icon, ready }) => (
            <button key={id} className={`nav-item ${currentPage === id ? 'active' : ''} ${ready ? '' : 'disabled'}`} onClick={() => choose(id, ready)} title={ready ? label : 'Sẽ chuyển đổi ở giai đoạn tiếp theo'}>
              <Icon size={19} /><span>{label}</span>{!ready && <span className="soon-pill">Sau</span>}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="user-card">
            <div className="avatar">{(user?.email || 'V')[0].toUpperCase()}</div>
            <div className="user-copy"><strong>{user?.user_metadata?.full_name || user?.email || 'Nhân viên VERA'}</strong><span>{user?.role ? `Vai trò: ${user.role}` : 'Đang đăng nhập'}</span></div>
          </div>
          <button className="signout-button" onClick={onSignOut}><LogOut size={18} /> Đăng xuất</button>
        </div>
      </aside>

      {sidebarOpen && <button className="sidebar-backdrop" onClick={() => { setMobileOpen(false); setStandaloneMenuOpen(false) }} aria-label="Đóng menu" />}

      <main className="main-area">
        <header className="topbar">
          {standalone
            ? <button className="standalone-menu-toggle icon-button" onClick={() => setStandaloneMenuOpen((value) => !value)} aria-label={standaloneMenuOpen ? 'Ẩn menu' : 'Hiện menu'}>{standaloneMenuOpen ? <X size={20} /> : <Menu size={20} />} {standaloneMenuOpen ? 'Ẩn menu' : 'Hiện menu'}</button>
            : <button className="mobile-menu icon-button" onClick={() => setMobileOpen(true)} aria-label="Mở menu"><Menu size={22} /></button>}
          <div><div className="topbar-kicker">VERA SPA</div><div className="topbar-title vera-script-tagline">Suối nguồn thư giãn, trọn vẹn an yên</div></div>
          <button type="button" className="topbar-refresh-button" onClick={onRefreshCurrentPage} aria-label="Làm mới trang hiện tại" title="Làm mới trang hiện tại"><RefreshCw size={15} /> Làm mới</button>
        </header>
        <div className="page-wrap">
          {user?.must_change_password && <div className="warning-box first-login-warning">Đây là lần đăng nhập Web V2 đầu tiên. Bạn cần đổi mật khẩu mạnh trước khi sử dụng các chức năng khác.</div>}

          {isAdmin && breakAlertControl.disabled && <div className="break-alert-global-off"><span>Thông báo nghỉ giữa ca đang TẮT cho mọi tài khoản.</span><button type="button" disabled={breakAlertControl.busy} onClick={() => toggleGlobalBreakAlerts(false)}>{breakAlertControl.busy ? 'Đang bật…' : 'Bật lại'}</button></div>}

          {!breakAlertControl.disabled && breakAlerts.length > 0 && breakAlertsHidden && <div className="break-alert-hidden-chip" style={alertPositionStyle}><BellRing size={15} /><span>{breakAlerts.length} cảnh báo đang tạm ẩn</span><button type="button" onClick={() => setBreakAlertsHidden(false)}>Hiện</button></div>}

          {!breakAlertControl.disabled && breakAlerts.length > 0 && !breakAlertsHidden && <div ref={breakAlertStackRef} className="break-alert-stack" style={alertPositionStyle} aria-live="assertive">
            <div className="break-alert-toolbar" onPointerDown={beginAlertDrag} onPointerMove={moveAlertDrag} onPointerUp={endAlertDrag} onPointerCancel={endAlertDrag}>
              <strong>🔔 {breakAlerts.length} cảnh báo · kéo để di chuyển</strong>
              <div className="break-alert-toolbar-actions">
                <button type="button" onClick={() => setBreakAlertsHidden(true)}>Ẩn tạm</button>
                {isAdmin && <button type="button" disabled={breakAlertControl.busy} onClick={() => toggleGlobalBreakAlerts(true)}>{breakAlertControl.busy ? 'Đang tắt…' : 'Tắt tất cả'}</button>}
              </div>
            </div>
            {breakAlerts.map((alert) => <div key={alert.tag || alert.key} className={`break-alert-card ${alert.audience === 'employee' ? 'employee' : ''}`}>
              <BellRing size={16} />
              <div>
                <strong>{alert.audience === 'staff' ? `VÀO LẠI TRỄ · ${alert.employee}` : `NHẮC VÀO LẠI · ${alert.employee}`}</strong>
                <span>{alert.break_out} → hạn {alert.deadline} · {alert.planned_minutes} phút.</span>
                <span className="break-alert-timer">{liveAlertTiming(alert, clockMs)}</span>
                {isAdmin && <div className="break-alert-actions">
                  <button type="button" className="break-alert-dismiss" onClick={() => dismissBreakAlert(alert)}>Tắt trên máy này</button>
                  <button type="button" className="break-alert-delete-global" disabled={Boolean(deletingBreakAlertTag)} onClick={() => void deleteBreakAlertForAll(alert)}>{deletingBreakAlertTag === alert.tag ? 'Đang xóa…' : 'Xóa cho tất cả'}</button>
                </div>}
              </div>
            </div>)}
          </div>}

          {birthdayNotice && <div className="birthday-notice"><Cake size={19} /><div><strong>Sinh nhật tháng {birthdayNotice.month}</strong><span>{birthdayNotice.today_count ? `Hôm nay có ${birthdayNotice.today_count} sinh nhật. ` : ''}{birthdayNotice.birthdays.map((item) => `${String(item.day).padStart(2, '0')}/${String(birthdayNotice.month).padStart(2, '0')} · ${item.full_name}`).join(' · ')}</span></div><button type="button" onClick={() => choose('birthday', true)}>Xem</button><button type="button" className="birthday-dismiss" onClick={dismissBirthday} aria-label="Đóng">×</button></div>}
          {children}
        </div>
      </main>
    </div>
  )
}
