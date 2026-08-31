import { AlertTriangle, CalendarDays, CheckCircle2, CircleDollarSign, ExternalLink, FileSpreadsheet, RefreshCw, Save, TrendingDown, TrendingUp, WalletCards } from 'lucide-react'
import { useEffect, useState } from 'react'
import { numberInputDisplayValue } from '../lib/numberInput'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const money = (value) => `${Math.round(Number(value || 0)).toLocaleString('vi-VN')}đ`
const numberText = (value) => Number(value || 0).toLocaleString('vi-VN', { maximumFractionDigits: 2 })
const fallbackEntryUrl = 'https://docs.google.com/forms/d/e/1FAIpQLSeJp1bLrl8zSyESu_K0eo6NxdKsm85p4fxGXPXigPlmgkAs7w/viewform'
const reconcileFilters = [
  ['today', 'Hôm nay'],
  ['yesterday', 'Hôm qua'],
  ['this_week', 'Tuần này'],
  ['last_week', 'Tuần trước'],
  ['this_month', 'Tháng này'],
  ['last_month', 'Tháng trước'],
  ['custom', 'Tùy chỉnh'],
]

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

async function loadPurchaseReconcile({ preset, start, end, signal }) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const params = new URLSearchParams({ preset })
  if (preset === 'custom') {
    if (start) params.set('start', start)
    if (end) params.set('end', end)
  }
  const response = await fetch(`${apiBase}/v2/revenue/purchase-reconcile?${params.toString()}`, {
    signal,
    headers: await authorizedHeaders(),
  })
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
  const [filterPreset, setFilterPreset] = useState('this_month')
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')
  const [reconcile, setReconcile] = useState(null)
  const [reconcileBusy, setReconcileBusy] = useState(false)
  const [reconcileError, setReconcileError] = useState('')

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

  useEffect(() => {
    if (filterPreset === 'custom' && (!customStart || !customEnd)) {
      setReconcile(null)
      setReconcileError('')
      return undefined
    }
    const controller = new AbortController()
    const run = async () => {
      setReconcileBusy(true); setReconcileError('')
      try {
        const result = await loadPurchaseReconcile({
          preset: filterPreset,
          start: customStart,
          end: customEnd,
          signal: controller.signal,
        })
        if (!controller.signal.aborted) setReconcile(result)
      } catch (err) {
        if (!controller.signal.aborted && err?.name !== 'AbortError') setReconcileError(err.message || 'Không tải được báo cáo đối chiếu mua hàng.')
      } finally {
        if (!controller.signal.aborted) setReconcileBusy(false)
      }
    }
    void run()
    return () => controller.abort()
  }, [filterPreset, customStart, customEnd, revision])

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
      .reconcile-panel{margin-top:20px;padding:16px;border:1px solid #dfe7e2;border-radius:18px;background:#fff}.reconcile-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:14px}.reconcile-head h2{margin:3px 0 0;font-size:20px;color:#173329}.reconcile-head p{margin:4px 0 0;color:#68736f;font-size:12px}
      .reconcile-filter{display:flex;align-items:end;gap:8px;flex-wrap:wrap}.reconcile-filter label{display:grid;gap:5px;font-size:11px;font-weight:900;color:#53635c}.reconcile-filter select,.reconcile-filter input{min-height:40px;min-width:145px}
      .reconcile-status{display:flex;gap:10px;align-items:flex-start;padding:12px 14px;border-radius:13px;margin-bottom:12px;font-weight:800;font-size:13px}.reconcile-status.ok{background:#eef8f1;border:1px solid #bdd9c6;color:#245b38}.reconcile-status.bad{background:#fff5e8;border:1px solid #efc27c;color:#864d00}.reconcile-status svg{flex:0 0 auto;margin-top:1px}
      .reconcile-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}.reconcile-kpi{padding:13px;border:1px solid #e1e7e3;border-radius:14px;background:#fafcfb}.reconcile-kpi span{display:block;font-size:10px;font-weight:900;color:#69766f;letter-spacing:.04em}.reconcile-kpi strong{display:block;margin-top:5px;font-size:19px;color:#173329}.reconcile-kpi.bad strong{color:#a14f00}
      .reconcile-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}.report-box{min-width:0;border:1px solid #e2e8e4;border-radius:14px;overflow:hidden}.report-box h3{display:flex;gap:8px;align-items:center;margin:0;padding:11px 13px;background:#f5f8f6;color:#24473a;font-size:13px}.report-scroll{overflow:auto;max-height:430px}.report-table{width:100%;border-collapse:collapse;min-width:650px;font-size:12px}.report-table th,.report-table td{padding:8px 9px;border-bottom:1px solid #edf1ee;white-space:nowrap;text-align:left}.report-table th{position:sticky;top:0;background:#f9fbfa;z-index:1;font-size:10px;color:#5e6d66;text-transform:uppercase}.report-table .money{text-align:right;font-variant-numeric:tabular-nums}.report-table tr.mismatch td{background:#fff4e5}.report-table tr.match td{background:#f5fbf7}.report-table tr.purchase-row td{font-weight:700}.status-match{color:#24703e;font-weight:900}.status-mismatch{color:#a14f00;font-weight:900}
      @media(max-width:1050px){.revenue-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.reconcile-grid{grid-template-columns:1fr}.reconcile-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
      @media(max-width:760px){.revenue-period{grid-template-columns:1fr}.revenue-actions{display:grid;grid-template-columns:1fr 1fr}.revenue-tip-editor{grid-template-columns:1fr}.revenue-tip-editor button{width:100%}.revenue-grid{grid-template-columns:1fr;gap:9px}.revenue-card{padding:15px;border-radius:14px}.revenue-card-value{margin-top:8px;font-size:24px}.revenue-page .page-heading{align-items:flex-start}.reconcile-head{display:grid}.reconcile-filter{display:grid;grid-template-columns:1fr 1fr}.reconcile-filter label:first-child{grid-column:1/-1}.reconcile-filter select,.reconcile-filter input{width:100%;min-width:0}.reconcile-kpis{grid-template-columns:1fr 1fr}}
      @media(max-width:460px){.revenue-actions{grid-template-columns:1fr}.reconcile-filter,.reconcile-kpis{grid-template-columns:1fr}.reconcile-filter label:first-child{grid-column:auto}}
    `}</style>
    <div className="page-heading">
      <div><span className="eyebrow"><CircleDollarSign size={14} /> Tài chính</span><h1>DOANH THU</h1><p className="revenue-source">Dữ liệu trực tiếp từ Quản lý Thu Chi · sheet Input.</p></div>
      <button className="secondary-button" type="button" onClick={() => { setNotice(''); setRevision((value) => value + 1) }} disabled={busy || reconcileBusy}><RefreshCw size={16} className={(busy || reconcileBusy) ? 'spin' : ''} /> Làm mới</button>
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

    <section className="reconcile-panel">
      <div className="reconcile-head">
        <div><span className="eyebrow"><FileSpreadsheet size={14}/> Đối chiếu chi mua hàng</span><h2>BÁO CÁO MUA HÀNG ↔ QUẢN LÝ THU CHI</h2><p>So sánh theo từng ngày: tổng cột Thành Tiền của BaoCaoMuaHang với các dòng Input có B = Chi và nội dung mua hàng, số tiền lấy từ cột C.</p></div>
        <div className="reconcile-filter">
          <label>Bộ lọc<select value={filterPreset} onChange={(event) => setFilterPreset(event.target.value)}>{reconcileFilters.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
          {filterPreset === 'custom' && <><label>Từ ngày<input type="date" value={customStart} onChange={(event) => setCustomStart(event.target.value)} /></label><label>Đến ngày<input type="date" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} /></label></>}
        </div>
      </div>

      {filterPreset === 'custom' && (!customStart || !customEnd) && <div className="revenue-meta">Chọn đủ Từ ngày và Đến ngày để xem hai báo cáo.</div>}
      {reconcileError && <div className="error-box">{reconcileError}</div>}
      {reconcileBusy && !reconcile && <div className="revenue-meta">Đang đọc BaoCaoMuaHang và Quản lý Thu Chi…</div>}

      {reconcile && <>
        <div className={`reconcile-status ${reconcile.all_match ? 'ok' : 'bad'}`}>
          {reconcile.all_match ? <CheckCircle2 size={19}/> : <AlertTriangle size={19}/>}
          <div>{reconcile.all_match
            ? `KHỚP: Không có chênh lệch trong ${reconcile.start_date_label} – ${reconcile.end_date_label}.`
            : `KHÔNG KHỚP: Có ${Number(reconcile.mismatch_count || 0)} ngày chênh lệch trong ${reconcile.start_date_label} – ${reconcile.end_date_label}.`}</div>
        </div>

        <div className="reconcile-kpis">
          <article className="reconcile-kpi"><span>BAOCAOMUAHANG · THÀNH TIỀN</span><strong>{money(reconcile.purchase_total)}</strong></article>
          <article className="reconcile-kpi"><span>THU CHI · CHI MUA HÀNG</span><strong>{money(reconcile.ledger_purchase_total)}</strong></article>
          <article className={`reconcile-kpi ${Math.abs(Number(reconcile.difference || 0)) >= 0.5 ? 'bad' : ''}`}><span>CHÊNH LỆCH</span><strong>{money(reconcile.difference)}</strong></article>
          <article className={`reconcile-kpi ${Number(reconcile.mismatch_count || 0) ? 'bad' : ''}`}><span>SỐ NGÀY KHÔNG KHỚP</span><strong>{Number(reconcile.mismatch_count || 0).toLocaleString('vi-VN')}</strong></article>
        </div>

        <div className="report-box">
          <h3><CalendarDays size={16}/> ĐỐI CHIẾU THEO NGÀY</h3>
          <div className="report-scroll"><table className="report-table"><thead><tr><th>Ngày</th><th className="money">BaoCaoMuaHang</th><th className="money">Thu Chi · Mua hàng</th><th className="money">Chênh lệch</th><th>Trạng thái</th></tr></thead><tbody>
            {(reconcile.comparison_rows || []).map((row) => <tr key={row.date} className={row.matched ? 'match' : 'mismatch'}><td>{row.date_label}</td><td className="money">{money(row.purchase_total)}</td><td className="money">{money(row.ledger_purchase_total)}</td><td className="money">{money(row.difference)}</td><td className={row.matched ? 'status-match' : 'status-mismatch'}>{row.matched ? 'KHỚP' : 'KHÔNG KHỚP'}</td></tr>)}
            {!(reconcile.comparison_rows || []).length && <tr><td colSpan="5">Không có dữ liệu mua hàng trong khoảng đã chọn.</td></tr>}
          </tbody></table></div>
        </div>

        <div className="reconcile-grid">
          <div className="report-box"><h3><FileSpreadsheet size={16}/> BaoCaoMuaHang.xlsb · Input</h3><div className="report-scroll"><table className="report-table"><thead><tr><th>Ngày nhập</th><th>Chi tiết hàng hóa</th><th className="money">Số lượng</th><th className="money">Đơn giá</th><th className="money">Thành Tiền</th><th>Người đặt</th><th>User</th></tr></thead><tbody>
            {(reconcile.purchase_rows || []).map((row, index) => <tr key={`${row.date}-${index}`}><td>{row.date_label}</td><td>{row.item || '—'}</td><td className="money">{numberText(row.quantity)}</td><td className="money">{money(row.unit_price)}</td><td className="money">{money(row.amount)}</td><td>{row.buyer || '—'}</td><td>{row.user || '—'}</td></tr>)}
            {!(reconcile.purchase_rows || []).length && <tr><td colSpan="7">Không có dữ liệu.</td></tr>}
          </tbody></table></div></div>

          <div className="report-box"><h3><FileSpreadsheet size={16}/> Quản lý Thu Chi · Input</h3><div className="report-scroll"><table className="report-table"><thead><tr><th>Ngày</th><th>B · Loại giao dịch</th><th className="money">C · Số tiền</th><th>Ghi chú</th></tr></thead><tbody>
            {(reconcile.ledger_rows || []).map((row, index) => <tr key={`${row.date}-${index}`} className={row.is_purchase ? 'purchase-row' : ''}><td>{row.date_label}</td><td>{row.type}</td><td className="money">{money(row.amount)}</td><td>{row.note || '—'}</td></tr>)}
            {!(reconcile.ledger_rows || []).length && <tr><td colSpan="4">Không có dữ liệu.</td></tr>}
          </tbody></table></div></div>
        </div>
        <div className="revenue-meta">Trong Quản lý Thu Chi, ngày ưu tiên lấy từ ngày ghi trong cột Ghi chú (ví dụ “Mua đồ ngày 27/08/2026”), sau đó mới dùng cột Ngày giao dịch. Cách này xử lý đúng các dòng được nhập bù nhiều ngày cùng lúc.</div>
      </>}
    </section>
  </div>
}
