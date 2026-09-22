import UiToolbar from './UiToolbar'
import { useEffect, useState } from 'react'
import './PayrollTabs.css'
export default function SystemTabs({ user, initialTab = 'changes', changes, storage }) {
  const [selected, setSelected] = useState(initialTab)
  useEffect(() => setSelected(initialTab), [initialTab])
  const tabs = [
    { id: 'changes', label: 'Thay đổi hệ thống', permission: 'audit_admin_view', content: changes },
    { id: 'storage', label: 'Bộ nhớ hệ thống', permission: 'storage_admin_view', content: storage },
  ].filter(item => user?.role === 'admin' || user?.permissions?.[item.permission] === true)
  const active = tabs.find(item => item.id === selected) || tabs[0]
  if (!active) return <p className="error-box">Tài khoản chưa được cấp quyền mở Hệ thống.</p>
  return <section data-ui-key="u-e2c4932df2ec" className="system-tabs-page"><h1>Hệ thống</h1><UiToolbar data-ui-key="u-895a139514c6" className="payroll-menu-tabs" role="tablist" aria-label="Hệ thống">{tabs.map(item => <button data-ui-key="u-0ddf24f3ca75" type="button" role="tab" id={`system-${item.id}-tab`} aria-selected={active.id === item.id} aria-controls="system-tab-content" key={item.id} onClick={() => setSelected(item.id)}>{item.label}</button>)}</UiToolbar><div id="system-tab-content" role="tabpanel" aria-labelledby={`system-${active.id}-tab`}>{active.content}</div></section>
}
