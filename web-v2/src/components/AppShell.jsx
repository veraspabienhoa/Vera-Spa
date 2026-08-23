import { CalendarDays, ClipboardList, FileText, LogOut, Menu, ShieldCheck, Users, X } from 'lucide-react'
import { useState } from 'react'

const items = [
  { id: 'leave', label: 'Đăng ký nghỉ', icon: CalendarDays, ready: true },
  { id: 'leave-manage', label: 'Quản lý lịch nghỉ', icon: ClipboardList },
  { id: 'employees', label: 'Nhân viên', icon: Users },
  { id: 'rules', label: 'Nội quy', icon: FileText },
  { id: 'permissions', label: 'Phân quyền', icon: ShieldCheck },
]

export default function AppShell({ user, currentPage, onPageChange, onSignOut, children }) {
  const [mobileOpen, setMobileOpen] = useState(false)

  const choose = (id, ready) => {
    if (!ready) return
    onPageChange(id)
    setMobileOpen(false)
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
        <div className="brand-block">
          <div className="brand-mark">V</div>
          <div>
            <div className="brand-name">VERA SPA</div>
            <div className="brand-subtitle">Web V2</div>
          </div>
          <button className="mobile-close icon-button" onClick={() => setMobileOpen(false)} aria-label="Đóng menu">
            <X size={20} />
          </button>
        </div>

        <div className="menu-caption">MENU</div>
        <nav className="nav-list">
          {items.map(({ id, label, icon: Icon, ready }) => (
            <button
              key={id}
              className={`nav-item ${currentPage === id ? 'active' : ''} ${ready ? '' : 'disabled'}`}
              onClick={() => choose(id, ready)}
              title={ready ? label : 'Sẽ chuyển sang Web V2 ở giai đoạn tiếp theo'}
            >
              <Icon size={19} />
              <span>{label}</span>
              {!ready && <span className="soon-pill">Sau</span>}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="user-card">
            <div className="avatar">{(user?.email || 'V')[0].toUpperCase()}</div>
            <div className="user-copy">
              <strong>{user?.user_metadata?.full_name || user?.email || 'Nhân viên VERA'}</strong>
              <span>{user?.role ? `Vai trò: ${user.role}` : 'Đang đăng nhập'}</span>
            </div>
          </div>
          <button className="signout-button" onClick={onSignOut}><LogOut size={18} /> Đăng xuất</button>
        </div>
      </aside>

      {mobileOpen && <button className="sidebar-backdrop" onClick={() => setMobileOpen(false)} aria-label="Đóng menu" />}

      <main className="main-area">
        <header className="topbar">
          <button className="mobile-menu icon-button" onClick={() => setMobileOpen(true)} aria-label="Mở menu">
            <Menu size={22} />
          </button>
          <div>
            <div className="topbar-kicker">VERA SPA</div>
            <div className="topbar-title">Quản lý vận hành</div>
          </div>
          <div className="environment-badge">V2 Pilot</div>
        </header>
        <div className="page-wrap">{children}</div>
      </main>
    </div>
  )
}
