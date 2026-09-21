import { AlertTriangle, CalendarDays, CheckCircle2, CircleDollarSign, Download, FileSpreadsheet, RefreshCw, Save, TrendingDown, TrendingUp, WalletCards } from 'lucide-react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'
import { defaultRevenueTipStart, revenueTipTotal } from '../lib/revenueTipPeriod'
import './RevenuePage.css'
import VeraDateInput from '../components/VeraDateInput'
import VeraMoneyInput from '../components/VeraMoneyInput'
import { formatVeraDate } from '../lib/veraDate'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const money = (value) => `${Math.round(Number(value || 0)).toLocaleString('vi-VN')}đ`
const numberText = (value) => Number(value || 0).toLocaleString('vi-VN', { maximumFractionDigits: 2 })
const reconcileFilters = [
  ['all', 'Tất cả'],
  ['yesterday', 'Hôm qua'],
  ['today', 'Hôm nay'],
  ['last_week', 'Tuần trước'],
  ['this_week', 'Tuần này'],
  ['last_month', 'Tháng trước'],
  ['this_month', 'Tháng này'],
  ['next_month', 'Tháng sau'],
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

async function loadRevenue({ source = 'manual', timeRange = 'all', start = '', end = '', signal }) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const params = new URLSearchParams({ source, time_range: timeRange })
  if (timeRange === 'custom') { if (start) params.set('start', start); if (end) params.set('end', end) }
  const response = await fetch(`${apiBase}/v2/revenue/summary?${params.toString()}`, { signal, headers: await authorizedHeaders() })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

async function loadLiveTourReports(signal) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const response = await fetch(`${apiBase}/v2/live-tour/reports`, { signal, headers: await authorizedHeaders() })
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

async function saveRevenueEntry({ transactionDate, incomeAmount, incomeNote, expenseAmount, expenseNote, confirmDuplicate = false }) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const response = await fetch(`${apiBase}/v2/revenue/entry`, {
    method: 'POST',
    headers: await authorizedHeaders(true),
    body: JSON.stringify({
      transaction_date: transactionDate,
      income_amount: Number(incomeAmount || 0),
      income_note: String(incomeNote || '').trim(),
      expense_amount: Number(expenseAmount || 0),
      expense_note: String(expenseNote || '').trim(),
      confirm_duplicate: Boolean(confirmDuplicate),
    }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = payload.detail
    const error = new Error((typeof detail === 'object' ? detail?.message : detail) || payload.message || `HTTP ${response.status}`)
    error.status = response.status
    error.code = typeof detail === 'object' ? detail?.code : ''
    throw error
  }
  return payload
}

async function updateRevenueEntry(id, body) {
  const response = await fetch(`${apiBase}/v2/revenue/entries/${encodeURIComponent(id)}`, { method: 'PATCH', headers: await authorizedHeaders(true), body: JSON.stringify(body) })
  const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`); return payload
}

async function deleteRevenueEntry(id) {
  const response = await fetch(`${apiBase}/v2/revenue/entries/${encodeURIComponent(id)}`, { method: 'DELETE', headers: await authorizedHeaders() })
  const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`); return payload
}

async function savePeriodTip(amount, startDate, endDate) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const response = await fetch(`${apiBase}/v2/revenue/tip`, {
    method: 'PUT',
    headers: await authorizedHeaders(true),
    body: JSON.stringify({ amount: Number(amount || 0), start_date: startDate || null, end_date: endDate || null }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

const defaultRevenueNote = (kind, transactionDate) => `${kind} ${formatVeraDate(transactionDate) || ''}`.trim()

function AutoFitMoney({ children }) {
  const ref = useRef(null)
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return undefined
    const fit = () => {
      let size = 30
      element.style.fontSize = `${size}px`
      while (size > 14 && element.scrollWidth > element.clientWidth) {
        size -= 1
        element.style.fontSize = `${size}px`
      }
    }
    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(element)
    return () => observer.disconnect()
  }, [children])
  return <div ref={ref} className="revenue-card-value">{children}</div>
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

export default function RevenuePage({ user }) {
  const [data, setData] = useState(null)
  const [tip, setTip] = useState(0)
  const [tipStart, setTipStart] = useState('')
  const [tipEnd, setTipEnd] = useState('')
  const [tipRows, setTipRows] = useState(null)
  const [tipLoadError, setTipLoadError] = useState('')
  const [busy, setBusy] = useState(false)
  const [savingTip, setSavingTip] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [revision, setRevision] = useState(0)
  const [revenueSource, setRevenueSource] = useState('manual')
  const [summaryRange, setSummaryRange] = useState('all')
  const [summaryStart, setSummaryStart] = useState('')
  const [summaryEnd, setSummaryEnd] = useState('')
  const [entryDate, setEntryDate] = useState(() => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }))
  const [entryIncomeAmount, setEntryIncomeAmount] = useState('')
  const [entryIncomeNote, setEntryIncomeNote] = useState('')
  const [incomeNoteEdited, setIncomeNoteEdited] = useState(false)
  const [entryExpenseAmount, setEntryExpenseAmount] = useState('')
  const [entryExpenseNote, setEntryExpenseNote] = useState('')
  const [expenseNoteEdited, setExpenseNoteEdited] = useState(false)
  const [savingEntry, setSavingEntry] = useState(false)
  const [filterPreset, setFilterPreset] = useState('this_month')
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')
  const [reconcile, setReconcile] = useState(null)
  const [reconcileBusy, setReconcileBusy] = useState(false)
  const [reconcileError, setReconcileError] = useState('')
  const [differenceFilter, setDifferenceFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [purchaseDate, setPurchaseDate] = useState('')
  const [ledgerDate, setLedgerDate] = useState('')
  const [ledgerType, setLedgerType] = useState('')
  const [activeTab, setActiveTab] = useState('ledger')
  const [detailPreset, setDetailPreset] = useState('this_month')
  const [detailStart, setDetailStart] = useState('')
  const [detailEnd, setDetailEnd] = useState('')
  const [detailData, setDetailData] = useState(null)
  const [detailBusy, setDetailBusy] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [exportingLedger, setExportingLedger] = useState(false)
  const [ledgerNoteFilter, setLedgerNoteFilter] = useState('')
  const [ledgerAmountFilter, setLedgerAmountFilter] = useState('')
  const [purchaseItemFilter, setPurchaseItemFilter] = useState('')
  const [purchaseBuyerFilter, setPurchaseBuyerFilter] = useState('')
  const [purchaseUserFilter, setPurchaseUserFilter] = useState('')
  const role = String(user?.role || '').trim().toLowerCase()
  const canViewAdminRevenueSummary = role === 'admin' || role === 'giamdoc'
  const isAdmin = role === 'admin'
  const autoMode = isAdmin && revenueSource === 'auto'
  useEffect(() => {
    if (!canViewAdminRevenueSummary && activeTab === 'overview') setActiveTab('ledger')
  }, [activeTab, canViewAdminRevenueSummary])
  const purchaseRows = (detailData?.purchase_rows || []).filter(row => {
    const item = String(row.item || '').toLocaleLowerCase('vi')
    const buyer = String(row.buyer || '').toLocaleLowerCase('vi')
    const rowUser = String(row.user || '').toLocaleLowerCase('vi')
    return (!purchaseDate || row.date === purchaseDate)
      && (!purchaseItemFilter || item.includes(purchaseItemFilter.toLocaleLowerCase('vi')))
      && (!purchaseBuyerFilter || buyer.includes(purchaseBuyerFilter.toLocaleLowerCase('vi')))
      && (!purchaseUserFilter || rowUser.includes(purchaseUserFilter.toLocaleLowerCase('vi')))
  })
  const ledgerRows = (detailData?.ledger_rows || []).filter(row => {
    const note = String(row.note || '').toLocaleLowerCase('vi')
    const amountText = String(Math.round(Number(row.amount || 0)))
    const wantedAmount = String(ledgerAmountFilter || '').replace(/\D/g, '')
    return (!ledgerDate || row.date === ledgerDate)
      && (!ledgerType || row.type === ledgerType)
      && (!ledgerNoteFilter || note.includes(ledgerNoteFilter.toLocaleLowerCase('vi')))
      && (!wantedAmount || amountText.includes(wantedAmount))
  })
  const ledgerTotals = ledgerRows.reduce((totals, row) => {
    const type = String(row.type || '').trim().toLocaleLowerCase('vi')
    const amount = Number(row.amount || 0)
    if (type === 'thu' || type.includes('doanh thu')) totals.income += amount
    if (type === 'chi' || type.includes('chi phí')) totals.expense += amount
    return totals
  }, { income: 0, expense: 0 })
  const ledgerTypes = [...new Set((detailData?.ledger_rows || []).map(row => row.type).filter(Boolean))]

  useEffect(() => {
    if (!incomeNoteEdited) setEntryIncomeNote(defaultRevenueNote('Doanh thu', entryDate))
    if (!expenseNoteEdited) setEntryExpenseNote(defaultRevenueNote('Chi phí', entryDate))
  }, [entryDate, expenseNoteEdited, incomeNoteEdited])

  useEffect(() => {
    const controller = new AbortController()
    const run = async () => {
      setBusy(true)
      setError('')
      setTipLoadError('')
      setTipRows(null)
      try {
        const result = await loadRevenue({ source: revenueSource, timeRange: summaryRange, start: summaryStart, end: summaryEnd, signal: controller.signal })
        let liveTourRows = null
        try {
          const liveTour = await loadLiveTourReports(controller.signal)
          liveTourRows = Array.isArray(liveTour?.reports) ? liveTour.reports : []
        } catch (tipError) {
          if (tipError?.name === 'AbortError') throw tipError
          if (!controller.signal.aborted) {
            setTipLoadError(tipError?.message || 'Không lấy được dữ liệu TIP từ Live Tour.')
          }
        }
        if (!controller.signal.aborted) {
          const defaultTipStartDate = defaultRevenueTipStart(result.current_date)
            || result.period_tip_start || result.start_date || ''
          const defaultTipEndDate = result.current_date || result.period_tip_end || ''
          const autoTip = Array.isArray(liveTourRows)
            ? revenueTipTotal(liveTourRows, defaultTipStartDate, defaultTipEndDate)
            : Number(result.period_tip || 0)
          const balance = Math.round((Number(result.total_income || 0) - Number(result.total_expense || 0) - autoTip) * 100) / 100
          setData({
            ...result,
            period_tip: autoTip,
            balance,
            period_tip_start: defaultTipStartDate,
            period_tip_end: defaultTipEndDate,
          })
          setTipRows(liveTourRows)
          setTip(autoTip)
          setTipStart(defaultTipStartDate)
          setTipEnd(defaultTipEndDate)
        }
      } catch (err) {
        if (!controller.signal.aborted && err?.name !== 'AbortError') setError(err.message || 'Không tải được Doanh thu.')
      } finally {
        if (!controller.signal.aborted) setBusy(false)
      }
    }
    void run()
    return () => controller.abort()
  }, [revenueSource, summaryEnd, summaryRange, summaryStart, revision])

  useEffect(() => {
    if (!Array.isArray(tipRows) || !tipStart || !tipEnd || tipStart > tipEnd) return
    const autoTip = revenueTipTotal(tipRows, tipStart, tipEnd)
    setTip(autoTip)
    setData((current) => {
      if (!current) return current
      const balance = Math.round((Number(current.total_income || 0) - Number(current.total_expense || 0) - autoTip) * 100) / 100
      return {
        ...current,
        period_tip: autoTip,
        balance,
        period_tip_start: tipStart,
        period_tip_end: tipEnd,
      }
    })
  }, [tipEnd, tipRows, tipStart])

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

  useEffect(() => {
    if (detailPreset === 'custom' && (!detailStart || !detailEnd)) {
      setDetailData(null)
      setDetailError('')
      return undefined
    }
    const controller = new AbortController()
    const run = async () => {
      setDetailBusy(true)
      setDetailError('')
      try {
        const result = await loadPurchaseReconcile({ preset: detailPreset, start: detailStart, end: detailEnd, signal: controller.signal })
        if (!controller.signal.aborted) setDetailData(result)
      } catch (err) {
        if (!controller.signal.aborted && err?.name !== 'AbortError') setDetailError(err.message || 'Không tải được dữ liệu chi tiết.')
      } finally {
        if (!controller.signal.aborted) setDetailBusy(false)
      }
    }
    void run()
    return () => controller.abort()
  }, [detailPreset, detailStart, detailEnd, revision])

  const submitTip = async () => {
    setSavingTip(true)
    setError('')
    setNotice('')
    try {
      if (!Number.isFinite(Number(tip)) || Number(tip) < 0) throw new Error('Tiền TIP trong kỳ phải là số không âm.')
      if (!tipStart || !tipEnd) throw new Error('Chọn đủ Ngày bắt đầu và Đến ngày cho Tiền TIP trong kỳ.')
      if (tipStart > tipEnd) throw new Error('Ngày bắt đầu Tiền TIP không được sau Đến ngày.')
      const result = await savePeriodTip(tip, tipStart, tipEnd)
      setData((current) => current ? ({ ...current, period_tip: result.period_tip, balance: result.balance, period_tip_start: result.period_tip_start, period_tip_end: result.period_tip_end }) : current)
      setTip(Number(result.period_tip || 0))
      setTipStart(result.period_tip_start || tipStart)
      setTipEnd(result.period_tip_end || tipEnd)
      setNotice(result.message || 'Đã lưu Tiền TIP trong kỳ.')
    } catch (err) {
      setError(err.message || 'Không lưu được Tiền TIP trong kỳ.')
    } finally {
      setSavingTip(false)
    }
  }

  const submitRevenueEntry = async (event) => {
    event?.preventDefault?.()
    setSavingEntry(true)
    setError('')
    setNotice('')
    try {
      if (!entryDate) throw new Error('Hãy chọn ngày giao dịch.')
      const incomeAmount = Number(entryIncomeAmount || 0)
      const expenseAmount = Number(entryExpenseAmount || 0)
      if (!Number.isFinite(incomeAmount) || incomeAmount < 0) throw new Error('Số tiền Thu không hợp lệ.')
      if (!Number.isFinite(expenseAmount) || expenseAmount < 0) throw new Error('Số tiền Chi không hợp lệ.')
      if (incomeAmount <= 0 && expenseAmount <= 0) throw new Error('Hãy nhập ít nhất một số tiền Thu hoặc Chi lớn hơn 0.')
      const entryPayload = {
        transactionDate: entryDate,
        incomeAmount,
        incomeNote: entryIncomeNote,
        expenseAmount,
        expenseNote: entryExpenseNote,
      }
      let result
      try {
        result = await saveRevenueEntry(entryPayload)
      } catch (saveError) {
        if (saveError?.status !== 409 || saveError?.code !== 'duplicate_revenue_entry') throw saveError
        if (!window.confirm(saveError.message)) return
        result = await saveRevenueEntry({ ...entryPayload, confirmDuplicate: true })
      }
      setEntryIncomeAmount('')
      setEntryExpenseAmount('')
      setIncomeNoteEdited(false)
      setExpenseNoteEdited(false)
      setEntryIncomeNote(defaultRevenueNote('Doanh thu', entryDate))
      setEntryExpenseNote(defaultRevenueNote('Chi phí', entryDate))
      setNotice(result.message || 'Đã ghi Thu Chi vào Chi tiết Doanh thu - Chi phí.')
      setRevision((value) => value + 1)
    } catch (err) {
      setError(err.message || 'Không ghi được Thu Chi.')
    } finally {
      setSavingEntry(false)
    }
  }

  const exportLedger = async () => {
    setExportingLedger(true)
    setDetailError('')
    try {
      const params = new URLSearchParams({ preset: detailPreset })
      if (detailPreset === 'custom') {
        if (detailStart) params.set('start', detailStart)
        if (detailEnd) params.set('end', detailEnd)
      }
      if (ledgerDate) params.set('transaction_date', ledgerDate)
      if (ledgerType) params.set('transaction_type', ledgerType)
      if (ledgerAmountFilter) params.set('amount', ledgerAmountFilter)
      if (ledgerNoteFilter) params.set('note', ledgerNoteFilter)
      const response = await fetch(`${apiBase}/v2/revenue/ledger/export.xlsx?${params}`, { headers: await authorizedHeaders() })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `VERA_DoanhThu_ChiPhi_${detailData?.start_date_label || ''}_${detailData?.end_date_label || ''}.xlsx`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      setDetailError(err.message || 'Không xuất được file Excel Doanh thu-Chi phí.')
    } finally {
      setExportingLedger(false)
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
    { key: 'net', label: 'TỔNG THU - TỔNG CHI', value: data?.net_income ?? (Number(data?.total_income || 0) - Number(data?.total_expense || 0)), icon: WalletCards },
    { key: 'tip', label: 'TIỀN TIP TRONG KỲ', value: data?.period_tip, icon: CircleDollarSign },
    { key: 'balance', label: 'CÒN LẠI', value: data?.balance, icon: WalletCards },
  ]
  const canEditTip = Boolean(data?.can_edit_tip)
  const canCreateEntry = Boolean(data?.can_create_entry)
  const overallStatus = reconcile?.overall_status || 'KHỚP'
  const overallClass = overallStatus === 'KHỚP' ? 'ok' : overallStatus === 'GẦN KHỚP' ? 'near' : 'bad'

  return <div className="feature-page revenue-page">
    <style>{`
      .revenue-page .revenue-source{display:flex;gap:8px;align-items:center;color:#68736f;font-size:13px}
      .revenue-period{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:14px}
      .revenue-period-card{display:flex;align-items:center;gap:12px;padding:14px 16px;border:1px solid #dfe7e2;border-radius:15px;background:#fff}
      .revenue-period-card svg{color:#8b6b22;flex:0 0 auto}.revenue-period-card span{display:block;font-size:11px;font-weight:900;letter-spacing:.05em;color:#68736f;text-transform:uppercase}.revenue-period-card strong{display:block;margin-top:3px;font-size:18px;color:#173329}
      .revenue-actions{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}.revenue-action-link{display:inline-flex;align-items:center;justify-content:center;gap:8px;text-decoration:none;min-height:43px}.revenue-action-link.disabled{opacity:.45;pointer-events:none}
      .revenue-entry-form{display:grid;grid-template-columns:minmax(180px,.75fr) minmax(170px,.75fr) minmax(260px,1.5fr) auto;grid-template-areas:"title title title title" "date date date save" "income income-note income-note income-note" "expense expense-note expense-note expense-note";gap:10px;align-items:end;margin-bottom:14px;padding:14px;border:1px solid #cbded3;border-radius:15px;background:#f5faf7}.revenue-entry-form h2{grid-area:title;margin:0;color:#173329;font-size:18px}.revenue-entry-form label{display:grid;gap:5px;font-size:12px;font-weight:900;color:#425c51}.revenue-entry-form input{min-height:42px}.revenue-entry-form .entry-date{grid-area:date}.revenue-entry-form .entry-amount:not(.entry-expense){grid-area:income}.revenue-entry-form .entry-note:not(.entry-expense-note){grid-area:income-note}.revenue-entry-form .entry-expense{grid-area:expense}.revenue-entry-form .entry-expense-note{grid-area:expense-note}.revenue-entry-form .entry-amount input{text-align:right;font-weight:850}.revenue-entry-form .entry-expense input{background:#fff4e5;border-color:#d99145}.revenue-entry-form .entry-expense-note input{background:#fff8ee;border-color:#d9a86f}.revenue-entry-form button{grid-area:save;min-height:42px;white-space:nowrap}.revenue-entry-help{grid-column:1/-1;margin:0;color:#66776f;font-size:11px}
      .revenue-tip-editor{display:grid;grid-template-columns:minmax(230px,1.45fr) minmax(155px,.9fr) minmax(155px,.9fr) minmax(190px,1fr) auto;gap:10px;align-items:end;margin-bottom:14px;padding:14px;border:1px solid #dfd5b9;border-radius:15px;background:#fffaf0}.revenue-tip-editor label{display:grid;gap:5px;font-size:12px;font-weight:900;min-width:0}.revenue-tip-editor input{font-size:16px;font-weight:800;min-width:0}.revenue-tip-editor .revenue-tip-amount input{text-align:right;font-size:18px}.revenue-tip-editor small{grid-column:1/-1;color:#75694d;line-height:1.45}.revenue-tip-current{display:flex;align-items:center;justify-content:space-between;gap:6px;min-height:42px;padding:0 8px;border:1px solid #dfd5b9;border-radius:10px;background:#fff;color:#75694d;font-size:11px;font-weight:900;white-space:nowrap}.revenue-tip-current button{min-height:30px;padding:4px 8px;font-size:11px;white-space:nowrap}
      .revenue-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}.revenue-card{padding:18px;border:1px solid #dfe7e2;border-radius:18px;background:#fff;min-width:0}.revenue-card-head{display:flex;align-items:center;gap:9px;color:#5d6f66;font-size:12px;font-weight:900;letter-spacing:.05em}.revenue-card-value{width:100%;min-width:0;margin-top:14px;font-size:30px;line-height:1.05;font-weight:900;color:#173329;white-space:nowrap;overflow:hidden;font-variant-numeric:tabular-nums}.revenue-card.net{background:#f7faf8;border-color:#d2e0d8}.revenue-card.tip{background:#fffaf0;border-color:#e4d5ad}.revenue-card.balance{background:#f3f8f5;border-color:#cbded3}
      .revenue-formula{margin-top:14px;padding:12px 14px;border:1px solid #cbded3;border-radius:13px;background:#f3f8f5;color:#244a3a;font-size:13px;font-weight:800;text-align:center}.revenue-meta{margin-top:10px;padding:12px 14px;border:1px solid #e4eae6;border-radius:13px;background:#fafcfb;color:#68736f;font-size:12px}
      .reconcile-panel{margin-top:20px;padding:16px;border:1px solid #dfe7e2;border-radius:18px;background:#fff}.reconcile-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:14px}.reconcile-head h2{margin:3px 0 0;font-size:20px;color:#173329}.reconcile-head p{margin:4px 0 0;color:#68736f;font-size:12px;max-width:850px}.reconcile-filter{display:flex;align-items:end;gap:8px;flex-wrap:wrap}.reconcile-filter label{display:grid;gap:5px;font-size:11px;font-weight:900;color:#53635c}.reconcile-filter select,.reconcile-filter input{min-height:40px;min-width:145px}
      .reconcile-status{display:flex;gap:10px;align-items:flex-start;padding:12px 14px;border-radius:13px;margin-bottom:12px;font-weight:800;font-size:13px}.reconcile-status.ok{background:#eef8f1;border:1px solid #bdd9c6;color:#245b38}.reconcile-status.near{background:#fffbea;border:1px solid #e9d982;color:#7a6500}.reconcile-status.bad{background:#fff0ed;border:1px solid #efb0a5;color:#8d291d}.reconcile-status svg{flex:0 0 auto;margin-top:1px}
      .reconcile-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:14px}.reconcile-kpi{padding:13px;border:1px solid #e1e7e3;border-radius:14px;background:#fafcfb}.reconcile-kpi span{display:block;font-size:10px;font-weight:900;color:#69766f;letter-spacing:.04em}.reconcile-kpi strong{display:block;margin-top:5px;font-size:19px;color:#173329}.reconcile-kpi.near strong{color:#806800}.reconcile-kpi.bad strong{color:#a13c2f}
      .comparison-filter-bar{display:flex;gap:8px;align-items:end;flex-wrap:wrap;padding:10px 12px;border-bottom:1px solid #e7ece9;background:#fbfcfb}.comparison-filter-bar label{display:grid;gap:4px;font-size:10px;font-weight:900;color:#5d6b64}.comparison-filter-bar select{min-height:36px;min-width:150px}.comparison-filter-bar small{margin-left:auto;color:#6c7772}
      .revenue-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.revenue-tab{border:1px solid #b8d0c3;background:#fff;color:#24473a;border-radius:12px;padding:10px 14px;font-weight:900;cursor:pointer}.revenue-tab.active{background:#1f513f;color:#fff;border-color:#1f513f}.detail-tab-panel{margin-bottom:18px}.detail-filter-panel{display:grid;grid-template-columns:1.05fr 1fr 1fr;gap:10px;padding:14px;border:1px solid #cbded3;border-radius:15px;background:#f7faf8;margin-bottom:12px}.detail-filter-panel label{display:grid;gap:5px;font-size:11px;font-weight:900;color:#53635c}.detail-filter-panel input,.detail-filter-panel select{min-height:42px}.detail-filter-secondary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;grid-column:1/-1}.detail-filter-actions{display:flex;gap:8px;align-items:end;justify-content:flex-end;flex-wrap:wrap;grid-column:1/-1}.detail-filter-actions button{min-height:40px}.detail-filter-actions .active{background:#1f513f;color:#fff;border-color:#1f513f}.admin-revenue-summary{display:grid;gap:14px}
      .ledger-summary-head{display:flex;align-items:stretch;gap:10px;padding:10px 12px;background:#f5f8f6}.ledger-filter-total{display:flex;align-items:center;gap:9px;min-width:180px;padding:10px 13px;border:1px solid #cbded3;border-radius:12px;background:#fff}.ledger-filter-total.expense{border-color:#e1c49f;background:#fffaf2}.ledger-filter-total svg{color:#8b6b22;flex:0 0 auto}.ledger-filter-total span{display:block;font-size:10px;font-weight:900;color:#68736f;text-transform:uppercase}.ledger-filter-total strong{display:block;margin-top:2px;font-size:18px;color:#173329}.ledger-summary-head .ledger-export{margin-left:auto;align-self:center}
.report-box{min-width:0;max-width:100%;border:1px solid #e2e8e4;border-radius:14px;overflow:hidden}.report-box h3{display:flex;gap:8px;align-items:center;margin:0;padding:11px 13px;background:#f5f8f6;color:#24473a;font-size:13px}.report-scroll{width:100%;max-width:100%;overflow:auto;max-height:430px}.report-table{width:100%;border-collapse:collapse;min-width:650px;font-size:12px}.comparison-table{min-width:1050px}.report-table th,.report-table td{padding:8px 9px;border-bottom:1px solid #edf1ee;white-space:nowrap;text-align:left;vertical-align:top}.report-table th{position:sticky;top:0;background:#dcefe5;z-index:1;font-size:10px;color:#173b2e;text-transform:uppercase;border-bottom:2px solid #79a48e}.report-table .money{text-align:right;font-variant-numeric:tabular-nums}.report-table .detail-cell{white-space:normal;min-width:330px;line-height:1.45}.report-table .detail-cell div+div{margin-top:4px}.report-table tr.mismatch td{background:#fff2ef}.report-table tr.near td{background:#fffceb}.report-table tr.match td{background:#f5fbf7}.report-table tr.purchase-row td{font-weight:700}.status-match{color:#24703e;font-weight:900}.status-near{color:#806800;font-weight:900}.status-mismatch{color:#a13c2f;font-weight:900}
      @media(max-width:1250px){.revenue-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.reconcile-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}}
      @media(max-width:1050px){.revenue-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
      @media(max-width:760px){.revenue-page{overflow-x:hidden}.detail-filter-panel{grid-template-columns:1fr 1fr;padding:10px}.detail-filter-panel>label:first-child{grid-column:1/-1}.detail-filter-secondary{grid-template-columns:1fr 1fr}.detail-filter-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:stretch;justify-content:stretch}.detail-filter-actions button{width:100%;min-width:0;white-space:nowrap;font-size:12px;padding:8px 5px}.revenue-period{grid-template-columns:1fr}.revenue-actions{display:grid;grid-template-columns:1fr 1fr}.revenue-tip-editor{grid-template-columns:1fr}.revenue-tip-editor button{width:100%}.revenue-tip-current button{width:auto}.revenue-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.revenue-card{padding:13px;border-radius:14px}.revenue-card.balance{grid-column:1/-1}.revenue-card-value{margin-top:8px;font-size:clamp(16px,4.6vw,22px);white-space:nowrap}.revenue-page .page-heading{align-items:flex-start}.reconcile-head{display:grid}.reconcile-filter,.comparison-filter-bar{display:grid;grid-template-columns:1fr 1fr}.reconcile-filter label:first-child{grid-column:1/-1}.reconcile-filter select,.reconcile-filter input,.comparison-filter-bar select{width:100%;min-width:0}.comparison-filter-bar small{margin:0;grid-column:1/-1}.reconcile-kpis{grid-template-columns:1fr 1fr}.ledger-summary-head{display:grid;grid-template-columns:1fr 1fr}.ledger-filter-total{min-width:0}.ledger-summary-head .ledger-export{grid-column:1/-1;margin:0;width:100%}.ledger-table{min-width:0;table-layout:fixed;font-size:10px}.ledger-table th,.ledger-table td{padding:7px 5px;white-space:normal;overflow-wrap:break-word}.ledger-table th:nth-child(1){width:23%}.ledger-table th:nth-child(2){width:19%}.ledger-table th:nth-child(3){width:26%}.ledger-table th:nth-child(4){width:32%}.ledger-table th:nth-child(n+5),.ledger-table td:nth-child(n+5){display:none}.ledger-table .money{white-space:nowrap}.report-box h3{padding:10px;font-size:12px}.report-box h3 button{white-space:nowrap}}
      @media(max-width:760px){.detail-filter-actions{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important}.detail-filter-actions button{display:flex;align-items:center;justify-content:center;width:100%;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ledger-table{display:block;min-width:0;table-layout:auto}.ledger-table thead{display:none}.ledger-table tbody{display:grid;gap:10px;padding:10px}.ledger-table tr{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));border:1px solid #b8d0c3;border-radius:12px;overflow:hidden;background:#fff}.ledger-table td{display:grid!important;grid-template-columns:minmax(76px,.8fr) minmax(0,1.2fr);align-items:start;gap:6px;width:auto!important;padding:8px 9px;white-space:normal;overflow-wrap:anywhere;border:0;border-bottom:1px solid #e3ebe6;font-size:11px}.ledger-table td::before{content:attr(data-label);color:#476357;font-size:9px;font-weight:900;letter-spacing:.04em;text-transform:uppercase}.ledger-table td:nth-child(4){grid-column:1/-1}.ledger-table td:nth-last-child(-n+2){border-bottom:0}.ledger-table .money{text-align:left;white-space:normal}.ledger-table tr.purchase-row td{background:#f8fbf9}}
      @media(max-width:460px){.detail-filter-panel,.detail-filter-secondary{grid-template-columns:1fr}.detail-filter-panel>label:first-child{grid-column:auto}.revenue-actions{grid-template-columns:1fr}.revenue-entry-form{grid-template-columns:1fr;grid-template-areas:"title" "date" "income" "expense" "income-note" "expense-note" "save"}.reconcile-filter,.comparison-filter-bar,.reconcile-kpis{grid-template-columns:1fr}.reconcile-filter label:first-child,.comparison-filter-bar small{grid-column:auto}}
      @media(max-width:760px){.revenue-entry-form{grid-template-columns:1fr 1fr;grid-template-areas:"title title" "date date" "income income" "income-note income-note" "expense expense" "expense-note expense-note" "save save"}.revenue-entry-form .entry-date,.revenue-entry-form .entry-note,.revenue-entry-form button{grid-column:auto}.revenue-entry-form button{width:100%}}
      @media(max-width:460px){.revenue-entry-form{grid-template-columns:1fr;grid-template-areas:"title" "date" "income" "expense" "income-note" "expense-note" "save"}}
    `}</style>

    <div className="page-heading">
      <div><span className="eyebrow"><CircleDollarSign size={14} /> Tài chính</span><h1>DOANH THU</h1><p className="revenue-source">Dữ liệu Thu/Chi được lưu trực tiếp trên server VERA SPA.</p></div>
      <button className="secondary-button" type="button" onClick={() => { setNotice(''); setRevision((value) => value + 1) }} disabled={busy || reconcileBusy}><RefreshCw size={16} className={(busy || reconcileBusy) ? 'spin' : ''} /> Làm mới</button>
    </div>
    {error && <div className="error-box">{error}</div>}
    {notice && <div className="success-box">{notice}</div>}
    {tipLoadError && <div className="error-box">{tipLoadError}</div>}

    {canCreateEntry && <form className="revenue-entry-form" onSubmit={submitRevenueEntry}>
      <h2>NHẬP DOANH THU - CHI PHÍ</h2>
      <label className="entry-date">Ngày giao dịch<VeraDateInput value={entryDate} onChange={(event) => setEntryDate(event.target.value)} disabled={savingEntry}/></label>
      <label className="entry-amount">Số tiền Thu<VeraMoneyInput value={entryIncomeAmount} onChange={(event) => setEntryIncomeAmount(event.target.value)} placeholder="0" disabled={savingEntry}/></label>
      <label className="entry-note">Ghi chú Thu<input type="text" maxLength={1000} value={entryIncomeNote} onChange={(event) => { setIncomeNoteEdited(true); setEntryIncomeNote(event.target.value) }} placeholder="Doanh thu + ngày giao dịch" disabled={savingEntry}/><small>Có thể xóa để nhập nội dung Thu mới.</small></label>
      <label className="entry-amount entry-expense">Số tiền Chi<VeraMoneyInput value={entryExpenseAmount} onChange={(event) => setEntryExpenseAmount(event.target.value)} placeholder="0" disabled={savingEntry}/></label>
      <label className="entry-note entry-expense-note">Ghi chú Chi<input type="text" maxLength={1000} value={entryExpenseNote} onChange={(event) => { setExpenseNoteEdited(true); setEntryExpenseNote(event.target.value) }} placeholder="Chi phí + ngày giao dịch" disabled={savingEntry}/><small>Có thể xóa để nhập nội dung Chi mới.</small></label>
      <button type="submit" className="primary-button" disabled={savingEntry}><Save size={16}/>{savingEntry ? 'Đang ghi…' : 'Lưu Thu + Chi'}</button>
    </form>}

    {canViewAdminRevenueSummary && <section className="revenue-period" aria-label="Khoảng dữ liệu Doanh thu">
      <article className="revenue-period-card"><CalendarDays size={20} /><div><span>Ngày bắt đầu</span><strong>{busy && !data ? '…' : (data?.start_date_label || '—')}</strong></div></article>
      <article className="revenue-period-card"><CalendarDays size={20} /><div><span>Báo cáo tới ngày</span><strong>{busy && !data ? '…' : (data?.current_date_label || '—')}</strong></div></article>
    </section>}

    {canViewAdminRevenueSummary && canEditTip && <section className="revenue-tip-editor">
      <label className="revenue-tip-amount">TIỀN TIP TRONG KỲ<input type="text" inputMode="none" value={money(tip)} readOnly aria-label="Tiền TIP trong kỳ tự động" /></label>
      <label>Ngày bắt đầu<VeraDateInput aria-label="Ngày bắt đầu Tiền TIP" value={tipStart} max={tipEnd || data?.current_date || undefined} disabled={savingTip || busy} onChange={(event) => setTipStart(event.target.value)} /></label>
      <label>Đến ngày<VeraDateInput aria-label="Đến ngày Tiền TIP" value={tipEnd} min={tipStart || undefined} max={data?.current_date || undefined} disabled={savingTip || busy} onChange={(event) => setTipEnd(event.target.value)} /></label>
      <div className="revenue-tip-current">Báo cáo tới ngày: {data?.current_date_label || '—'} <button type="button" className="secondary-button" disabled={savingTip || busy || !data?.current_date} onClick={() => setTipEnd(data?.current_date || '')}>Dùng ngày này</button></div>
      <button type="button" className="primary-button" onClick={submitTip} disabled={savingTip || busy}><Save size={16}/> {savingTip ? 'Đang lưu…' : 'Lưu Tiền TIP'}</button>
      <small>Tiền TIP tự động cộng từ TIP của nhân viên trong báo cáo hóa đơn Live Tour theo đúng khoảng Ngày bắt đầu → Đến ngày. Kỳ 1 mặc định bắt đầu ngày 01, kỳ 2 mặc định bắt đầu ngày 16; Đến ngày mặc định bằng Ngày hiện tại. Đổi một trong hai ngày sẽ tự lọc và tính lại số TIP ngay.</small>
    </section>}

    {canViewAdminRevenueSummary && <div className="admin-revenue-summary">
      <section className="revenue-grid" aria-live="polite">
        {cards.map(({ key, label, value, icon: Icon }) => <article className={`revenue-card ${key}`} key={key}><div className="revenue-card-head"><Icon size={18} aria-hidden="true" /> {label}</div><AutoFitMoney>{busy && !data ? '…' : money(value)}</AutoFitMoney></article>)}
      </section>
      {data && <div className="revenue-formula">Tổng thu - Tổng chi = <strong>{money(data.net_income ?? (Number(data.total_income || 0) - Number(data.total_expense || 0)))}</strong> · Còn lại = (Tổng thu - Tổng chi) - Tiền TIP trong kỳ = <strong>{money(data.balance)}</strong></div>}
    </div>}

    <div className="revenue-tabs" role="tablist" aria-label="Doanh thu và chi phí">
      <button type="button" className={`revenue-tab ${activeTab === 'ledger' ? 'active' : ''}`} onClick={() => setActiveTab('ledger')}>Doanh thu-Chi phí</button>
      <button type="button" className={`revenue-tab ${activeTab === 'purchase' ? 'active' : ''}`} onClick={() => setActiveTab('purchase')}>Báo cáo mua hàng</button>
      {canViewAdminRevenueSummary && <button type="button" className={`revenue-tab ${activeTab === 'overview' ? 'active' : ''}`} onClick={() => setActiveTab('overview')}>Tổng quan</button>}
    </div>

    {activeTab !== 'overview' && <section className="detail-tab-panel">
      <div className="detail-filter-panel">
        <label>Thời gian<select value={detailPreset} onChange={(event) => setDetailPreset(event.target.value)}>{reconcileFilters.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Từ ngày<VeraDateInput value={detailPreset === 'custom' ? detailStart : (detailData?.start_date || '')} onChange={(event) => { setDetailPreset('custom'); setDetailStart(event.target.value) }} /></label>
        <label>Đến ngày<VeraDateInput value={detailPreset === 'custom' ? detailEnd : (detailData?.end_date || '')} onChange={(event) => { setDetailPreset('custom'); setDetailEnd(event.target.value) }} /></label>
        {activeTab === 'ledger' ? <div className="detail-filter-secondary">
          <label>Ngày<VeraDateInput value={ledgerDate} onChange={(event) => setLedgerDate(event.target.value)} /></label>
          <label>Loại giao dịch<select value={ledgerType} onChange={(event) => setLedgerType(event.target.value)}><option value="">Tất cả</option>{ledgerTypes.map(type => <option key={type} value={type}>{type}</option>)}</select></label>
          <label>Số tiền<VeraMoneyInput value={ledgerAmountFilter} onChange={(event) => setLedgerAmountFilter(event.target.value)} placeholder="Tìm số tiền" /></label>
          <label>Ghi chú<input value={ledgerNoteFilter} onChange={(event) => setLedgerNoteFilter(event.target.value)} placeholder="Tìm nội dung ghi chú" /></label>
        </div> : <div className="detail-filter-secondary">
          <label>Ngày nhập<VeraDateInput value={purchaseDate} onChange={(event) => setPurchaseDate(event.target.value)} /></label>
          <label>Chi tiết hàng hóa<input value={purchaseItemFilter} onChange={(event) => setPurchaseItemFilter(event.target.value)} placeholder="Tìm hàng hóa" /></label>
          <label>Người đặt<input value={purchaseBuyerFilter} onChange={(event) => setPurchaseBuyerFilter(event.target.value)} placeholder="Tìm người đặt" /></label>
          <label>User<input value={purchaseUserFilter} onChange={(event) => setPurchaseUserFilter(event.target.value)} placeholder="Tìm user" /></label>
        </div>}
        <div className="detail-filter-actions">
          {reconcileFilters.map(([value, label]) => <button type="button" key={value} className={`secondary-button ${detailPreset === value ? 'active' : ''}`} onClick={() => { setDetailPreset(value); if (value !== 'custom') { setDetailStart(''); setDetailEnd('') } }}>{label}</button>)}
          <button type="button" className="secondary-button" onClick={() => { setLedgerDate(''); setLedgerType(''); setLedgerAmountFilter(''); setLedgerNoteFilter(''); setPurchaseDate(''); setPurchaseItemFilter(''); setPurchaseBuyerFilter(''); setPurchaseUserFilter('') }}>Xóa lọc chi tiết</button>
        </div>
      </div>
      {detailError && <div className="error-box">{detailError}</div>}
      {detailBusy && !detailData && <div className="revenue-meta">Đang tải dữ liệu…</div>}
      {activeTab === 'ledger' && <div className="report-box"><div className="ledger-summary-head" aria-live="polite"><article className="ledger-filter-total"><TrendingUp size={18}/><div><span>Doanh thu theo bộ lọc</span><strong>{money(ledgerTotals.income)}</strong></div></article><article className="ledger-filter-total expense"><TrendingDown size={18}/><div><span>Chi phí theo bộ lọc</span><strong>{money(ledgerTotals.expense)}</strong></div></article><button type="button" className="secondary-button compact ledger-export" disabled={exportingLedger || detailBusy || !detailData} onClick={exportLedger}><Download size={14}/>{exportingLedger ? 'Đang xuất…' : 'Xuất Excel'}</button></div><div className="report-scroll"><table className="report-table ledger-table"><thead><tr><th>Ngày</th><th>Loại giao dịch</th><th className="money">Số tiền</th><th>Ghi chú</th><th>Ngày nhập</th><th>Giờ nhập</th><th>Người nhập</th></tr></thead><tbody>
        {ledgerRows.map((row, index) => <tr key={`${row.date}-${index}`} className={row.is_purchase ? 'purchase-row' : ''}><td data-label="Ngày">{row.date_label}</td><td data-label="Loại giao dịch">{row.type}</td><td data-label="Số tiền" className="money">{money(row.amount)}</td><td data-label="Ghi chú">{row.note || '—'}</td><td data-label="Ngày nhập">{row.entered_date_label || '—'}</td><td data-label="Giờ nhập">{row.entered_time || '—'}</td><td data-label="Người nhập">{row.entered_by || '—'}</td></tr>)}
        {!ledgerRows.length && <tr><td colSpan="7">Không có dữ liệu phù hợp bộ lọc.</td></tr>}
      </tbody></table></div></div>}
      {activeTab === 'purchase' && <div className="report-box"><h3><FileSpreadsheet size={16}/> Báo cáo mua hàng</h3><div className="report-scroll"><table className="report-table"><thead><tr><th>Ngày nhập</th><th>Chi tiết hàng hóa</th><th className="money">Số lượng</th><th className="money">Đơn giá</th><th className="money">Thành Tiền</th><th>Người đặt</th><th>User</th></tr></thead><tbody>
        {purchaseRows.map((row, index) => <tr key={`${row.date}-${index}`}><td>{row.date_label}</td><td>{row.item || '—'}</td><td className="money">{numberText(row.quantity)}</td><td className="money">{money(row.unit_price)}</td><td className="money">{money(row.amount)}</td><td>{row.buyer || '—'}</td><td>{row.user || '—'}</td></tr>)}
        {!purchaseRows.length && <tr><td colSpan="7">Không có dữ liệu phù hợp bộ lọc.</td></tr>}
      </tbody></table></div></div>}
    </section>}

    {canViewAdminRevenueSummary && activeTab === 'overview' && <section className="reconcile-panel">
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

        <div className="revenue-meta">Ngày trong dữ liệu Thu/Chi ưu tiên lấy từ ngày ghi trong cột Ghi chú, sau đó mới dùng cột Ngày giao dịch. Khi phát hiện một ngày có trạng thái <strong>KHÔNG KHỚP</strong> hoặc số liệu của ngày KHÔNG KHỚP thay đổi, hệ thống tự gửi Web Push chi tiết cho <strong>Admin, Quản lý và Lễ tân</strong>; cùng một trạng thái/số liệu sẽ không gửi lặp lại chỉ vì làm mới trang.</div>
      </>}
    </section>}
  </div>
}
