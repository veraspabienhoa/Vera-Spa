import UiToolbar from './UiToolbar'
import { Suspense, useState } from 'react'
import PageErrorBoundary from './PageErrorBoundary'
import './PayrollTabs.css'

export default function PayrollTabs({ user, initialTab = 'ktv', ktv, administrative, configuration }) {
  const admin = user?.role === 'admin'
  const tabs = [
    { id: 'ktv', page: 'payroll', label: 'Lương KTV', allowed: admin || user?.permissions?.payroll_history === true, content: ktv },
    { id: 'administrative', page: 'department-payroll', label: 'Lương hành chánh', allowed: admin || user?.permissions?.payroll_calculate === true, content: administrative },
    { id: 'configuration', page: 'payroll-config', label: 'Cấu hình lương', allowed: admin, content: configuration },
  ].filter(tab => tab.allowed)
  const [selected, setSelected] = useState(initialTab)
  const active = tabs.find(tab => tab.id === selected)?.id || tabs[0]?.id
  const [visited, setVisited] = useState([active])
  if (!tabs.length) return <p className="error-box" role="alert">Tài khoản chưa được cấp quyền xem Bảng Lương.</p>
  return <section data-ui-key="u-ddf45b437365" className="payroll-tabs-page">
    <UiToolbar data-ui-key="u-26dc4fb6c705" className="payroll-menu-tabs" role="tablist" aria-label="Bảng Lương">{tabs.map(tab => <button data-ui-key="u-b2175291398c" type="button" key={tab.id} id={`payroll-tab-${tab.id}`} role="tab" aria-selected={active === tab.id} aria-controls={`payroll-panel-${tab.id}`} onClick={() => {
      setSelected(tab.id)
      setVisited(current => current.includes(tab.id) ? current : [...current, tab.id])
    }}>{tab.label}</button>)}</UiToolbar>
    {tabs.map(tab => <div key={tab.id} id={`payroll-panel-${tab.id}`} role="tabpanel" aria-labelledby={`payroll-tab-${tab.id}`} hidden={active !== tab.id}>
      {(active === tab.id || visited.includes(tab.id)) && <PageErrorBoundary page={tab.page} onRetry={() => tab.content?.type?.reset?.()}>
        <Suspense fallback={<p role="status">Đang tải {tab.label}…</p>}>{tab.content}</Suspense>
      </PageErrorBoundary>}
    </div>)}
  </section>
}
