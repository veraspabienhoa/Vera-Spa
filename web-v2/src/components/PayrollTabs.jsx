import { useState } from 'react'
import './PayrollTabs.css'

export default function PayrollTabs({ user, initialTab = 'ktv', ktv, administrative }) {
  const admin = user?.role === 'admin'
  const tabs = [
    { id: 'ktv', label: 'Lương KTV', allowed: admin || user?.permissions?.payroll_history === true, content: ktv },
    { id: 'administrative', label: 'Lương hành chánh', allowed: admin || user?.permissions?.payroll_calculate === true, content: administrative },
  ].filter(tab => tab.allowed)
  const [selected, setSelected] = useState(initialTab)
  const active = tabs.find(tab => tab.id === selected)?.id || tabs[0]?.id
  const [visited, setVisited] = useState([active])
  if (!tabs.length) return <p className="error-box" role="alert">Tài khoản chưa được cấp quyền xem Bảng Lương.</p>
  return <section className="payroll-tabs-page">
    <h1>Bảng Lương</h1>
    <div className="payroll-menu-tabs" role="tablist" aria-label="Bảng Lương">{tabs.map(tab => <button type="button" key={tab.id} id={`payroll-tab-${tab.id}`} role="tab" aria-selected={active === tab.id} aria-controls={`payroll-panel-${tab.id}`} onClick={() => {
      setSelected(tab.id)
      setVisited(current => current.includes(tab.id) ? current : [...current, tab.id])
    }}>{tab.label}</button>)}</div>
    {tabs.map(tab => <div key={tab.id} id={`payroll-panel-${tab.id}`} role="tabpanel" aria-labelledby={`payroll-tab-${tab.id}`} hidden={active !== tab.id}>
      {(active === tab.id || visited.includes(tab.id)) && tab.content}
    </div>)}
  </section>
}
