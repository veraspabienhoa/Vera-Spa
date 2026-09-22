import { useState } from 'react'
import SpaManagementPage from './SpaManagementPage'
import KtvShiftSettingsPanel from './KtvShiftSettingsPanel'
import ShiftBreakSettingsPanel from './ShiftBreakSettingsPanel'
import DepartmentShiftSettingsPanel from './DepartmentShiftSettingsPanel'
import './SpaManagementPage.css'

export default function SettingsPage({ user }) {
  const admin = user?.role === 'admin'
  const permissions = user?.permissions || {}
  const catalog = admin || permissions.live_tour_admin === true
  const ktv = admin || permissions.ktv_shift_view === true
  const schedule = admin || ['letan', 'locker', 'quanly', 'tapvu'].some(department => permissions[`work_schedule_${department}`] === true)
  const shifts = ktv || schedule || admin
  const [tab, setTab] = useState(catalog ? 'services' : 'shifts')
  const activeTab = tab === 'shifts' ? (shifts ? tab : 'services') : (catalog ? tab : 'shifts')
  if (!catalog && !shifts) return <p className="error-box">Tài khoản chưa được cấp quyền mở Cài đặt.</p>
  return <div className="feature-page spa-management">
    <div className="page-heading"><div><span className="eyebrow">VERA SPA</span><h1>Cài đặt</h1><p>Quản lý dịch vụ, khu vực phục vụ và ca làm việc.</p></div></div>
    <div className="spa-tabs" role="tablist" aria-label="Cài đặt">
      {(catalog ? [['services', 'Cài đặt dịch vụ'], ['areas', 'Cài đặt khu vực dịch vụ']] : []).concat(shifts ? [['shifts', 'Cài đặt ca']] : []).map(([key, label]) => <button type="button" key={key} id={`settings-${key}-tab`} role="tab" aria-selected={activeTab === key} aria-controls="settings-content" onClick={() => setTab(key)}>{label}</button>)}
    </div>
    <div id="settings-content" role="tabpanel" aria-labelledby={`settings-${activeTab}-tab`}>
      {activeTab === 'shifts' ? <>
        {ktv && <KtvShiftSettingsPanel />}
        {schedule && <DepartmentShiftSettingsPanel />}
        {admin && <ShiftBreakSettingsPanel />}
      </> : <SpaManagementPage key={activeTab} user={user} mode="settings" initialTab={activeTab} embedded />}
    </div>
  </div>
}
