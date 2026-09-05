import { AlertTriangle, CalendarDays, CheckCircle2, CircleDollarSign, ExternalLink, FileSpreadsheet, RefreshCw, Save, TrendingDown, TrendingUp, WalletCards } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { numberInputDisplayValue } from '../lib/numberInput'
import { getCurrentSession } from '../lib/supabase'
import VeraDateInput from '../components/VeraDateInput'

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
const differenceFilters = [
  ['all', 'Tất cả'],
  ['exact', 'Bằng 0'],
  ['near', '1 – 5.000đ'],
  ['mismatch', 'Trên 5.000đ'],
]
const statusFilters = [
  ['all', 'Tất cả'],
  ['KHỚP', 'KHỚP'],
  ['GẦN KHỚP', 'GẦN KHỚP'],
  ['KHÔNG KHỚP', 'KHÔNG KHỚP'],
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

function statusClass(status) {
  if (status === 'KHỚP') return 'match'
  if (status === 'GẦN KHỚP') return 'near'
  return 'mismatch'
}

function statusTextClass(status) {
  if (status === 'KHỚP') return 'status-match'
  if (status === 'GẦN KHỚP') return 'status-near'
  return 'status-mismatch'
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
  const [differenceFilter, setDifferenceFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')

  useEffect(() => {
    const controller = new AbortController()
    const run = async () => {
      setBusy(true)
      setError('')
      try {
        const result = await loadRevenue(controller.signal)
        if (!controller.signal.aborted) {
          setData(result)
          setTip(Number(result.period_tip || 0))
        }
      } catch (err) {
        if (!controller.signal.aborted && err?.name !== 'AbortError') setError(err.message || 'Không tải được Doanh thu.')
      } finally {
        if (!controller.signal.aborted) setBusy(false)
      }
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
      setReconcileBusy(true)
      setReconcileError('')
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
    setSavingTip(true)
    setError('')
    setNotice('')
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

  const comparisonRows = useMemo(() => {
    let rows = [...(reconcile?.comparison_rows || [])]
    if (differenceFilter !== 'all') {
      rows = rows.filter((row) => {
        const diff = Math.abs(Number(row.difference || 0))
        if (differenceFilter === 'exact') return diff < 0.5
        if (differenceFilter === 'near') return diff >= 0.5 && diff <= 5000
        if (differenceFilter === 'mismatch') return diff > 5000
        return true
      })
    }
    if (statusFilter !== 'all') rows = rows.filter((row) => row.status === statusFilter)
    return rows
  }, [differenceFilter, reconcile, statusFilter])

  const cards = [
    { key: 'income', label: 'TỔNG THU', value: data?.total_income, icon: TrendingUp },
    { key: 'expense', label: 'TỔNG CHI', value: data?.total_expense, icon: TrendingDown },
    { key: 'tip', label: 'TIỀN TIP TRONG KỲ', value: data?.period_tip, icon: CircleDollarSign },
    { key: 'balance', label: 'CÒN LẠI', value: data?.balance, icon: WalletCards },
  ]
  const entryUrl = data?.entry_form_url || fallbackEntryUrl
  const reportUrl = data?.report_url || ''
  const canEditTip = Boolean(data?.can_edit_tip)
  const overallStatus = reconcile?.overall_status || 'KHỚP'
  const overallClass = overallStatus === 'KHỚP' ? 'ok' : overallStatus === 'GẦN KHỚP' ? 'near' : 'bad'

  return <div className="feature-page revenue-page">
    <style>{`
      .revenue-page .revenue-source{display:flex;gap:8px;align-items:center;color:#68736f;font-size:13px}
      .revenue-period{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:14px}
      .revenue-period-card{display:flex;align-items:center;gap:12px;padding:14px 16px;border:1px solid #dfe7e2;border-radius:15px;background:#fff}
      .revenue-period-card svg{color:#8b6b22;flex:0 0 auto}.revenue-period-card span{display:block;font-size:11px;font-weight:900;letter-spacing:.05em;color:#68736f;text-transform:uppercase}.revenue-period-card strong{display:block;margin-top:3px;font-size:18px;color:#173329}
      .revenue-actions{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}.revenue-action-link{display:inline-flex;align-items:center;justify-content:center;gap:8px;text-decoration:none;min-height:43px}.revenue-action-link.disabled{opacity:.45;pointer-events:none}
      .revenue-tip-editor{display:grid;grid-template-columns:minmax(220px,380px) auto 1fr;gap:10px;align-items:end;margin-bottom:14px;padding:14px;border:1px solid #dfd5b9;border-radius:15px;background:#fffaf0}.revenue-tip-editor label{display:grid;gap:5px;font-size:12px;font-weight:900}.revenue-tip-editor input{font-size:18px;font-weight:800;text-align:right}.revenue-tip-editor small{color:#75694d;line-height:1.45}
      .revenue-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.revenue-card{padding:22px;border:1px solid #dfe7e2;border-radius:18px;background:#fff;min-width:0}.revenue-card-head{display:flex;align-items:center;gap:9px;color:#5d6f66;font-size:12px;font-weight:900;letter-spacing:.05em}.revenue-card-value{margin-top:14px;font-size:30px;line-height:1.05;font-weight:900;color:#173329;overflow-wrap:anywhere}.revenue-card.tip{background:#fffaf0;border-color:#e4d5ad}.revenue-card.balance{background:#f3f8f5;border-color:#cbded3}
      .revenue-formula{margin-top:14px;padding:12px 14px;border:1px solid #cbded3;border-radius:13px;background:#f3f8f5;color:#244a3a;font-size:13px;font-weight:800;text-align:center}.revenue-meta{margin-top:10px;padding:12px 14px;border:1px solid #e4eae6;border-radius:13px;background:#fafcfb;color:#68736f;font-size:12px}
      .reconcile-panel{margin-top:20px;padding:16px;border:1px solid #dfe7e2;border-radius:18px;background:#fff}.reconcile-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:14px}.reconcile-head h2{margin:3px 0 0;font-size:20px;color:#173329}.reconcile-head p{margin:4px 0 0;color:#68736f;font-size:12px;max-width:850px}.reconcile-filter{display:flex;align-items:end;gap:8px;flex-wrap:wrap}.reconcile-filter label{display:grid;gap:5px;font-size:11px;font-weight:900;color:#53635c}.reconcile-filter select,.reconcile-filter input{min-height:40px;min-width:145px}
      .reconcile-status{display:flex;gap:10px;align-items:flex-start;padding:12px 14px;border-radius:13px;margin-bottom:12px;font-weight:800;font-size:13px}.reconcile-status.ok{background:#eef8f1;border:1px solid #bdd9c6;color:#245b38}.reconcile-status.near{background:#fffbea;border:1px solid #e9d982;color:#7a6500}.reconcile-status.bad{background:#fff0ed;border:1px solid #efb0a5;color:#8d291d}.reconcile-status svg{flex:0 0 auto;margin-top:1px}
      .reconcile-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:14px}.reconcile-kpi{padding:13px;border:1px solid #e1e7e3;border-radius:14px;background:#fafcfb}.reconcile-kpi span{display:block;font-size:10px;font-weight:900;color:#69766f;letter-spacing:.04em}.reconcile-kpi strong{display:block;margin-top:5px;font-size:19px;color:#173329}.reconcile-kpi.near strong{color:#806800}.reconcile-kpi.bad strong{color:#a13c2f}
      .comparison-filter-bar{display:flex;gap:8px;align-items:end;flex-wrap:wrap;padding:10px 12px;border-bottom:1px solid #e7ece9;background:#fbfcfb}.comparison-filter-bar label{display:grid;gap:4px;font-size:10px;font-weight:900;color:#5d6b64}.comparison-filter-bar select{min-height:36px;min-width:150px}.comparison-filter-bar small{margin-left:auto;color:#6c7772}
      .reconcile-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}.report-box{min-width:0;border:1px solid #e2e8e4;border-radius:14px;overflow:hidden}.report-box h3{display:flex;gap:8px;align-items:center;margin:0;padding:11px 13px;background:#f5f8f6;color:#24473a;font-size:13px}.report-scroll{overflow:auto;max-height:430px}.report-table{width:100%;border-collapse:collapse;min-width:650px;font-size:12px}.comparison-table{min-width:1050px}.report-table th,.report-table td{padding:8px 9px;border-bottom:1px solid #edf1ee;white-space:nowrap;text-align:left;vertical-align:top}.report-table th{position:sticky;top:0;background:#f9fbfa;z-index:1;font-size:10px;color:#5e6d66;text-transform:uppercase}.report-table .money{text-align:right;font-variant-numeric:tabular-nums}.report-table .detail-cell{white-space:normal;min-width:330px;line-height:1.45}.report-table .detail-cell div+div{margin-top:4px}.report-table tr.mismatch td{background:#fff2ef}.report-table tr.near td{background:#fffceb}.report-table tr.match td{background:#f5fbf7}.report-table tr.purchase-row td{font-weight:700}.status-match{color:#24703e;font-weight:900}.status-near{color:#806800;font-weight:900}.status-mismatch{color:#a13c2f;font-weight:900}
      @media(max-width:1150px){.reconcile-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}}
      @media(max-width:1050px){.revenue-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.reconcile-grid{grid-template-columns:1fr}}
      @media(max-width:760px){.revenue-period{grid-template-columns:1fr}.revenue-actions{display:grid;grid-template-columns:1fr 1fr}.revenue-tip-editor{grid-template-columns:1fr}.revenue-tip-editor button{width:100%}.revenue-grid{grid-template-columns:1fr;gap:9px}.revenue-card{padding:15px;border-radius:14px}.revenue-card-value{margin-top:8px;font-size:24px}.revenue-page .page-heading{align-items:flex-start}.reconcile-head{display:grid}.reconcile-filter,.comparison-filter-bar{display:grid;grid-template-columns:1fr 1fr}.reconcile-filter label:first-child{grid-column:1/-1}.reconcile-filter select,.reconcile-filter input,.comparison-filter-bar select{width:100%;min-width:0}.comparison-filter-bar small{margin:0;grid-column:1/-1}.reconcile-kpis{grid-template-columns:1fr 1fr}}
      @media(max-width:460px){.revenue-actions{grid-template-columns:1fr}.reconcile-filter,.comparison-filter-bar,.reconcile-kpis{grid-template-columns:1fr}.reconcile-filter label:first-child,.comparison-filter-bar small{grid-column:auto}}
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
        <div><span className="eyebrow"><FileSpreadsheet size={14}/> Đối chiếu chi mua hàng</span><h2>BÁO CÁO MUA HÀNG ↔ QUẢN LÝ THU CHI</h2><p>So sánh từng ngày: tổng cột Thành Tiền của BaoCaoMuaHang với các dòng Input có B = Chi và nội dung mua hàng, số tiền lấy từ cột C. Chênh lệch từ 1đ đến 5.000đ được xếp GẦN KHỚP; trên 5.000đ là KHÔNG KHỚP.</p></div>
        <div className="reconcile-filter">
          <label>Bộ lọc thời gian<select value={filterPreset} onChange={(event) => setFilterPreset(event.target.value)}>{reconcileFilters.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
          {filterPreset === 'custom' && <><label>Từ ngày<VeraDateInput aria-label="Từ ngày" value={customStart} onChange={(event) => setCustomStart(event.target.value)} /></label><label>Đến ngày<VeraDateInput aria-label="Đến ngày" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} /></label></>}
        </div>
      </div>

      {filterPreset === 'custom' && (!customStart || !customEnd) && <div className="revenue-meta">Chọn đủ Từ ngày và Đến ngày để xem hai báo cáo.</div>}
      {reconcileError && <div className="error-box">{reconcileError}</div>}
      {reconcileBusy && !reconcile && <div className="revenue-meta">Đang đọc BaoCaoMuaHang và Quản lý Thu Chi…</div>}

      {reconcile && <>
        <div className={`reconcile-status ${overallClass}`}>
          {overallStatus === 'KHỚP' ? <CheckCircle2 size={19}/> : <AlertTriangle size={19}/>}
          <div>{overallStatus === 'KHỚP'
            ? `KHỚP: Tất cả ngày đều không có chênh lệch trong ${reconcile.start_date_label} – ${reconcile.end_date_label}.`
            : overallStatus === 'GẦN KHỚP'
              ? `GẦN KHỚP: Có ${Number(reconcile.near_match_count || 0)} ngày chênh lệch không quá 5.000đ và không có ngày nào vượt 5.000đ.`
              : `KHÔNG KHỚP: Có ${Number(reconcile.mismatch_count || 0)} ngày chênh lệch trên 5.000đ trong ${reconcile.start_date_label} – ${reconcile.end_date_label}.`}</div>
        </div>

        <div className="reconcile-kpis">
          <article className="reconcile-kpi"><span>BAOCAOMUAHANG · THÀNH TIỀN</span><strong>{money(reconcile.purchase_total)}</strong></article>
          <article className="reconcile-kpi"><span>THU CHI · CHI MUA HÀNG</span><strong>{money(reconcile.ledger_purchase_total)}</strong></article>
          <article className={`reconcile-kpi ${Math.abs(Number(reconcile.difference || 0)) > 5000 ? 'bad' : Math.abs(Number(reconcile.difference || 0)) >= 0.5 ? 'near' : ''}`}><span>CHÊNH LỆCH TỔNG</span><strong>{money(reconcile.difference)}</strong></article>
          <article className={`reconcile-kpi ${Number(reconcile.near_match_count || 0) ? 'near' : ''}`}><span>SỐ NGÀY GẦN KHỚP</span><strong>{Number(reconcile.near_match_count || 0).toLocaleString('vi-VN')}</strong></article>
          <article className={`reconcile-kpi ${Number(reconcile.mismatch_count || 0) ? 'bad' : ''}`}><span>SỐ NGÀY KHÔNG KHỚP</span><strong>{Number(reconcile.mismatch_count || 0).toLocaleString('vi-VN')}</strong></article>
        </div>

        <div className="report-box">
          <h3><CalendarDays size={16}/> ĐỐI CHIẾU THEO NGÀY</h3>
          <div className="comparison-filter-bar">
            <label>Chênh lệch<select value={differenceFilter} onChange={(event) => setDifferenceFilter(event.target.value)}>{differenceFilters.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>Trạng thái<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>{statusFilters.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <small>Hiển thị <strong>{comparisonRows.length}</strong>/{(reconcile.comparison_rows || []).length} ngày.</small>
          </div>
          <div className="report-scroll"><table className="report-table comparison-table"><thead><tr><th>Ngày</th><th className="money">BaoCaoMuaHang</th><th className="money">Thu Chi · Mua hàng</th><th className="money">Chênh lệch</th><th>Trạng thái</th><th>Chi tiết nội dung</th></tr></thead><tbody>
            {comparisonRows.map((row) => <tr key={row.date} className={statusClass(row.status)}><td>{row.date_label}</td><td className="money">{money(row.purchase_total)}</td><td className="money">{money(row.ledger_purchase_total)}</td><td className="money">{money(row.difference)}</td><td className={statusTextClass(row.status)}>{row.status || '—'}</td><td className="detail-cell"><div><strong>BaoCaoMuaHang:</strong> {row.purchase_detail_text || '—'}</div><div><strong>Thu Chi:</strong> {row.ledger_detail_text || '—'}</div></td></tr>)}
            {!comparisonRows.length && <tr><td colSpan="6">Không có dữ liệu phù hợp với bộ lọc Chênh lệch / Trạng thái.</td></tr>}
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

        <div className="revenue-meta">Ngày trong Quản lý Thu Chi ưu tiên lấy từ ngày ghi trong cột Ghi chú, sau đó mới dùng cột Ngày giao dịch. Khi phát hiện một ngày có trạng thái <strong>KHÔNG KHỚP</strong> hoặc số liệu của ngày KHÔNG KHỚP thay đổi, hệ thống tự gửi Web Push chi tiết cho <strong>Admin, Quản lý và Lễ tân</strong>; cùng một trạng thái/số liệu sẽ không gửi lặp lại chỉ vì làm mới trang.</div>
      </>}
    </section>
  </div>
}
