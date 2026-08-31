import { Activity, Bot, Cake, CalendarDays, CircleDollarSign, ClipboardList, Compass, FileText, HardDrive, LogOut, Menu, RefreshCw, ScanLine, ShieldCheck, UserRound, Users, WalletCards, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { veraApi } from '../lib/api'

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

export default function AppShell({ user, currentPage, onPageChange, onRefreshCurrentPage, onSignOut, children }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [birthdayNotice, setBirthdayNotice] = useState(null)

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
        @media(max-width:820px){.topbar-title.vera-script-tagline{font-size:23px;line-height:1.05}}
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
          {birthdayNotice && <div className="birthday-notice"><Cake size={19} /><div><strong>Sinh nhật tháng {birthdayNotice.month}</strong><span>{birthdayNotice.today_count ? `Hôm nay có ${birthdayNotice.today_count} sinh nhật. ` : ''}{birthdayNotice.birthdays.map((item) => `${String(item.day).padStart(2, '0')}/${String(birthdayNotice.month).padStart(2, '0')} · ${item.full_name}`).join(' · ')}</span></div><button type="button" onClick={() => choose('birthday', true)}>Xem</button><button type="button" className="birthday-dismiss" onClick={dismissBirthday} aria-label="Đóng">×</button></div>}
          {children}
        </div>
      </main>
    </div>
  )
}
