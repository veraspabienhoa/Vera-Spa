import { Suspense, useState } from 'react'
import { recoverablePage as lazyPage } from '../lib/recoverablePage'

const SnapshotPage = lazyPage(() => import('./SnapshotPage'))
const CheckinHistoryPage = lazyPage(() => import('./CheckinHistoryPage'))

export default function AttendancePage({ user, initialTab = 'snapshot' }) {
  const [selected, setSelected] = useState(initialTab)
  const tabs = [
    { id: 'snapshot', label: 'Bảng chấm công', allowed: user?.permissions?.snapshot_today === true },
    { id: 'history', label: 'Lịch sử check in', allowed: user?.permissions?.device_history_view === true },
  ].filter(tab => tab.allowed)
  const active = tabs.some(tab => tab.id === selected) ? selected : tabs[0]?.id
  return <div className="attendance-workspace">
    <div className="page-heading"><h1>CHẤM CÔNG</h1></div>
    {!tabs.length ? <p role="status">Bạn chưa được cấp quyền xem chấm công hoặc lịch sử check in.</p> : <>
      <div className="attendance-tabs" role="tablist" aria-label="Chấm công">
        {tabs.map((tab, index) => <button key={tab.id} type="button" role="tab"
          id={`attendance-tab-${tab.id}`} aria-controls={`attendance-panel-${tab.id}`}
          aria-selected={active === tab.id} tabIndex={active === tab.id ? 0 : -1}
          onClick={() => setSelected(tab.id)} onKeyDown={event => {
            const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length
              : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length
                : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null
            if (next === null) return
            event.preventDefault(); setSelected(tabs[next].id)
            document.getElementById(`attendance-tab-${tabs[next].id}`)?.focus()
          }}>{tab.label}</button>)}
      </div>
      <section role="tabpanel" id={`attendance-panel-${active}`} aria-labelledby={`attendance-tab-${active}`}>
        <Suspense fallback={<p role="status">Đang tải…</p>}>
          {active === 'snapshot' ? <SnapshotPage user={user} embedded /> : <CheckinHistoryPage user={user} embedded />}
        </Suspense>
      </section>
    </>}
  </div>
}
