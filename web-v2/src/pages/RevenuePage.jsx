import { CalendarDays, CircleDollarSign, ExternalLink, RefreshCw, TrendingDown, TrendingUp, WalletCards } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const money = (value) => `${Math.round(Number(value || 0)).toLocaleString('vi-VN')}đ`
const fallbackEntryUrl = 'https://docs.google.com/forms/d/e/1FAIpQLSeJp1bLrl8zSyESu_K0eo6NxdKsm85p4fxGXPXigPlmgkAs7w/viewform'

async function loadRevenue(signal) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}
  const response = await fetch(`${apiBase}/v2/revenue/summary`, { signal, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

export default function RevenuePage() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const run = async () => {
      setBusy(true); setError('')
      try { const result = await loadRevenue(controller.signal); if (!controller.signal.aborted) setData(result) }
      catch (err) { if (!controller.signal.aborted && err?.name !== 'AbortError') setError(err.message || 'Không tải được Doanh thu.') }
      finally { if (!controller.signal.aborted) setBusy(false) }
    }
    void run()
    return () => controller.abort()
  }, [revision])

  const cards = [
    { key: 'income', label: 'TỔNG THU', value: data?.total_income, icon: TrendingUp },
    { key: 'expense', label: 'TỔNG CHI', value: data?.total_expense, icon: TrendingDown },
    { key: 'balance', label: 'CÒN LẠI', value: data?.balance, icon: WalletCards },
  ]
  const entryUrl = data?.entry_form_url || fallbackEntryUrl
  const reportUrl = data?.report_url || ''

  return <div className="feature-page revenue-page">
    <style>{`
      .revenue-page .revenue-source{display:flex;gap:8px;align-items:center;color:#68736f;font-size:13px}
      .revenue-period{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:14px}
      .revenue-period-card{display:flex;align-items:center;gap:12px;padding:14px 16px;border:1px solid #dfe7e2;border-radius:15px;background:#fff}
      .revenue-period-card svg{color:#8b6b22;flex:0 0 auto}.revenue-period-card span{display:block;font-size:11px;font-weight:900;letter-spacing:.05em;color:#68736f;text-transform:uppercase}.revenue-period-card strong{display:block;margin-top:3px;font-size:18px;color:#173329}
      .revenue-actions{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}.revenue-action-link{display:inline-flex;align-items:center;justify-content:center;gap:8px;text-decoration:none;min-height:43px}.revenue-action-link.disabled{opacity:.45;pointer-events:none}
      .revenue-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
      .revenue-card{padding:22px;border:1px solid #dfe7e2;border-radius:18px;background:#fff;min-width:0}
      .revenue-card-head{display:flex;align-items:center;gap:9px;color:#5d6f66;font-size:12px;font-weight:900;letter-spacing:.05em}
      .revenue-card-value{margin-top:14px;font-size:30px;line-height:1.05;font-weight:900;color:#173329;overflow-wrap:anywhere}
      .revenue-card.balance{background:#f3f8f5;border-color:#cbded3}
      .revenue-meta{margin-top:14px;padding:12px 14px;border:1px solid #e4eae6;border-radius:13px;background:#fafcfb;color:#68736f;font-size:12px}
      @media(max-width:760px){.revenue-period{grid-template-columns:1fr}.revenue-actions{display:grid;grid-template-columns:1fr 1fr}.revenue-grid{grid-template-columns:1fr;gap:9px}.revenue-card{padding:15px;border-radius:14px}.revenue-card-value{margin-top:8px;font-size:24px}.revenue-page .page-heading{align-items:flex-start}}
      @media(max-width:460px){.revenue-actions{grid-template-columns:1fr}}
    `}</style>
    <div className="page-heading">
      <div><span className="eyebrow"><CircleDollarSign size={14} /> Tài chính</span><h1>DOANH THU</h1><p className="revenue-source">Dữ liệu trực tiếp từ Quản lý Thu Chi · sheet Input.</p></div>
      <button className="secondary-button" type="button" onClick={() => setRevision((value) => value + 1)} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới</button>
    </div>
    {error && <div className="error-box">{error}</div>}

    <section className="revenue-period" aria-label="Khoảng dữ liệu Doanh thu">
      <article className="revenue-period-card"><CalendarDays size={20} /><div><span>Ngày bắt đầu</span><strong>{busy && !data ? '…' : (data?.start_date_label || '—')}</strong></div></article>
      <article className="revenue-period-card"><CalendarDays size={20} /><div><span>Ngày hiện tại</span><strong>{busy && !data ? '…' : (data?.current_date_label || '—')}</strong></div></article>
    </section>

    <div className="revenue-actions">
      <a className="primary-button revenue-action-link" href={entryUrl} target="_blank" rel="noopener noreferrer"><ExternalLink size={16} /> Nhập thu chi</a>
      <a className={`secondary-button revenue-action-link ${reportUrl ? '' : 'disabled'}`.trim()} href={reportUrl || '#'} target="_blank" rel="noopener noreferrer" aria-disabled={!reportUrl}><ExternalLink size={16} /> Xem báo cáo</a>
    </div>

    <section className="revenue-grid" aria-live="polite">
      {cards.map(({ key, label, value, icon: Icon }) => <article className={`revenue-card ${key}`} key={key}><div className="revenue-card-head"><Icon size={18} aria-hidden="true" /> {label}</div><div className="revenue-card-value">{busy && !data ? '…' : money(value)}</div></article>)}
    </section>
    {data && <div className="revenue-meta">Nguồn: <strong>{data.source || 'Quản lý Thu Chi'}</strong> · Sheet: <strong>{data.worksheet || 'Input'}</strong>{' · '}Số giao dịch Thu/Chi đã tính: <strong>{Number(data.transaction_count || 0).toLocaleString('vi-VN')}</strong>.</div>}
  </div>
}
