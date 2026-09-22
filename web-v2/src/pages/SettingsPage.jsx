import { useEffect, useState } from 'react'
import SpaManagementPage from './SpaManagementPage'
import KtvShiftSettingsPanel from './KtvShiftSettingsPanel'
import ShiftBreakSettingsPanel from './ShiftBreakSettingsPanel'
import DepartmentShiftSettingsPanel from './DepartmentShiftSettingsPanel'
import './SpaManagementPage.css'
import './SettingsPage.css'

export default function SettingsPage({ user, initialTab, appearance, notifications, permissionSettings }) {
  const admin = user?.role === 'admin'
  const permissions = user?.permissions || {}
  const catalog = admin || permissions.live_tour_admin === true
  const ktv = admin || permissions.ktv_shift_view === true
  const schedule = admin || ['letan', 'locker', 'quanly', 'tapvu'].some(department => permissions[`work_schedule_${department}`] === true)
  const shifts = ktv || schedule || admin
  const tabs = [
    ...(catalog ? [['services', 'Cài đặt dịch vụ'], ['areas', 'Cài đặt khu vực dịch vụ']] : []),
    ...(shifts ? [['shifts', 'Cài đặt ca']] : []),
    ...(admin ? [['appearance', 'Giao diện'], ['notifications', 'Thông báo']] : []),
    ...(admin || permissions.permission_admin === true ? [['permissions', 'Phân quyền']] : []),
  ]
  const [tab, setTab] = useState(initialTab || tabs[0]?.[0])
  useEffect(() => { if (initialTab) setTab(initialTab) }, [initialTab])
  const activeTab = tabs.some(([key]) => key === tab) ? tab : tabs[0]?.[0]
  const navigateTabs = (event) => {
    const index = tabs.findIndex(([key]) => key === activeTab)
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1
      : event.key === 'ArrowRight' ? (index + 1) % tabs.length
        : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : null
    if (next === null) return
    event.preventDefault()
    setTab(tabs[next][0])
    document.getElementById(`settings-${tabs[next][0]}-tab`)?.focus()
  }
  if (!tabs.length) return <p className="error-box">Tài khoản chưa được cấp quyền mở Cài đặt.</p>
  return <div className="feature-page spa-management settings-page">
    <div className="page-heading"><div><span className="eyebrow">VERA SPA</span><h1>Cài đặt</h1><p>Quản lý dịch vụ, ca làm việc, giao diện, thông báo và phân quyền.</p></div></div>
    <div className="spa-tabs settings-tabs" onKeyDown={navigateTabs} role="tablist" aria-label="Cài đặt">
      {tabs.map(([key, label]) => <button type="button" key={key} id={`settings-${key}-tab`} role="tab" tabIndex={activeTab === key ? 0 : -1} aria-selected={activeTab === key} aria-controls="settings-content" onClick={() => setTab(key)}>{label}</button>)}
    </div>
    <div id="settings-content" role="tabpanel" aria-labelledby={`settings-${activeTab}-tab`}>
      {activeTab === 'appearance' ? appearance : activeTab === 'notifications' ? notifications : activeTab === 'permissions' ? permissionSettings : activeTab === 'shifts' ? <>
        {ktv && <KtvShiftSettingsPanel />}
        {schedule && <DepartmentShiftSettingsPanel />}
        {admin && <ShiftBreakSettingsPanel />}
      </> : <SpaManagementPage key={activeTab} user={user} mode="settings" initialTab={activeTab} embedded />}
    </div>
  </div>
}
