import { CalendarDays, CircleDollarSign, ExternalLink, RefreshCw, Save, TrendingDown, TrendingUp, WalletCards } from 'lucide-react'
import { useEffect, useState } from 'react'
import { numberInputDisplayValue } from '../lib/numberInput'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const money = (value) => `${Math.round(Number(value || 0)).toLocaleString('vi-VN')}đ`
const fallbackEntryUrl = 'https://docs.google.com/forms/d/e/1FAIpQLSeJp1bLrl8zSyESu_K0eo6NxdKsm85p4fxGXPXigPlmgkAs7w/viewform'

async function authorizedHeaders(withJson = false) {
  const session = await getCurrentSession()
  const headers = new Headers()
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  if (withJson) headers.set('Content-Type', 'application/json')
  return headers
}

async function loadRevenue(signal) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const response = await fetch(`${apiBase}/v2/revenue/summary`, { signal, headers: await authorizedHeaders() })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

async function savePeriodTip(amount) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const response = await fetch(`${apiBase}/v2/revenue/tip`, {
    method: 'PUT',
    headers: await authorizedHeaders(true),
    body: JSON.stringify({ amount: Number(amount || 0) }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

export default function RevenuePage() {
  const [data, setData] = useState(null)
  const [tip, setTip] = useState(0)
  const [busy, setBusy] = useState(false)
  const [savingTip, setSavingTip] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const run = async () => {
      setBusy(true); setError('')
      try {
        const result = await loadRevenue(controller.signal)
        if (!controller.signal.aborted) {
          setData(result)
          setTip(Number(result.period_tip || 0))
        }
      }
      catch (err) { if (!controller.signal.aborted && err?.name !== 'AbortError') setError(err.message || 'Không tải được Doanh thu.') }
      finally { if (!controller.signal.aborted) setBusy(false) }
    }
    void run()
    return () => controller.abort()
  }, [revision])

  const submitTip = async () => {
    setSavingTip(true); setError(''); setNotice('')
    try {
      if (!Number.isFinite(Number(tip)) || Number(tip) < 0) throw new Error('Tiền TIP trong kỳ phải là số không âm.')
      const result = await savePeriodTip(tip)
      setData((current) => current ? ({ ...current, period_tip: result.period_tip, balance: result.balance }) : current)
      setTip(Number(result.period_tip || 0))
      setNotice(result.message || 'Đã lưu Tiền TIP trong kỳ.')
    } catch (err) {
      setError(err.message || 'Không lưu được Tiền TIP trong kỳ.')
    } finally {
      setSavingTip(false)
    }
  }

  const cards = [
    { key: 'income', label: 'TỔNG THU', value: data?.total_income, icon: TrendingUp },
    { key: 'expense', label: 'TỔNG CHI', value: data?.total_expense, icon: TrendingDown },
    { key: 'tip', label: 'TIỀN TIP TRONG KỲ', value: data?.period_tip, icon: CircleDollarSign },
    { key: 'balance', label: 'CÒN LẠI', value: data?.balance, icon: WalletCards },
  ]
  const entryUrl = data?.entry_form_url || fallbackEntryUrl
  const reportUrl = data?.report_url || ''
  const canEditTip = Boolean(data?.can_edit_tip)

  return <div className="feature-page revenue-page">
    <style>{`
      .revenue-page .revenue-source{display:flex;gap:8px;align-items:center;color:#68736f;font-size:13px}
      .revenue-period{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:14px}
      .revenue-period-card{display:flex;align-items:center;gap:12px;padding:14px 16px;border:1px solid #dfe7e2;border-radius:15px;background:#fff}
      .revenue-period-card svg{color:#8b6b22;flex:0 0 auto}.revenue-period-card span{display:block;font-size:11px;font-weight:900;letter-spacing:.05em;color:#68736f;text-transform:uppercase}.revenue-period-card strong{display:block;margin-top:3px;font-size:18px;color:#173329}
      .revenue-actions{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}.revenue-action-link{display:inline-flex;align-items:center;justify-content:center;gap:8px;text-decoration:none;min-height:43px}.revenue-action-link.disabled{opacity:.45;pointer-events:none}
      .revenue-tip-editor{display:grid;grid-template-columns:minmax(220px,380px) auto 1fr;gap:10px;align-items:end;margin-bottom:14px;padding:14px;border:1px solid #dfd5b9;border-radius:15px;background:#fffaf0}.revenue-tip-editor label{display:grid;gap:5px;font-size:12px;font-weight:900}.revenue-tip-editor input{font-size:18px;font-weight:800;text-align:right}.revenue-tip-editor small{color:#75694d;line-height:1.45}
      .revenue-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
      .revenue-card{padding:22px;border:1px solid #dfe7e2;border-radius:18px;background:#fff;min-width:0}
      .revenue-card-head{display:flex;align-items:center;gap:9px;color:#5d6f66;font-size:12px;font-weight:900;letter-spacing:.05em}
      .revenue-card-value{margin-top:14px;font-size:30px;line-height:1.05;font-weight:900;color:#173329;overflow-wrap:anywhere}
      .revenue-card.tip{background:#fffaf0;border-color:#e4d5ad}.revenue-card.balance{background:#f3f8f5;border-color:#cbded3}
      .revenue-formula{margin-top:14px;padding:12px 14px;border:1px solid #cbded3;border-radius:13px;background:#f3f8f5;color:#244a3a;font-size:13px;font-weight:800;text-align:center}
      .revenue-meta{margin-top:10px;padding:12px 14px;border:1px solid #e4eae6;border-radius:13px;background:#fafcfb;color:#68736f;font-size:12px}
      @media(max-width:1050px){.revenue-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
      @media(max-width:760px){.revenue-period{grid-template-columns:1fr}.revenue-actions{display:grid;grid-template-columns:1fr 1fr}.revenue-tip-editor{grid-template-columns:1fr}.revenue-tip-editor button{width:100%}.revenue-grid{grid-template-columns:1fr;gap:9px}.revenue-card{padding:15px;border-radius:14px}.revenue-card-value{margin-top:8px;font-size:24px}.revenue-page .page-heading{align-items:flex-start}}
      @media(max-width:460px){.revenue-actions{grid-template-columns:1fr}}
    `}</style>
    <div className="page-heading">
      <div><span className="eyebrow"><CircleDollarSign size={14} /> Tài chính</span><h1>DOANH THU</h1><p className="revenue-source">Dữ liệu trực tiếp từ Quản lý Thu Chi · sheet Input.</p></div>
      <button className="secondary-button" type="button" onClick={() => { setNotice(''); setRevision((value) => value + 1) }} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới</button>
    </div>
    {error && <div className="error-box">{error}</div>}
    {notice && <div className="success-box">{notice}</div>}

    <section className="revenue-period" aria-label="Khoảng dữ liệu Doanh thu">
      <article className="revenue-period-card"><CalendarDays size={20} /><div><span>Ngày bắt đầu</span><strong>{busy && !data ? '…' : (data?.start_date_label || '—')}</strong></div></article>
      <article className="revenue-period-card"><CalendarDays size={20} /><div><span>Ngày hiện tại</span><strong>{busy && !data ? '…' : (data?.current_date_label || '—')}</strong></div></article>
    </section>

    <div className="revenue-actions">
      <a className="primary-button revenue-action-link" href={entryUrl} target="_blank" rel="noopener noreferrer"><ExternalLink size={16} /> Nhập thu chi</a>
      <a className={`secondary-button revenue-action-link ${reportUrl ? '' : 'disabled'}`.trim()} href={reportUrl || '#'} target="_blank" rel="noopener noreferrer" aria-disabled={!reportUrl}><ExternalLink size={16} /> Xem báo cáo</a>
    </div>

    {canEditTip && <section className="revenue-tip-editor">
      <label>TIỀN TIP TRONG KỲ<input type="number" min="0" step="1000" inputMode="numeric" value={numberInputDisplayValue(tip)} disabled={savingTip} onChange={(event) => setTip(event.target.value)} /></label>
      <button type="button" className="primary-button" onClick={submitTip} disabled={savingTip || busy}><Save size={16}/> {savingTip ? 'Đang lưu…' : 'Lưu Tiền TIP'}</button>
      <small>Số tiền này được lưu theo kỳ Doanh thu hiện tại. Công thức Còn lại sẽ trừ Tiền TIP trong kỳ ngay sau khi lưu.</small>
    </section>}

    <section className="revenue-grid" aria-live="polite">
      {cards.map(({ key, label, value, icon: Icon }) => <article className={`revenue-card ${key}`} key={key}><div className="revenue-card-head"><Icon size={18} aria-hidden="true" /> {label}</div><div className="revenue-card-value">{busy && !data ? '…' : money(value)}</div></article>)}
    </section>
    {data && <div className="revenue-formula">{money(data.total_income)} - {money(data.total_expense)} - {money(data.period_tip)} = {money(data.balance)} · Tổng thu - Tổng chi - Tiền TIP trong kỳ = Còn lại</div>}
    {data && <div className="revenue-meta">Nguồn: <strong>{data.source || 'Quản lý Thu Chi'}</strong> · Sheet: <strong>{data.worksheet || 'Input'}</strong>{' · '}Số giao dịch Thu/Chi đã tính: <strong>{Number(data.transaction_count || 0).toLocaleString('vi-VN')}</strong>.</div>}
  </div>
}
