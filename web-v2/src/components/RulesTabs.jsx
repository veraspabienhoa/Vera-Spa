import { Suspense, useState } from 'react'
import PageErrorBoundary from './PageErrorBoundary'
import './RulesTabs.css'

export default function RulesTabs({ initialTab = 'administrative', administrative, ktv }) {
  const [active, setActive] = useState(initialTab)
  const [visited, setVisited] = useState([initialTab])
  const tabs = [{ id: 'administrative', label: 'Nội quy hành chánh', content: administrative }, { id: 'ktv', label: 'Nội quy KTV', content: ktv }]
  return <section className="rules-tabs-page">
    <h1>Nội qui</h1>
    <div className="rules-menu-tabs" role="tablist" aria-label="Nội qui">{tabs.map(tab => <button type="button" id={`rules-tab-${tab.id}`} role="tab" aria-selected={active === tab.id} aria-controls={`rules-panel-${tab.id}`} key={tab.id} onClick={() => { setActive(tab.id); setVisited(rows => rows.includes(tab.id) ? rows : [...rows, tab.id]) }}>{tab.label}</button>)}</div>
    {tabs.map(tab => <div key={tab.id} id={`rules-panel-${tab.id}`} role="tabpanel" aria-labelledby={`rules-tab-${tab.id}`} hidden={active !== tab.id}>
      {visited.includes(tab.id) && <PageErrorBoundary page={tab.id === 'ktv' ? 'rules' : 'hc-rules'}><Suspense fallback={<p role="status">Đang tải nội quy…</p>}>{tab.content}</Suspense></PageErrorBoundary>}
    </div>)}
  </section>
}
