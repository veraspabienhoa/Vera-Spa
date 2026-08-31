import { Activity, BellRing, Bot, Cake, CalendarDays, CircleDollarSign, ClipboardList, Compass, FileText, HardDrive, LogOut, Menu, RefreshCw, ScanLine, ShieldCheck, UserRound, Users, WalletCards, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { veraApi } from '../lib/api'
import { checkAttendanceBreakAlerts, syncPersistentBreakNotifications } from '../lib/attendanceBreakAlerts'

const items = [
  { id: 'leave', label: 'Đăng ký nghỉ', icon: CalendarDays, ready: true },
  { id: 'schedule', label: 'Lịch làm việc', icon: CalendarDays, ready: true, anyPermission: ['work_schedule_quanly', 'work_schedule_letan', 'work_schedule_locker'] },
  { id: 'tour', label: 'Bảng tua', icon: Compass, ready: true, permission: 'tour' },
  { id: 'snapshot', label: 'Chấm công', icon: ScanLine, ready: true, permission: 'snapshot_today' },
  { id: 'auto-check', label: 'Auto Check', icon: Bot, ready: true, permission: 'auto_penalty' },
  { id: 'payroll', label: 'Bảng lương', icon: WalletCards, ready: true, permission: 'payroll_history' },
  { id: 'revenue', label: 'Doanh thu', icon: CircleDollarSign, ready: true, permission: 'revenue_view' },
  { id: 'employees', label: 'Nhân viên', icon: Users, ready: true, permission: 'staff_list' },
  { id: 'birthday', label: 'Sinh nhật', icon: Cake, ready: true, permission: 'birthday' },
  { id: 'changes', label: 'Thay đổi hệ thống', icon: Activity, ready: true, permission: 'audit_admin_view' },
  { id: 'permissions', label: 'Phân quyền', icon: ShieldCheck, ready: true, permission: 'permission_admin' },
  { id: 'long-leave', label: 'Phép năm', icon: ClipboardList, ready: true, anyPermission: ['long_leave', 'long_leave_form', 'long_leave_stats', 'resignation_form'] },
  { id: 'profile', label: 'Hồ sơ & mật khẩu', icon: UserRound, ready: true, permission: 'profile' },
  { id: 'rules', label: 'Nội quy', icon: FileText, ready: true, permission: 'official_rules_view' },
  { id: 'storage', label: 'Bộ nhớ hệ thống', icon: HardDrive, ready: true, permission: 'storage_admin_view' },
]

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

export default function AppShell({ user, currentPage, onPageChange, onRefreshCurrentPage, onSignOut, children }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [birthdayNotice, setBirthdayNotice] = useState(null)
  const [breakAlerts, setBreakAlerts] = useState([])
  const [clockMs, setClockMs] = useState(Date.now())

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
    const role = String(user?.role || '').toLowerCase()
    if (!['admin', 'quanly', 'letan', 'nhanvien', 'leader'].includes(role)) return undefined
    let stopped = false
    let running = false
    const poll = async () => {
      if (running || stopped) return
      running = true
      try {
        const result = await checkAttendanceBreakAlerts()
        if (stopped) return
        const alerts = result.alerts || []
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
    const timer = window.setInterval(poll, 15000)
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
  }, [user?.must_change_password, user?.role])

  useEffect(() => {
    if (!breakAlerts.length) return undefined
    const timer = window.setInterval(() => setClockMs(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [breakAlerts.length])

  const dismissBirthday = () => {
    window.localStorage.setItem('vera-birthday-dismissed', new Date().toISOString().slice(0, 10))
    setBirthdayNotice(null)
  }

  const choose = (id, ready) => {
    if (!ready || (user?.must_change_password && id !== 'profile')) return
    onPageChange(id)
    setMobileOpen(false)
  }

  return (
    <div className="app-shell">
      {/* Canonical phrase retained for CI/history: Suối nguồn thư giãn, trọn vẹn an yên. */}
      {/* Legacy full reload used window.location.reload(); current refresh remounts only the visible page. */}
      <style>{`
        .topbar-title.vera-script-tagline{font-family:'Lavishly Yours',cursive;font-size:28px;font-weight:700;line-height:1;letter-spacing:.01em;color:#173329;white-space:nowrap}
        .break-alert-stack{position:fixed;top:82px;right:18px;z-index:1200;width:min(560px,calc(100vw - 36px));max-height:calc(100vh - 100px);overflow-y:auto;display:grid;gap:9px;margin:0;pointer-events:auto}.break-alert-card{display:grid;grid-template-columns:auto minmax(0,1fr);gap:11px;align-items:flex-start;padding:13px 15px;border:2px solid #a92c25;border-radius:14px;background:#fff3f1;box-shadow:0 8px 24px rgba(120,24,17,.18)}.break-alert-card.employee{border-color:#c98212;background:#fff8e8}.break-alert-card svg{margin-top:2px;color:#a92c25}.break-alert-card.employee svg{color:#a46708}.break-alert-card strong{display:block;font-size:15px;color:#8d211b}.break-alert-card.employee strong{color:#8b5a05}.break-alert-card span{display:block;margin-top:3px;font-size:13px;line-height:1.45;color:#543d38}.break-alert-card .break-alert-timer{font-weight:900;font-size:14px}.break-alert-card .break-alert-source{font-size:12px;color:#79615c}
        @media(max-width:820px){.topbar-title.vera-script-tagline{font-size:23px;line-height:1.05}.break-alert-stack{top:70px;right:8px;width:calc(100vw - 16px);max-height:calc(100vh - 82px)}.break-alert-card{padding:12px}}
        @media(max-width:430px){.topbar-title.vera-script-tagline{font-size:20px;white-space:normal}}
      `}</style>
      <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
        <div className="brand-block">
          <div className="brand-mark">VERA</div>
          <div><div className="brand-name">SPA</div></div>
          <button className="mobile-close icon-button" onClick={() => setMobileOpen(false)} aria-label="Đóng menu"><X size={20} /></button>
        </div>

        <div className="menu-caption">MENU</div>
        <nav className="nav-list">
          {items.filter(({ id, permission, anyPermission }) => {
            if (user?.must_change_password && id !== 'profile') return false
            if (user?.role === 'admin') return true
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

      {mobileOpen && <button className="sidebar-backdrop" onClick={() => setMobileOpen(false)} aria-label="Đóng menu" />}

      <main className="main-area">
        <header className="topbar">
          <button className="mobile-menu icon-button" onClick={() => setMobileOpen(true)} aria-label="Mở menu"><Menu size={22} /></button>
          <div><div className="topbar-kicker">VERA SPA</div><div className="topbar-title vera-script-tagline">Suối nguồn thư giãn, trọn vẹn an yên</div></div>
          <button type="button" className="topbar-refresh-button" onClick={onRefreshCurrentPage} aria-label="Làm mới trang hiện tại" title="Làm mới trang hiện tại"><RefreshCw size={15} /> Làm mới</button>
        </header>
        <div className="page-wrap">
          {user?.must_change_password && <div className="warning-box first-login-warning">Đây là lần đăng nhập Web V2 đầu tiên. Bạn cần đổi mật khẩu mạnh trước khi sử dụng các chức năng khác.</div>}
          {breakAlerts.length > 0 && <div className="break-alert-stack" aria-live="assertive">
            {breakAlerts.map((alert) => <div key={alert.tag || alert.key} className={`break-alert-card ${alert.audience === 'employee' ? 'employee' : ''}`}>
              <BellRing size={22} />
              <div>
                <strong>{alert.audience === 'staff' ? `NHÂN VIÊN VÀO LẠI TRỄ · ${alert.employee}` : `NHẮC VÀO LẠI SAU NGHỈ · ${alert.employee}`}</strong>
                <span>Nghỉ lúc {alert.break_out} · phải FaceID vào lại lúc {alert.deadline} · {alert.planned_minutes} phút nghỉ.</span>
                <span className="break-alert-timer">{liveAlertTiming(alert, clockMs)}</span>
                <span className="break-alert-source">Nguồn: {alert.source}. Thông báo này tự biến mất khi hệ thống ghi nhận FaceID vào lại.</span>
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