import useTablePage from '../lib/useTablePage'
import TablePager from '../components/TablePager'
import useRevenueSource from '../lib/useRevenueSource'
import useRevenueRealtime from '../lib/useRevenueRealtime'
import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import { AlertTriangle, CalendarDays, CheckCircle2, CircleDollarSign, Download, FileSpreadsheet, RefreshCw, Save, Upload, TrendingDown, TrendingUp, WalletCards } from 'lucide-react'
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
const todayIsoVietnam = () => {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}
const reconcileFilters = [
  ['all', 'Tất cả'],
  ['yesterday', 'Hôm qua'],
  ['today', 'Hôm nay'],
  ['last_week', 'Tuần trước'],
  ['this_week', 'Tuần này'],
  ['last_month', 'Tháng trước'],
  ['this_month', 'Tháng này'],
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

async function loadPeriodReport(start, end, signal) {
  const params = new URLSearchParams()
  if (start) params.set('start', start)
  if (end) params.set('end', end)
  const response = await fetch(`${apiBase}/v2/revenue/period-report?${params}`, { signal, cache: 'no-store', headers: await authorizedHeaders() })
  const result = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`)
  return result
}

async function loadPeriodTip(start, end, signal, legacy = false) {
  if (legacy) {
    const response = await fetch(`${apiBase}/v2/live-tour/reports`, { signal, headers: await authorizedHeaders() })
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`)
    return { period_tip: revenueTipTotal(result.reports || [], start, end) }
  }
  const params = new URLSearchParams({ start, end })
  const response = await fetch(`${apiBase}/v2/revenue/tip-summary?${params}`, { signal, headers: await authorizedHeaders() })
  const result = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`)
  return result
}

async function loadPurchaseReconcile({ preset, start, end, signal, canonical = false, reportEnd = '' }) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const params = new URLSearchParams({ preset })
  if (canonical) { params.set('canonical', 'true'); if (reportEnd) params.set('report_end', reportEnd) }
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

async function loadRevenueAudit({ timeRange, start, end, signal }) {
  const params = new URLSearchParams({ time_range: timeRange })
  if (timeRange === 'custom') { if (start) params.set('start', start); if (end) params.set('end', end) }
  const response = await fetch(`${apiBase}/v2/revenue/audit?${params}`, { signal, headers: await authorizedHeaders() })
  const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`); return payload
}

async function loadRevenueDuplicates({ timeRange, start, end, signal }) {
  const params = new URLSearchParams({ time_range: timeRange })
  if (timeRange === 'custom') { if (start) params.set('start', start); if (end) params.set('end', end) }
  const response = await fetch(`${apiBase}/v2/revenue/duplicates?${params}`, { signal, headers: await authorizedHeaders() })
  const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`); return payload
}

async function importRevenueExcel(file, mode) {
  if (!file) return null
  if (!/\.xlsx$/i.test(file.name || '')) throw new Error('Chỉ hỗ trợ file Excel .xlsx.')
  if (file.size > 15 * 1024 * 1024) throw new Error('File Excel vượt quá 15 MB.')
  const response = await fetch(`${apiBase}/v2/revenue/import.xlsx?mode=${encodeURIComponent(mode)}`, {
    method: 'POST',
    headers: await authorizedHeaders(),
    body: file,
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

async function savePeriodTip(amount, startDate, endDate, autoMode, commonReport = false) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const response = await fetch(`${apiBase}/v2/revenue/${commonReport ? 'report-period' : autoMode ? 'tip-period' : 'tip'}`, {
    method: 'PUT',
    headers: await authorizedHeaders(true),
    body: JSON.stringify({ ...(autoMode || commonReport ? {} : { amount: Number(amount || 0) }), start_date: startDate || null, end_date: endDate || null }),
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
  return <div data-ui-key="u-8ce3e4957cc4" ref={ref} className="revenue-card-value">{children}</div>
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
  usePageRefresh(() => { setRevision(value => value + 1); setReconcileRevision(value => value + 1) }, () => Boolean(busy || savingTip || savingEntry || importingRevenue || entryEditor))
  const [data, setData] = useState(null)
  const [tip, setTip] = useState(0)
  const [tipStart, setTipStart] = useState('')
  const [tipEnd, setTipEnd] = useState('')
  const [tipBusy, setTipBusy] = useState(false)
  const [tipLoadError, setTipLoadError] = useState('')
  const [busy, setBusy] = useState(false)
  const [savingTip, setSavingTip] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [revision, setRevision] = useState(0)
  const [summaryVersion, setSummaryVersion] = useState(0)
  const [reconcileRevision, setReconcileRevision] = useState(0)
  const sharedSource = useRevenueSource()
  const revenueSource = sharedSource.source
  const sourceReady = sharedSource.ready
  const sharedSourceSupported = sharedSource.supported
  const sourceRevision = sharedSource.revision
  const refreshRevenueSource = sharedSource.refresh
  const commonReport = sharedSource.reportVersion >= 1 && revenueSource !== 'manual_tip_auto'
  const reportSnapshot = useRef(null)
  const [manualLedger, setManualLedger] = useState(false)
  const canonicalLedger = commonReport && !(manualLedger && revenueSource !== 'auto')
  const tipEditorRef = useRef(null)
  // Auto uses the displayed TIP end date as its report cutoff too. A cleared
  // input must not silently switch the report back to all dates.
  const summaryEnd = commonReport || revenueSource === 'auto' ? tipEnd || data?.end_date || '' : ''
  const reportEnd = commonReport ? data?.end_date || summaryEnd : ''
  const summaryTipStart = commonReport ? tipStart : ''
  const summaryTipEnd = commonReport ? tipEnd : ''
  const summaryRange = summaryEnd ? 'custom' : 'all'
  const summaryStart = summaryEnd ? '2025-09-05' : ''
  const [entryDate, setEntryDate] = useState(todayIsoVietnam)
  const revenueImportAppendRef = useRef(null)
  const revenueImportReplaceRef = useRef(null)
  const [importingRevenue, setImportingRevenue] = useState('')
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
  const [detailPreset, setDetailPreset] = useState('all')
  const [detailStart, setDetailStart] = useState('')
  const [detailEnd, setDetailEnd] = useState('')
  const [detailData, setDetailData] = useState(null)
  const detailLoaded = useRef(null)
  const detailTabActive = ['ledger', 'purchase'].includes(activeTab)
  const [detailBusy, setDetailBusy] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [exportingLedger, setExportingLedger] = useState(false)
  const [ledgerNoteFilter, setLedgerNoteFilter] = useState('')
  const [ledgerEnteredDate, setLedgerEnteredDate] = useState('')
  const [ledgerEnteredByFilter, setLedgerEnteredByFilter] = useState('')
  const [ledgerAmountFilter, setLedgerAmountFilter] = useState('')
  const [purchaseItemFilter, setPurchaseItemFilter] = useState('')
  const [purchaseBuyerFilter, setPurchaseBuyerFilter] = useState('')
  const [purchaseUserFilter, setPurchaseUserFilter] = useState('')
  const [selectedLedgerId, setSelectedLedgerId] = useState(null)
  const [entryEditor, setEntryEditor] = useState(null)
  const [auditData, setAuditData] = useState({ rows: [] })
  const [duplicateData, setDuplicateData] = useState({ groups: [], group_count: 0, duplicate_row_count: 0, duplicate_amount: 0 })
  const role = String(user?.role || '').trim().toLowerCase()
  const canViewAdminRevenueSummary = role === 'admin' || role === 'giamdoc'
  const isAdmin = role === 'admin'
  const autoMode = revenueSource === 'auto'
  const hybridMode = revenueSource === 'manual_tip_auto'
  const systemTipMode = autoMode || hybridMode
  useEffect(() => {
    if (!canViewAdminRevenueSummary && activeTab === 'overview') setActiveTab('ledger')
  }, [activeTab, canViewAdminRevenueSummary])
  const purchaseRows = useMemo(() => (detailData?.purchase_rows || []).filter(row => {
    const item = String(row.item || '').toLocaleLowerCase('vi')
    const buyer = String(row.buyer || '').toLocaleLowerCase('vi')
    const rowUser = String(row.user || '').toLocaleLowerCase('vi')
    return (!purchaseDate || row.date === purchaseDate)
      && (!purchaseItemFilter || item.includes(purchaseItemFilter.toLocaleLowerCase('vi')))
      && (!purchaseBuyerFilter || buyer.includes(purchaseBuyerFilter.toLocaleLowerCase('vi')))
      && (!purchaseUserFilter || rowUser.includes(purchaseUserFilter.toLocaleLowerCase('vi')))
  }), [detailData, purchaseDate, purchaseItemFilter, purchaseBuyerFilter, purchaseUserFilter])
  const ledgerRows = useMemo(() => ((detailData?.source === revenueSource || (sourceReady && !sharedSourceSupported)) && (!commonReport || detailData?.canonical === canonicalLedger) ? (detailData?.ledger_rows || []) : []).filter(row => {
    const note = String(row.note || '').toLocaleLowerCase('vi')
    const enteredBy = String(row.entered_by || '').toLocaleLowerCase('vi')
    const amountText = String(Math.round(Number(row.amount || 0)))
    const wantedAmount = String(ledgerAmountFilter || '').replace(/\D/g, '')
    return (!ledgerDate || row.date === ledgerDate)
      && (!ledgerType || row.type === ledgerType)
      && (!ledgerNoteFilter || note.includes(ledgerNoteFilter.toLocaleLowerCase('vi')))
      && (!ledgerEnteredDate || row.entered_date_label === formatVeraDate(ledgerEnteredDate))
      && (!ledgerEnteredByFilter || enteredBy.includes(ledgerEnteredByFilter.toLocaleLowerCase('vi')))
      && (!wantedAmount || amountText.includes(wantedAmount))
  }), [detailData, revenueSource, sourceReady, sharedSourceSupported, commonReport, canonicalLedger, ledgerDate, ledgerType, ledgerNoteFilter, ledgerEnteredDate, ledgerEnteredByFilter, ledgerAmountFilter])
  const ledgerTotals = ledgerRows.reduce((totals, row) => {
    const type = String(row.type || '').trim().toLocaleLowerCase('vi')
    const amount = Number(row.amount || 0)
    if (type === 'thu' || type.includes('doanh thu')) totals.income += amount
    if (type === 'chi' || type.includes('chi phí')) totals.expense += amount
    return totals
  }, { income: 0, expense: 0 })
  const ledgerTypes = [...new Set((detailData?.ledger_rows || []).map(row => row.type).filter(Boolean))]
  const selectedLedgerRow = ledgerRows.find(row => row.id === selectedLedgerId) || null

  useEffect(() => {
    if (!incomeNoteEdited) setEntryIncomeNote(defaultRevenueNote('Doanh thu', entryDate))
    if (!expenseNoteEdited) setEntryExpenseNote(defaultRevenueNote('Chi phí', entryDate))
  }, [entryDate, expenseNoteEdited, incomeNoteEdited])

  useEffect(() => {
    if (!sourceReady) return undefined
    const key = (start, end) => JSON.stringify([revenueSource, sourceRevision, revision, start, end])
    if (commonReport && reportSnapshot.current) {
      if (!summaryTipStart || !summaryTipEnd || summaryTipStart > summaryTipEnd) { setBusy(false); return undefined }
      if (reportSnapshot.current === key(summaryTipStart, summaryTipEnd)) { setBusy(false); return undefined }
    }
    const controller = new AbortController()
    setBusy(true)
    setError('')
    const run = async () => {
      try {
        const result = commonReport
          ? await loadPeriodReport(summaryTipStart, summaryTipEnd, controller.signal)
          : await loadRevenue({ source: revenueSource, timeRange: summaryRange, start: summaryStart, end: summaryEnd, signal: controller.signal })
        if (!controller.signal.aborted) {
          if (commonReport && (result.source !== revenueSource || result.source_revision !== sourceRevision)) {
            void refreshRevenueSource()
            return
          }
          const defaultTipStartDate = defaultRevenueTipStart(result.current_date) || result.period_tip_start || ''
          const defaultTipEndDate = result.current_date || result.period_tip_end || ''
          if (commonReport) {
            reportSnapshot.current = key(result.period_tip_start, result.period_tip_end)
            setTip(Number(result.period_tip || 0))
          }
          setData({ ...result, source_revision: result.source_revision ?? sourceRevision })
          setSummaryVersion(value => value + 1)
          setTipStart(current => current || (commonReport || result.source === 'auto' ? result.period_tip_start : defaultTipStartDate))
          setTipEnd(current => current || (commonReport || result.source === 'auto' ? result.period_tip_end : defaultTipEndDate))
        }
      } catch (err) {
        if (!controller.signal.aborted && err?.name !== 'AbortError') setError(err.message || 'Không tải được Doanh thu.')
      } finally {
        if (!controller.signal.aborted) setBusy(false)
      }
    }
    let timer
    if (commonReport && summaryTipStart && summaryTipEnd) timer = setTimeout(run, 200)
    else void run()
    return () => { clearTimeout(timer); controller.abort() }
  }, [sourceReady, sourceRevision, revenueSource, summaryEnd, summaryRange, summaryStart, revision, commonReport, summaryTipStart, summaryTipEnd, refreshRevenueSource])

  useEffect(() => {
    if (commonReport) { setTipBusy(false); return undefined }
    if (!sourceReady || data?.source_revision !== sourceRevision || !tipStart || !tipEnd || tipStart > tipEnd) return undefined
    const controller = new AbortController()
    setTipBusy(true)
    setTipLoadError('')
    const timer = setTimeout(async () => {
      try {
        const result = await loadPeriodTip(tipStart, tipEnd, controller.signal, !sharedSourceSupported)
        if (controller.signal.aborted) return
        const autoTip = Number(result.period_tip || 0)
        setTip(autoTip)
        setData(current => current ? ({ ...current, period_tip: autoTip,
          balance: Math.round((Number(current.total_income || 0) - Number(current.total_expense || 0) - autoTip) * 100) / 100,
          period_tip_start: tipStart, period_tip_end: tipEnd }) : current)
      } catch (err) {
        if (!controller.signal.aborted) setTipLoadError(err.message || 'Không lấy được TIP trong kỳ.')
      } finally { if (!controller.signal.aborted) setTipBusy(false) }
    }, 250)
    return () => { clearTimeout(timer); controller.abort() }
  }, [sourceReady, sourceRevision, tipStart, tipEnd, summaryVersion, data?.source_revision, sharedSourceSupported, commonReport])

  useEffect(() => {
    if (!sourceReady || (commonReport && !reportEnd) || activeTab !== 'overview') return undefined
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
          preset: filterPreset, canonical: commonReport, reportEnd,
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
  }, [filterPreset, customStart, customEnd, reconcileRevision, sourceReady, sourceRevision, activeTab, commonReport, reportEnd])

  useEffect(() => {
    if (!sourceReady || (commonReport && !reportEnd) || !detailTabActive) return undefined
    if (detailPreset === 'custom' && (!detailStart || !detailEnd)) {
      setDetailData(null)
      setDetailError('')
      return undefined
    }
    const scope = JSON.stringify([detailPreset, detailStart, detailEnd, sourceRevision, reconcileRevision, canonicalLedger, reportEnd])
    if (detailLoaded.current?.scope === scope && Date.now() - detailLoaded.current.at < 30000) return undefined
    const controller = new AbortController()
    const run = async () => {
      setDetailBusy(true)
      setDetailError('')
      try {
        const result = await loadPurchaseReconcile({ preset: detailPreset, start: detailStart, end: detailEnd, canonical: canonicalLedger, reportEnd, signal: controller.signal })
        if (!controller.signal.aborted) { setDetailData(result); detailLoaded.current = { scope, at: Date.now() } }
      } catch (err) {
        if (!controller.signal.aborted && err?.name !== 'AbortError') setDetailError(err.message || 'Không tải được dữ liệu chi tiết.')
      } finally {
        if (!controller.signal.aborted) setDetailBusy(false)
      }
    }
    void run()
    return () => controller.abort()
  }, [detailPreset, detailStart, detailEnd, reconcileRevision, sourceReady, sourceRevision, detailTabActive, canonicalLedger, reportEnd, commonReport])

  useEffect(() => {
    if (!isAdmin || !['audit', 'duplicates'].includes(activeTab) || (detailPreset === 'custom' && (!detailStart || !detailEnd))) return undefined
    const controller = new AbortController()
    const request = activeTab === 'audit'
      ? loadRevenueAudit({ timeRange: detailPreset, start: detailStart, end: detailEnd, signal: controller.signal }).then(result => { if (!controller.signal.aborted) setAuditData(result) })
      : loadRevenueDuplicates({ timeRange: detailPreset, start: detailStart, end: detailEnd, signal: controller.signal }).then(result => { if (!controller.signal.aborted) setDuplicateData(result) })
    request
      .catch(err => { if (!controller.signal.aborted && err?.name !== 'AbortError') setDetailError(err.message || 'Không tải được lịch sử Thu Chi.') })
    return () => controller.abort()
  }, [activeTab, detailEnd, detailPreset, detailStart, isAdmin, reconcileRevision])

  const submitTip = async () => {
    setSavingTip(true)
    setError('')
    setNotice('')
    try {
      const invalidDate = [...(tipEditorRef.current?.querySelectorAll('input') || [])].find(input => !input.checkValidity())
      if (invalidDate) { invalidDate.reportValidity(); return }
      if (!Number.isFinite(Number(tip)) || Number(tip) < 0) throw new Error('Tiền TIP trong kỳ phải là số không âm.')
      if (!tipStart || !tipEnd) throw new Error('Chọn đủ Ngày bắt đầu và Đến ngày cho Tiền TIP trong kỳ.')
      if (tipStart > tipEnd) throw new Error('Ngày bắt đầu Tiền TIP không được sau Đến ngày.')
      const result = await savePeriodTip(tip, tipStart, tipEnd, autoMode, commonReport)
      if (commonReport) setData(result)
      else setData((current) => current ? ({ ...current, period_tip: result.period_tip, balance: Math.round((Number(current.net_income ?? (Number(current.total_income || 0) - Number(current.total_expense || 0))) - Number(result.period_tip || 0)) * 100) / 100, period_tip_start: result.period_tip_start, period_tip_end: result.period_tip_end }) : current)
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
    if (autoMode || !sourceReady) return
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
      if (commonReport) setManualLedger(true)
      setNotice(result.message || 'Đã ghi Thu Chi vào Chi tiết Doanh thu - Chi phí.')
      setRevision((value) => value + 1)
      setReconcileRevision((value) => value + 1)
    } catch (err) {
      setError(err.message || 'Không ghi được Thu Chi.')
    } finally {
      setSavingEntry(false)
    }
  }

  const handleRevenueImport = async (event, mode) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || autoMode || !sourceReady) return
    if (mode === 'replace' && !window.confirm('THAY THẾ TOÀN BỘ dữ liệu Doanh thu-Chi phí hiện tại bằng file Excel này? Dữ liệu hiện tại sẽ không còn hiển thị sau khi import.')) return
    setImportingRevenue(mode)
    setError('')
    setNotice('')
    try {
      const result = await importRevenueExcel(file, mode)
      setNotice(result?.message || 'Đã import Excel Doanh thu-Chi phí.')
      setRevision(value => value + 1)
      setReconcileRevision(value => value + 1)
    } catch (err) {
      setError(err.message || 'Không import được Excel Doanh thu-Chi phí.')
    } finally {
      setImportingRevenue('')
    }
  }

  const exportLedger = async () => {
    setExportingLedger(true)
    setDetailError('')
    try {
      const params = new URLSearchParams({ preset: detailPreset })
      if (canonicalLedger) { params.set('canonical', 'true'); if (reportEnd) params.set('report_end', reportEnd) }
      if (detailPreset === 'custom') {
        if (detailStart) params.set('start', detailStart)
        if (detailEnd) params.set('end', detailEnd)
      }
      if (ledgerDate) params.set('transaction_date', ledgerDate)
      if (ledgerType) params.set('transaction_type', ledgerType)
      if (ledgerAmountFilter) params.set('amount', ledgerAmountFilter)
      if (ledgerNoteFilter) params.set('note', ledgerNoteFilter)
      if (ledgerEnteredDate) params.set('entered_date', ledgerEnteredDate)
      if (ledgerEnteredByFilter) params.set('entered_by', ledgerEnteredByFilter)
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

  useEffect(() => {
    if (!systemTipMode || autoMode) return undefined
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'hidden') { setRevision(value => value + 1); setReconcileRevision(value => value + 1) }
    }, 30000)
    return () => window.clearInterval(timer)
  }, [systemTipMode, autoMode])

  const realtimeError = useRevenueRealtime(sourceReady && (autoMode || commonReport),
    Boolean(busy || (detailTabActive && detailBusy) || (activeTab === 'overview' && reconcileBusy) || tipBusy || savingTip || savingEntry || importingRevenue || entryEditor),
    () => { setRevision(value => value + 1); setReconcileRevision(value => value + 1); void sharedSource.refresh() },
    Boolean(error || (detailTabActive && detailError) || (activeTab === 'overview' && reconcileError) || tipLoadError))

  const openRevenueEditor = (mode) => {
    const row = selectedLedgerRow
    if (!row) { setError('Hãy check chọn một dòng Thu Chi trước.'); return }
    if (!canManageCurrentEntry(row)) { setError('Chỉ được sửa hoặc xóa bản ghi đã nhập trong ngày hiện tại.'); return }
    setError('')
    setEntryEditor({ mode, row, type: row.type || 'Thu', date: row.date || '', amount: String(Math.round(Number(row.amount || 0))), note: row.note || '', enteredDate: row.entered_date || '', enteredTime: row.entered_time || '00:00:00', enteredBy: row.entered_by || '' })
  }

  const saveManualRevenue = async () => {
    if (!entryEditor || autoMode || !sourceReady) return
    const { row } = entryEditor
    try {
      if (entryEditor.mode === 'delete') {
        const result = await deleteRevenueEntry(row.id)
        setNotice(result.message || 'Đã xóa bản ghi.')
      } else {
        if (!entryEditor.date || !entryEditor.enteredDate) throw new Error('Hãy nhập đủ Ngày giao dịch và Ngày nhập.')
        if (!/^([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/.test(entryEditor.enteredTime)) throw new Error('Giờ nhập phải đúng HH:MM hoặc HH:MM:SS.')
        const result = await updateRevenueEntry(row.id, { transaction_type: entryEditor.type, amount: Number(String(entryEditor.amount).replace(/\D/g, '')), transaction_date: entryEditor.date, note: entryEditor.note, entered_date: entryEditor.enteredDate, entered_time: entryEditor.enteredTime, entered_by_name: entryEditor.enteredBy })
        setNotice(result.message || 'Đã sửa toàn bộ dữ liệu bản ghi.')
      }
      setEntryEditor(null); setSelectedLedgerId(null); setRevision(value => value + 1); setReconcileRevision(value => value + 1)
    } catch (err) { setError(err.message || 'Không sửa được bản ghi doanh thu.') }
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

  const ledgerPagination = useTablePage(ledgerRows, JSON.stringify([revenueSource, detailPreset, detailStart, detailEnd, ledgerDate, ledgerType, ledgerNoteFilter, ledgerEnteredDate, ledgerEnteredByFilter, ledgerAmountFilter]))
  const purchasePagination = useTablePage(purchaseRows, JSON.stringify([detailPreset, detailStart, detailEnd, purchaseDate, purchaseItemFilter, purchaseBuyerFilter, purchaseUserFilter]))
  const auditPagination = useTablePage(auditData.rows || [], JSON.stringify([detailPreset, detailStart, detailEnd]))
  const duplicatePagination = useTablePage(duplicateData.groups || [], JSON.stringify([detailPreset, detailStart, detailEnd]))
  const comparisonPagination = useTablePage(comparisonRows, JSON.stringify([filterPreset, customStart, customEnd, differenceFilter, statusFilter]))

  const cards = hybridMode ? [
    { key: 'income', label: hybridMode ? 'TIỀN DỊCH VỤ · MANUAL' : 'TIỀN DỊCH VỤ', value: data?.service_revenue, icon: TrendingUp },
    { key: 'tip', label: 'TIỀN TIP', value: data?.tip_revenue, icon: CircleDollarSign },
    { key: 'balance', label: 'TỔNG DOANH THU', value: data?.total_revenue, icon: WalletCards },
  ] : [
    { key: 'income', label: 'TỔNG THU', value: data?.total_income, icon: TrendingUp },
    { key: 'expense', label: 'TỔNG CHI', value: data?.total_expense, icon: TrendingDown },
    { key: 'net', label: 'TỔNG THU - TỔNG CHI', value: data?.net_income ?? (Number(data?.total_income || 0) - Number(data?.total_expense || 0)), icon: WalletCards },
    { key: 'tip', label: 'TIỀN TIP TRONG KỲ', value: data?.period_tip, icon: CircleDollarSign },
    { key: 'balance', label: 'CÒN LẠI', value: data?.balance, icon: WalletCards },
  ]
  const canEditTip = Boolean(data?.can_edit_tip)
  const canCreateEntry = Boolean(sourceReady && !sharedSource.changing && !autoMode && data?.source === revenueSource && data?.can_create_entry)
  const canEditEntry = Boolean(sourceReady && !sharedSource.changing && !autoMode && data?.source === revenueSource && data?.can_edit_entry)
  const canDeleteEntry = Boolean(sourceReady && !sharedSource.changing && !autoMode && data?.source === revenueSource && data?.can_delete_entry)
  const canManageCurrentEntry = (row) => Boolean(!autoMode && !row?.read_only && row?.id && (isAdmin || (row.entered_date && row.entered_date === (data?.business_date || todayIsoVietnam()))))
  const overallStatus = reconcile?.overall_status || 'KHỚP'
  const overallClass = overallStatus === 'KHỚP' ? 'ok' : overallStatus === 'GẦN KHỚP' ? 'near' : 'bad'

  return <div className="feature-page revenue-page">
    <style>{`
      .revenue-page .revenue-source{display:flex;gap:8px;align-items:center;color:#68736f;font-size:13px}.revenue-source-toolbar{display:grid;gap:10px;margin-bottom:14px;padding:12px 14px;border:1px solid #cbded3;border-radius:15px;background:#f7faf8}.revenue-source-toggle,.revenue-time-toolbar{display:flex;gap:7px;flex-wrap:wrap}.revenue-source-toggle button,.revenue-time-toolbar button{min-height:36px;padding:6px 11px;border:1px solid #b8d0c3;border-radius:10px;background:#fff;color:#24473a;font-weight:900}.revenue-source-toggle button.active,.revenue-time-toolbar button.active{background:#1f513f;color:#fff;border-color:#1f513f}.revenue-custom-range{display:flex;gap:10px;flex-wrap:wrap}.revenue-custom-range label{display:grid;gap:4px;font-size:11px;font-weight:900}.revenue-source-toolbar small{color:#64746d}.revenue-crud-actions{display:flex;gap:5px;white-space:nowrap}.revenue-admin-records{margin:14px 0}
      .revenue-period{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:14px}
      .revenue-period-card{display:flex;align-items:center;gap:12px;padding:14px 16px;border:1px solid #dfe7e2;border-radius:15px;background:#fff}
      .revenue-period-card svg{color:#8b6b22;flex:0 0 auto}.revenue-period-card span{display:block;font-size:11px;font-weight:900;letter-spacing:.05em;color:#68736f;text-transform:uppercase}.revenue-period-card strong{display:block;margin-top:3px;font-size:18px;color:#173329}
      .revenue-actions{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}.revenue-action-link{display:inline-flex;align-items:center;justify-content:center;gap:8px;text-decoration:none;min-height:43px}.revenue-action-link.disabled{opacity:.45;pointer-events:none}
            .revenue-entry-form{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,2fr);grid-template-areas:"title title" "date ." "income income-note" "expense expense-note" "save save";gap:10px;align-items:end;margin-bottom:14px;padding:14px;border:1px solid #cbded3;border-radius:15px;background:#f5faf7}.revenue-entry-form h2{grid-area:title;margin:0;color:#173329;font-size:18px}.revenue-entry-form label{display:grid;gap:5px;font-size:12px;font-weight:900;color:#425c51}.revenue-entry-form input{min-height:42px}.revenue-entry-form .entry-date{grid-area:date}.revenue-entry-form .entry-date .vera-date-input{width:100%;max-width:none}.revenue-entry-form .entry-amount:not(.entry-expense){grid-area:income}.revenue-entry-form .entry-note:not(.entry-expense-note){grid-area:income-note}.revenue-entry-form .entry-expense{grid-area:expense}.revenue-entry-form .entry-expense-note{grid-area:expense-note}.revenue-entry-form .entry-amount input{text-align:right;font-weight:850}.revenue-entry-form .entry-expense input{background:#fff4e5;border-color:#d99145}.revenue-entry-form .entry-expense-note input{background:#fff8ee;border-color:#d9a86f}.revenue-entry-form input.auto-note-empty{color:#9aa39f;font-weight:650}.revenue-entry-form > button{grid-area:save;min-height:42px;white-space:nowrap;width:100%}.revenue-entry-help{grid-column:1/-1;margin:0;color:#66776f;font-size:11px}
      .revenue-tip-editor{display:grid;grid-template-columns:minmax(230px,1.45fr) minmax(155px,.9fr) minmax(155px,.9fr) minmax(190px,1fr) auto;gap:10px;align-items:end;margin-bottom:14px;padding:14px;border:1px solid #dfd5b9;border-radius:15px;background:#fffaf0}.revenue-tip-editor label{display:grid;gap:5px;font-size:12px;font-weight:900;min-width:0}.revenue-tip-editor input{font-size:16px;font-weight:800;min-width:0}.revenue-tip-editor .revenue-tip-amount input{text-align:right;font-size:18px}.revenue-tip-editor small{grid-column:1/-1;color:#75694d;line-height:1.45}.revenue-tip-current{display:flex;align-items:center;justify-content:space-between;gap:6px;min-height:42px;padding:0 8px;border:1px solid #dfd5b9;border-radius:10px;background:#fff;color:#75694d;font-size:11px;font-weight:900;white-space:nowrap}.revenue-tip-current button{min-height:30px;padding:4px 8px;font-size:11px;white-space:nowrap}
      .revenue-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}.revenue-card{padding:18px;border:1px solid #dfe7e2;border-radius:18px;background:#fff;min-width:0}.revenue-card-head{display:flex;align-items:center;gap:9px;color:#5d6f66;font-size:12px;font-weight:900;letter-spacing:.05em}.revenue-card-value{width:100%;min-width:0;margin-top:14px;font-size:30px;line-height:1.05;font-weight:900;color:#173329;white-space:nowrap;overflow:hidden;font-variant-numeric:tabular-nums}.revenue-card.net{background:#f7faf8;border-color:#d2e0d8}.revenue-card.tip{background:#fffaf0;border-color:#e4d5ad}.revenue-card.balance{background:#f3f8f5;border-color:#cbded3}
      .revenue-formula{margin-top:14px;padding:12px 14px;border:1px solid #cbded3;border-radius:13px;background:#f3f8f5;color:#244a3a;font-size:13px;font-weight:800;text-align:center}.revenue-meta{margin-top:10px;padding:12px 14px;border:1px solid #e4eae6;border-radius:13px;background:#fafcfb;color:#68736f;font-size:12px}
      .reconcile-panel{margin-top:20px;padding:16px;border:1px solid #dfe7e2;border-radius:18px;background:#fff}.reconcile-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:14px}.reconcile-head h2{margin:3px 0 0;font-size:20px;color:#173329}.reconcile-head p{margin:4px 0 0;color:#68736f;font-size:12px;max-width:850px}.reconcile-filter{display:flex;align-items:end;gap:8px;flex-wrap:wrap}.reconcile-filter label{display:grid;gap:5px;font-size:11px;font-weight:900;color:#53635c}.reconcile-filter select,.reconcile-filter input{min-height:40px;min-width:145px}
      .reconcile-status{display:flex;gap:10px;align-items:flex-start;padding:12px 14px;border-radius:13px;margin-bottom:12px;font-weight:800;font-size:13px}.reconcile-status.ok{background:#eef8f1;border:1px solid #bdd9c6;color:#245b38}.reconcile-status.near{background:#fffbea;border:1px solid #e9d982;color:#7a6500}.reconcile-status.bad{background:#fff0ed;border:1px solid #efb0a5;color:#8d291d}.reconcile-status svg{flex:0 0 auto;margin-top:1px}
      .reconcile-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:14px}.reconcile-kpi{padding:13px;border:1px solid #e1e7e3;border-radius:14px;background:#fafcfb}.reconcile-kpi span{display:block;font-size:10px;font-weight:900;color:#69766f;letter-spacing:.04em}.reconcile-kpi strong{display:block;margin-top:5px;font-size:19px;color:#173329}.reconcile-kpi.near strong{color:#806800}.reconcile-kpi.bad strong{color:#a13c2f}
      .comparison-filter-bar{display:flex;gap:8px;align-items:end;flex-wrap:wrap;padding:10px 12px;border-bottom:1px solid #e7ece9;background:#fbfcfb}.comparison-filter-bar label{display:grid;gap:4px;font-size:10px;font-weight:900;color:#5d6b64}.comparison-filter-bar select{min-height:36px;min-width:150px}.comparison-filter-bar small{margin-left:auto;color:#6c7772}
      .revenue-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.revenue-tab{border:1px solid #b8d0c3;background:#fff;color:#24473a;border-radius:12px;padding:10px 14px;font-weight:900;cursor:pointer}.revenue-tab.active{background:#1f513f;color:#fff;border-color:#1f513f}.detail-tab-panel{margin-bottom:18px}.detail-filter-panel{display:grid;grid-template-columns:1.05fr 1fr 1fr;gap:10px;padding:14px;border:1px solid #cbded3;border-radius:15px;background:#f7faf8;margin-bottom:12px}.detail-filter-panel label{display:grid;gap:5px;font-size:11px;font-weight:900;color:#53635c}.detail-filter-panel input,.detail-filter-panel select{min-height:42px}.detail-filter-secondary{display:grid;grid-template-columns:.9fr .9fr .9fr 1.3fr 1fr .9fr;gap:10px;grid-column:1/-1}.detail-filter-actions{display:flex;gap:8px;align-items:end;justify-content:flex-end;flex-wrap:wrap;grid-column:1/-1}.detail-filter-actions button{min-height:40px}.detail-filter-actions .active{background:#1f513f;color:#fff;border-color:#1f513f}.admin-revenue-summary{display:grid;gap:14px}
      .ledger-summary-head{display:flex;align-items:stretch;gap:10px;padding:10px 12px;background:#f5f8f6;flex-wrap:wrap}.ledger-filter-total{display:flex;align-items:center;gap:9px;min-width:180px;padding:10px 13px;border:1px solid #cbded3;border-radius:12px;background:#fff}.ledger-filter-total.expense{border-color:#e1c49f;background:#fffaf2}.ledger-filter-total svg{color:#8b6b22;flex:0 0 auto}.ledger-filter-total span{display:block;font-size:10px;font-weight:900;color:#68736f;text-transform:uppercase}.ledger-filter-total strong{display:block;margin-top:2px;font-size:18px;color:#173329}.ledger-summary-head .ledger-import,.ledger-summary-head .ledger-export{align-self:center}.ledger-summary-head .ledger-import:first-of-type{margin-left:auto}.ledger-selected-actions{display:flex;gap:6px;align-items:center;margin-left:auto}.ledger-check-column{width:42px!important;text-align:center!important}.ledger-check-column input{width:18px;height:18px;accent-color:#1f513f}.selected-ledger-row td{background:#eaf5ef!important}.revenue-audit-grid{display:grid;grid-template-columns:1.2fr .8fr;gap:12px}.audit-payload{min-width:250px;white-space:normal!important}.duplicate-summary{display:flex;justify-content:space-between;gap:10px;padding:12px;background:#fff8e9}.duplicate-summary strong{color:#8a5419}.revenue-editor-backdrop{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;padding:18px;background:rgba(9,31,23,.55)}.revenue-editor-dialog{width:min(760px,100%);max-height:92vh;overflow:auto;border:2px solid #1f513f;border-radius:18px;background:#fff;box-shadow:0 24px 70px rgba(0,0,0,.3)}.revenue-editor-dialog header,.revenue-editor-dialog footer{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 16px;background:#f3f8f5}.revenue-editor-dialog header span{font-size:10px;font-weight:900;color:#8b6b22}.revenue-editor-dialog h2{margin:3px 0 0;color:#173329}.revenue-editor-form{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;padding:16px}.revenue-editor-form label{display:grid;gap:5px;font-size:11px;font-weight:900;color:#425c51}.revenue-editor-form input,.revenue-editor-form select{min-height:42px}.revenue-editor-form .editor-note{grid-column:1/-1}.revenue-editor-form .editor-entered-by{grid-column:span 2}.delete-warning{margin:0 16px 16px;padding:12px;border:1px solid #e2b0a8;border-radius:10px;background:#fff1ef;color:#8f3026}.revenue-editor-dialog footer{justify-content:flex-end}.revenue-editor-dialog footer button{min-width:140px}
.report-box{min-width:0;max-width:100%;border:1px solid #e2e8e4;border-radius:14px;overflow:hidden}.report-box h3{display:flex;gap:8px;align-items:center;margin:0;padding:11px 13px;background:#f5f8f6;color:#24473a;font-size:13px}.report-scroll{width:100%;max-width:100%;overflow:auto;max-height:430px}.report-table{width:100%;border-collapse:collapse;min-width:650px;font-size:12px}.comparison-table{min-width:1050px}.report-table th,.report-table td{padding:8px 9px;border-bottom:1px solid #edf1ee;white-space:nowrap;text-align:left;vertical-align:top}.report-table th{position:sticky;top:0;background:#dcefe5;z-index:1;font-size:10px;color:#173b2e;text-transform:uppercase;border-bottom:2px solid #79a48e}.report-table .money{text-align:right;font-variant-numeric:tabular-nums}.report-table .detail-cell{white-space:normal;min-width:330px;line-height:1.45}.report-table .detail-cell div+div{margin-top:4px}.report-table tr.mismatch td{background:#fff2ef}.report-table tr.near td{background:#fffceb}.report-table tr.match td{background:#f5fbf7}.report-table tr.purchase-row td{font-weight:700}.status-match{color:#24703e;font-weight:900}.status-near{color:#806800;font-weight:900}.status-mismatch{color:#a13c2f;font-weight:900}
      @media(max-width:1250px){.revenue-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.reconcile-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}.revenue-audit-grid{grid-template-columns:1fr}}
      @media(max-width:1050px){.revenue-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
      @media(max-width:760px){.revenue-page{overflow-x:hidden}.detail-filter-panel{grid-template-columns:1fr 1fr;padding:10px}.detail-filter-panel>label:first-child{grid-column:1/-1}.detail-filter-secondary{grid-template-columns:1fr 1fr}.detail-filter-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:stretch;justify-content:stretch}.detail-filter-actions button{width:100%;min-width:0;white-space:nowrap;font-size:12px;padding:8px 5px}.revenue-period{grid-template-columns:1fr}.revenue-actions{display:grid;grid-template-columns:1fr 1fr}.revenue-tip-editor{grid-template-columns:1fr}.revenue-tip-editor button{width:100%}.revenue-tip-current button{width:auto}.revenue-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.revenue-card{padding:13px;border-radius:14px}.revenue-card.balance{grid-column:1/-1}.revenue-card-value{margin-top:8px;font-size:clamp(16px,4.6vw,22px);white-space:nowrap}.revenue-page .page-heading{align-items:flex-start}.reconcile-head{display:grid}.reconcile-filter,.comparison-filter-bar{display:grid;grid-template-columns:1fr 1fr}.reconcile-filter label:first-child{grid-column:1/-1}.reconcile-filter select,.reconcile-filter input,.comparison-filter-bar select{width:100%;min-width:0}.comparison-filter-bar small{margin:0;grid-column:1/-1}.reconcile-kpis{grid-template-columns:1fr 1fr}.ledger-summary-head{display:grid;grid-template-columns:1fr 1fr}.ledger-filter-total{min-width:0}.ledger-selected-actions{grid-column:1/-1;margin:0;display:grid;grid-template-columns:1fr 1fr}.ledger-summary-head .ledger-export{grid-column:1/-1;margin:0;width:100%}.ledger-table{min-width:0;table-layout:fixed;font-size:10px}.ledger-table th,.ledger-table td{padding:7px 5px;white-space:normal;overflow-wrap:break-word}.ledger-table .money{white-space:nowrap}.report-box h3{padding:10px;font-size:12px}.report-box h3 button{white-space:nowrap}.revenue-editor-form{grid-template-columns:1fr 1fr}.revenue-editor-form .editor-note,.revenue-editor-form .editor-entered-by{grid-column:1/-1}}
      @media(max-width:760px){.detail-filter-actions{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important}.detail-filter-actions button{display:flex;align-items:center;justify-content:center;width:100%;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ledger-table{display:block;min-width:0;table-layout:auto}.ledger-table thead{display:none}.ledger-table tbody{display:grid;gap:10px;padding:10px}.ledger-table tr{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));border:1px solid #b8d0c3;border-radius:12px;overflow:hidden;background:#fff}.ledger-table td{display:grid!important;grid-template-columns:minmax(76px,.8fr) minmax(0,1.2fr);align-items:start;gap:6px;width:auto!important;padding:8px 9px;white-space:normal;overflow-wrap:anywhere;border:0;border-bottom:1px solid #e3ebe6;font-size:11px}.ledger-table td::before{content:attr(data-label);color:#476357;font-size:9px;font-weight:900;letter-spacing:.04em;text-transform:uppercase}.ledger-table td:nth-child(4){grid-column:1/-1}.ledger-table td:nth-last-child(-n+2){border-bottom:0}.ledger-table .money{text-align:left;white-space:normal}.ledger-table tr.purchase-row td{background:#f8fbf9}}
      @media(max-width:460px){.detail-filter-panel,.detail-filter-secondary{grid-template-columns:1fr}.detail-filter-panel>label:first-child{grid-column:auto}.revenue-actions{grid-template-columns:1fr}.reconcile-filter,.comparison-filter-bar,.reconcile-kpis{grid-template-columns:1fr}.reconcile-filter label:first-child,.comparison-filter-bar small{grid-column:auto}}
      @media(max-width:760px){.revenue-entry-form{grid-template-columns:1fr;grid-template-areas:"title" "date" "income" "income-note" "expense" "expense-note" "save"}.revenue-entry-form .entry-date,.revenue-entry-form .entry-note,.revenue-entry-form > button{grid-column:auto}.revenue-entry-form > button{width:100%}.revenue-tip-editor .vera-date-input{position:relative;width:100%;max-width:100%;min-width:0;overflow:hidden}.revenue-tip-editor .vera-date-input>input[type="text"]{display:block;width:100%;min-width:0;padding-right:48px!important;color:#173329;background:#fff;font-size:16px;font-weight:800;opacity:1}.revenue-tip-editor .vera-date-picker-button{right:4px;width:38px}.revenue-tip-editor .vera-native-date-picker{left:auto!important;right:4px!important;width:38px!important;max-width:38px!important}}
    `}</style>

    <div data-ui-key="u-6a3dd201fbe6" className="page-heading">
      <div><span className="eyebrow"><CircleDollarSign size={14} /> Tài chính</span><h1>DOANH THU</h1><p className="revenue-source">Dữ liệu Thu/Chi được lưu trực tiếp trên server VERA SPA.</p></div>
      <button data-ui-key="u-416bf407a667" data-ui-label-default="Làm mới" className="secondary-button" type="button" onClick={() => { setNotice(''); setRevision((value) => value + 1); setReconcileRevision((value) => value + 1) }} disabled={busy || reconcileBusy}><RefreshCw size={16} className={(busy || reconcileBusy) ? 'spin' : ''} /><UiCustomText uiKey="u-416bf407a667"> Làm mới</UiCustomText></button>
    </div>
    <StableFeedback>{(error || realtimeError) && <div className="error-box">{error || realtimeError}</div>}
    {notice && <div className="success-box">{notice}</div>}
    {sharedSource.error && <div className="error-box">{sharedSource.error}</div>}
    {tipLoadError && <div className="error-box">{tipLoadError}</div>}</StableFeedback>

    {isAdmin && <section data-ui-key="u-c8da699c05ac" className="revenue-source-toolbar">
      <div className="revenue-source-toggle" role="group" aria-label="Nguồn dữ liệu doanh thu">
        <button data-ui-key="u-2cf563011ccb" data-ui-label-default="Manual · Thủ công" type="button" className={revenueSource === 'manual' ? 'active' : ''} disabled={!sourceReady || !sharedSourceSupported || sharedSource.changing || savingEntry || savingTip || Boolean(importingRevenue) || (!autoMode && Boolean(entryEditor))} onClick={() => sharedSource.change('manual')}><UiCustomText uiKey="u-2cf563011ccb">Manual · Thủ công</UiCustomText></button>
        <button data-ui-key="u-38afe49fa1cb" data-ui-label-default="Auto · Tự động hệ thống" type="button" className={revenueSource === 'auto' ? 'active' : ''} disabled={!sourceReady || !sharedSourceSupported || sharedSource.changing || savingEntry || savingTip || Boolean(importingRevenue) || (!autoMode && Boolean(entryEditor))} onClick={() => sharedSource.change('auto')}><UiCustomText uiKey="u-38afe49fa1cb">Auto · Tự động hệ thống</UiCustomText></button>
        <button data-ui-key="u-967badc6d902" data-ui-label-default="Dịch vụ Manual · Tip Auto" type="button" className={revenueSource === 'manual_tip_auto' ? 'active' : ''} disabled={!sourceReady || !sharedSourceSupported || sharedSource.changing || savingEntry || savingTip || Boolean(importingRevenue) || (!autoMode && Boolean(entryEditor))} onClick={() => sharedSource.change('manual_tip_auto')}><UiCustomText uiKey="u-967badc6d902">Dịch vụ Manual · Tip Auto</UiCustomText></button>
      </div>
    </section>}

    {commonReport && <p className="revenue-meta">Manual và Auto dùng chung báo cáo: lịch sử Manual đến 24-09-2026, thanh toán và Nhập mua từ 25-09-2026. Sổ nhập tay sau mốc này được giữ riêng, không cộng lại vào tổng.</p>}
    <div className="revenue-meta" role="status">{!sourceReady ? 'Đang tải chế độ Doanh thu…' : !sharedSourceSupported ? 'Cần chạy Deploy VPS Production để bật chế độ Doanh thu dùng chung. Manual hiện tại vẫn sử dụng được.' : autoMode
      ? 'Auto · Tự động hệ thống · Áp dụng cho mọi tài khoản. Lịch sử Manual từ 05-09-2025 đến 24-09-2026; từ 25-09-2026, Thu = tiền dịch vụ thực thu + TIP, Chi = Nhập mua. Tự kiểm tra thay đổi mỗi 5 giây khi mở trang. Đã khóa nhập, sửa, xóa và import Manual.'
      : 'Manual · Nhập Thu/Chi theo quyền được cấp.'}</div>

    {canCreateEntry && !autoMode && <form className="revenue-entry-form" onSubmit={submitRevenueEntry}>
      <h2>NHẬP DOANH THU - CHI PHÍ</h2>
      <label className="entry-date">Ngày giao dịch<VeraDateInput aria-label="Ngày giao dịch" value={entryDate} onChange={(event) => setEntryDate(event.target.value)} disabled={savingEntry}/></label>
      <label className="entry-amount">Số tiền Thu<VeraMoneyInput value={entryIncomeAmount} onChange={(event) => setEntryIncomeAmount(event.target.value)} placeholder="0" disabled={savingEntry}/></label>
      <label className="entry-note">Ghi chú Thu<input className={!entryIncomeAmount && !incomeNoteEdited ? 'auto-note-empty' : ''} type="text" maxLength={1000} value={entryIncomeNote} onChange={(event) => { setIncomeNoteEdited(true); setEntryIncomeNote(event.target.value) }} placeholder="Doanh thu + ngày giao dịch" disabled={savingEntry}/></label>
      <label className="entry-amount entry-expense">Số tiền Chi<VeraMoneyInput value={entryExpenseAmount} onChange={(event) => setEntryExpenseAmount(event.target.value)} placeholder="0" disabled={savingEntry}/></label>
      <label className="entry-note entry-expense-note">Ghi chú Chi<input className={!entryExpenseAmount && !expenseNoteEdited ? 'auto-note-empty' : ''} type="text" maxLength={1000} value={entryExpenseNote} onChange={(event) => { setExpenseNoteEdited(true); setEntryExpenseNote(event.target.value) }} placeholder="Chi phí + ngày giao dịch" disabled={savingEntry}/></label>
      <button data-ui-key="u-4c1eb92b9b18" type="submit" className="primary-button" disabled={savingEntry}><Save size={16}/>{savingEntry ? 'Đang ghi…' : 'Lưu Thu + Chi'}</button>
    </form>}

    {canViewAdminRevenueSummary && <section data-ui-key="u-4e91fcf9b37c" className="revenue-period" aria-label="Khoảng dữ liệu Doanh thu">
      <article className="revenue-period-card"><CalendarDays size={20} /><div><span>Ngày bắt đầu</span><strong>{busy && !data ? '…' : (data?.start_date_label || '—')}</strong></div></article>
      <article className="revenue-period-card revenue-report-cutoff"><CalendarDays size={20} /><div><span>Báo cáo tới ngày</span><strong>{busy && !data ? '…' : ((commonReport || autoMode) && data?.end_date ? formatVeraDate(data.end_date) : data?.current_date_label || '—')}</strong></div>

      </article>
    </section>}

    {canViewAdminRevenueSummary && canEditTip && <section data-ui-key="u-a5723df4546d" className="revenue-tip-editor" ref={tipEditorRef}>
      <label className="revenue-tip-amount">TIỀN TIP TRONG KỲ<input type="text" inputMode="none" value={money(commonReport ? data?.period_tip : tip)} readOnly aria-label="Tiền TIP trong kỳ tự động" /></label>
      <label>Từ ngày tính TIP<VeraDateInput aria-label="Ngày bắt đầu Tiền TIP" value={tipStart} min={autoMode ? '2025-09-05' : undefined} max={tipEnd || data?.current_date || undefined} disabled={savingTip || busy} onChange={(event) => setTipStart(event.target.value)} /></label>
      <label>{commonReport || autoMode ? 'Đến ngày (báo cáo và TIP)' : 'Đến ngày tính TIP'}<VeraDateInput aria-label="Đến ngày Tiền TIP" value={tipEnd} min={tipStart || undefined} max={data?.current_date || undefined} disabled={savingTip || busy} onChange={(event) => setTipEnd(event.target.value)} /></label>
      <div className="revenue-tip-current"><button data-ui-key="u-225f35c741ac" type="button" className="secondary-button" disabled={savingTip || busy || !data?.current_date} onClick={() => setTipEnd(data?.current_date || '')}>Dùng ngày này · {data?.current_date_label || '—'}</button></div>
      {!hybridMode && <button data-ui-key="u-e90fac269afb" type="button" className="primary-button" onClick={submitTip} disabled={savingTip || busy || tipBusy || Boolean(tipLoadError) || !tipStart || !tipEnd || tipStart > tipEnd}><Save size={16}/> {savingTip ? 'Đang lưu…' : 'Lưu Tiền TIP'}</button>}
      {(commonReport || autoMode) && <p className="revenue-auto-date-note">Đổi Đến ngày sẽ tự tính Tổng thu, Tổng chi và Còn lại từ 05-09-2025 đến hết ngày chọn. TIP tính theo Từ ngày tính TIP → Đến ngày.</p>}
      <small>{hybridMode ? 'Dịch vụ Manual · Tip Auto: ' : ''}Tiền TIP tự động cộng từ TIP của nhân viên trong báo cáo hóa đơn Live Tour theo đúng khoảng Ngày bắt đầu → Đến ngày. Kỳ 1 mặc định bắt đầu ngày 01, kỳ 2 mặc định bắt đầu ngày 16; Đến ngày mặc định bằng Ngày hiện tại. Đổi một trong hai ngày sẽ tự lọc và tính lại số TIP ngay.</small>
    </section>}

    {canViewAdminRevenueSummary && <div className="admin-revenue-summary">
      {commonReport && busy && <p role="status">Đang tính báo cáo và TIP theo cùng kỳ đã chọn…</p>}
      <section data-ui-key="u-a4c778e6c2bb" className="revenue-grid" aria-live="polite" aria-busy={busy}>
        {cards.map(({ key, label, value, icon: Icon }) => <article className={`revenue-card ${key}`} key={key}><div data-ui-key="u-2ffef07af4fc" className="revenue-card-head"><Icon size={18} aria-hidden="true" /> {label}</div><AutoFitMoney>{busy && !data ? '…' : money(value)}</AutoFitMoney></article>)}
      </section>
      {data && <div className="revenue-formula">{hybridMode ? <>Tổng doanh thu = Tiền dịch vụ {hybridMode ? '(Manual)' : ''} + Tiền tip (Auto) = <strong>{money(data.total_revenue)}</strong></> : <>Tổng thu - Tổng chi = <strong>{money(data.net_income ?? (Number(data.total_income || 0) - Number(data.total_expense || 0)))}</strong> · Còn lại = (Tổng thu - Tổng chi) - Tiền TIP trong kỳ = <strong>{money(data.balance)}</strong></>}</div>}
    </div>}

    <UiToolbar data-ui-key="u-10492b384942" className="revenue-tabs" role="tablist" aria-label="Doanh thu và chi phí">
      <button data-ui-key="u-f01408c2e75b" data-ui-label-default="Doanh thu-Chi phí" type="button" className={`revenue-tab ${activeTab === 'ledger' ? 'active' : ''}`} onClick={() => setActiveTab('ledger')}><UiCustomText uiKey="u-f01408c2e75b">Doanh thu-Chi phí</UiCustomText></button>
      <button data-ui-key="u-b828ccc54b6c" data-ui-label-default="Báo cáo mua hàng" type="button" className={`revenue-tab ${activeTab === 'purchase' ? 'active' : ''}`} onClick={() => setActiveTab('purchase')}><UiCustomText uiKey="u-b828ccc54b6c">Báo cáo mua hàng</UiCustomText></button>
      {canViewAdminRevenueSummary && <button data-ui-key="u-3a9aa4e685fc" data-ui-label-default="Tổng quan" type="button" className={`revenue-tab ${activeTab === 'overview' ? 'active' : ''}`} onClick={() => setActiveTab('overview')}><UiCustomText uiKey="u-3a9aa4e685fc">Tổng quan</UiCustomText></button>}
      {isAdmin && <button data-ui-key="u-c1d88cedf5da" data-ui-label-default="Lịch sử sửa, xóa" type="button" className={`revenue-tab ${activeTab === 'audit' ? 'active' : ''}`} onClick={() => setActiveTab('audit')}><UiCustomText uiKey="u-c1d88cedf5da">Lịch sử sửa, xóa</UiCustomText></button>}
      {isAdmin && <button data-ui-key="u-3b0a4c838849" data-ui-label-default="Kiểm tra dữ liệu trùng" type="button" className={`revenue-tab ${activeTab === 'duplicates' ? 'active' : ''}`} onClick={() => setActiveTab('duplicates')}><UiCustomText uiKey="u-3b0a4c838849">Kiểm tra dữ liệu trùng</UiCustomText></button>}
    </UiToolbar>

    {activeTab !== 'overview' && <section data-ui-key="u-ccb707340dfb" className="detail-tab-panel">
      {commonReport && !autoMode && activeTab === 'ledger' && <div className="revenue-ledger-view" role="group" aria-label="Nguồn sổ thu chi">
        <button type="button" aria-pressed={!manualLedger} onClick={() => { setManualLedger(false); setSelectedLedgerId(null) }}>Báo cáo chung</button>
        <button type="button" aria-pressed={manualLedger} onClick={() => { setManualLedger(true); setSelectedLedgerId(null) }}>Sổ nhập tay</button>
      </div>}
      <div data-ui-key="u-92de57f35d25" className="detail-filter-panel">
        <label>Thời gian<select value={detailPreset} onChange={(event) => setDetailPreset(event.target.value)}>{reconcileFilters.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Từ ngày<VeraDateInput value={detailPreset === 'custom' ? detailStart : (detailData?.start_date || '')} onChange={(event) => { setDetailPreset('custom'); setDetailStart(event.target.value) }} /></label>
        <label>Đến ngày<VeraDateInput value={detailPreset === 'custom' ? detailEnd : (detailData?.end_date || '')} onChange={(event) => { setDetailPreset('custom'); setDetailEnd(event.target.value) }} /></label>
        {activeTab === 'ledger' ? <div className="detail-filter-secondary">
          <label>Ngày<VeraDateInput value={ledgerDate} onChange={(event) => setLedgerDate(event.target.value)} /></label>
          <label>Loại giao dịch<select value={ledgerType} onChange={(event) => setLedgerType(event.target.value)}><option value="">Tất cả</option>{ledgerTypes.map(type => <option key={type} value={type}>{type}</option>)}</select></label>
          <label>Số tiền<VeraMoneyInput value={ledgerAmountFilter} onChange={(event) => setLedgerAmountFilter(event.target.value)} placeholder="Tìm số tiền" /></label>
          <label>Ghi chú<input value={ledgerNoteFilter} onChange={(event) => setLedgerNoteFilter(event.target.value)} placeholder="Tìm nội dung ghi chú" /></label>
          <label>Ngày nhập<VeraDateInput value={ledgerEnteredDate} onChange={(event) => setLedgerEnteredDate(event.target.value)} /></label>
          <label>Người nhập<input value={ledgerEnteredByFilter} onChange={(event) => setLedgerEnteredByFilter(event.target.value)} placeholder="Tìm người nhập" /></label>
        </div> : activeTab === 'purchase' ? <div className="detail-filter-secondary">
          <label>Ngày nhập<VeraDateInput value={purchaseDate} onChange={(event) => setPurchaseDate(event.target.value)} /></label>
          <label>Chi tiết hàng hóa<input value={purchaseItemFilter} onChange={(event) => setPurchaseItemFilter(event.target.value)} placeholder="Tìm hàng hóa" /></label>
          <label>Người đặt<input value={purchaseBuyerFilter} onChange={(event) => setPurchaseBuyerFilter(event.target.value)} placeholder="Tìm người đặt" /></label>
          <label>User<input value={purchaseUserFilter} onChange={(event) => setPurchaseUserFilter(event.target.value)} placeholder="Tìm user" /></label>
        </div> : null}
        <UiToolbar data-ui-key="u-d3c2154b8b3d" className="detail-filter-actions">
          {reconcileFilters.filter(([value]) => value !== 'custom').map(([value, label]) => <button data-ui-key="u-983619469a80" type="button" key={value} className={`secondary-button ${detailPreset === value ? 'active' : ''}`} onClick={() => { setDetailPreset(value); setDetailStart(''); setDetailEnd('') }}>{label}</button>)}
          <button data-ui-key="u-e82fca1fc852" data-ui-label-default="Xóa lọc chi tiết" type="button" className="secondary-button" onClick={() => { setLedgerDate(''); setLedgerType(''); setLedgerAmountFilter(''); setLedgerNoteFilter(''); setLedgerEnteredDate(''); setLedgerEnteredByFilter(''); setPurchaseDate(''); setPurchaseItemFilter(''); setPurchaseBuyerFilter(''); setPurchaseUserFilter('') }}><UiCustomText uiKey="u-e82fca1fc852">Xóa lọc chi tiết</UiCustomText></button>
        </UiToolbar>
      </div>
      <StableFeedback>{detailError && <div className="error-box">{detailError}</div>}</StableFeedback>
      {detailBusy && !detailData && <div className="revenue-meta">Đang tải dữ liệu…</div>}
      {activeTab === 'ledger' && <TablePager pagination={{ ...ledgerPagination, setPage: page => { setSelectedLedgerId(null); ledgerPagination.setPage(page) } }} label="Thu Chi"/>}
      {activeTab === 'purchase' && <TablePager pagination={purchasePagination} label="Nhập mua"/>}
      {activeTab === 'audit' && <TablePager pagination={auditPagination} label="Lịch sử Thu Chi"/>}
      {activeTab === 'duplicates' && <TablePager pagination={duplicatePagination} label="Dữ liệu trùng"/>}
      {activeTab === 'ledger' && <div className="report-box"><div className="ledger-summary-head" aria-live="polite"><article className="ledger-filter-total"><TrendingUp size={18}/><div><span>Doanh thu theo bộ lọc</span><strong>{money(ledgerTotals.income)}</strong></div></article><article className="ledger-filter-total expense"><TrendingDown size={18}/><div><span>Chi phí theo bộ lọc</span><strong>{money(ledgerTotals.expense)}</strong></div></article>{(canEditEntry || canDeleteEntry || (isAdmin && autoMode)) && <UiToolbar data-ui-key="u-ad73a3b151e3" className="ledger-selected-actions">{(canEditEntry || (isAdmin && autoMode)) && <button data-ui-key="u-81a960c20c4e" data-ui-label-default="Sửa dòng đã chọn" type="button" className="secondary-button compact" disabled={autoMode || !selectedLedgerRow} title={autoMode ? 'Auto đang bật: đã khóa sửa và xóa dữ liệu Manual.' : undefined} onClick={() => openRevenueEditor('edit')}><UiCustomText uiKey="u-81a960c20c4e">Sửa dòng đã chọn</UiCustomText></button>}{(canDeleteEntry || (isAdmin && autoMode)) && <button data-ui-key="u-8f6a391301f0" data-ui-label-default="Xóa dòng đã chọn" type="button" className="secondary-button compact danger-button" disabled={autoMode || !selectedLedgerRow} title={autoMode ? 'Auto đang bật: đã khóa sửa và xóa dữ liệu Manual.' : undefined} onClick={() => openRevenueEditor('delete')}><UiCustomText uiKey="u-8f6a391301f0">Xóa dòng đã chọn</UiCustomText></button>}</UiToolbar>}{isAdmin && sourceReady && <><input ref={revenueImportAppendRef} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden onChange={(event) => handleRevenueImport(event, 'append')} /><input ref={revenueImportReplaceRef} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden onChange={(event) => handleRevenueImport(event, 'replace')} /><button data-ui-key="u-7e27da35f77d" type="button" className="secondary-button compact ledger-import" disabled={autoMode || Boolean(importingRevenue)} title={autoMode ? 'Auto đang bật: đã khóa import Manual.' : undefined} onClick={() => revenueImportAppendRef.current?.click()}><Upload size={14}/>{importingRevenue === 'append' ? 'Đang import…' : 'Import thêm mới'}</button><button data-ui-key="u-20ceef2515eb" type="button" className="secondary-button compact ledger-import danger-button" disabled={autoMode || Boolean(importingRevenue)} title={autoMode ? 'Auto đang bật: đã khóa import Manual.' : undefined} onClick={() => revenueImportReplaceRef.current?.click()}><Upload size={14}/>{importingRevenue === 'replace' ? 'Đang thay thế…' : 'Import thay toàn bộ'}</button></>}<button data-ui-key="u-69a7e9901e0b" type="button" className="secondary-button compact ledger-export" disabled={exportingLedger || detailBusy || !detailData} onClick={exportLedger}><Download size={14}/>{exportingLedger ? 'Đang xuất…' : 'Xuất Excel'}</button></div><div className="report-scroll"><table data-ui-key="u-3a04a395affa" className="report-table ledger-table"><thead><tr>{(canEditEntry || canDeleteEntry) && revenueSource !== 'auto' && <th data-ui-key="u-8a7b4635a7e5" aria-label="Chọn dòng" className="ledger-check-column"/>}<th data-ui-key="u-98934399c8f7" data-ui-label-default="Ngày"><UiCustomText uiKey="u-98934399c8f7">Ngày</UiCustomText></th><th data-ui-key="u-17fd19573619" data-ui-label-default="Loại giao dịch"><UiCustomText uiKey="u-17fd19573619">Loại giao dịch</UiCustomText></th><th data-ui-key="u-2a5610621cae" data-ui-label-default="Số tiền" className="money"><UiCustomText uiKey="u-2a5610621cae">Số tiền</UiCustomText></th><th data-ui-key="u-8b640f64dc26" data-ui-label-default="Ghi chú"><UiCustomText uiKey="u-8b640f64dc26">Ghi chú</UiCustomText></th><th data-ui-key="u-3c424c661a02" data-ui-label-default="Ngày nhập"><UiCustomText uiKey="u-3c424c661a02">Ngày nhập</UiCustomText></th><th data-ui-key="u-5f9896c666d2" data-ui-label-default="Giờ nhập"><UiCustomText uiKey="u-5f9896c666d2">Giờ nhập</UiCustomText></th><th data-ui-key="u-21727193cf42" data-ui-label-default="Người nhập"><UiCustomText uiKey="u-21727193cf42">Người nhập</UiCustomText></th></tr></thead><tbody>
        {ledgerPagination.rows.map((row, index) => <tr key={`${row.date}-${index}`} className={`${row.is_purchase ? 'purchase-row' : ''} ${selectedLedgerId === row.id ? 'selected-ledger-row' : ''}`}>{(canEditEntry || canDeleteEntry) && revenueSource !== 'auto' && <td data-label="Chọn" className="ledger-check-column"><input type="checkbox" checked={selectedLedgerId === row.id} disabled={!canManageCurrentEntry(row)} onChange={() => setSelectedLedgerId(current => current === row.id ? null : row.id)} aria-label={`Chọn dòng ${row.type} ${row.date_label}`}/></td>}<td data-label="Ngày">{row.date_label}</td><td data-label="Loại giao dịch">{row.type}</td><td data-label="Số tiền" className="money">{money(row.amount)}</td><td data-label="Ghi chú">{row.note || '—'}</td><td data-label="Ngày nhập">{row.entered_date_label || '—'}</td><td data-label="Giờ nhập">{row.entered_time || '—'}</td><td data-label="Người nhập">{row.entered_by || '—'}</td></tr>)}
        {!ledgerRows.length && <tr><td colSpan={(canEditEntry || canDeleteEntry) && revenueSource !== 'auto' ? 8 : 7}>Không có dữ liệu phù hợp bộ lọc.</td></tr>}
      </tbody></table></div></div>}
      {activeTab === 'purchase' && <div className="report-box"><h3><FileSpreadsheet size={16}/> Báo cáo mua hàng</h3><div className="report-scroll"><table data-ui-key="u-131ebc13c4b2" className="report-table"><thead><tr><th data-ui-key="u-9b382b46eeb2" data-ui-label-default="Ngày nhập"><UiCustomText uiKey="u-9b382b46eeb2">Ngày nhập</UiCustomText></th><th data-ui-key="u-cd63804a4c3f" data-ui-label-default="Chi tiết hàng hóa"><UiCustomText uiKey="u-cd63804a4c3f">Chi tiết hàng hóa</UiCustomText></th><th data-ui-key="u-e8ff07730168" data-ui-label-default="Số lượng" className="money"><UiCustomText uiKey="u-e8ff07730168">Số lượng</UiCustomText></th><th data-ui-key="u-3941ca1390a3" data-ui-label-default="Đơn giá" className="money"><UiCustomText uiKey="u-3941ca1390a3">Đơn giá</UiCustomText></th><th data-ui-key="u-c8a3a799561b" data-ui-label-default="Thành Tiền" className="money"><UiCustomText uiKey="u-c8a3a799561b">Thành Tiền</UiCustomText></th><th data-ui-key="u-9460b258f67d" data-ui-label-default="Người đặt"><UiCustomText uiKey="u-9460b258f67d">Người đặt</UiCustomText></th><th data-ui-key="u-df08e166a37d" data-ui-label-default="User"><UiCustomText uiKey="u-df08e166a37d">User</UiCustomText></th></tr></thead><tbody>
        {purchasePagination.rows.map((row, index) => <tr key={`${row.date}-${index}`}><td>{row.date_label}</td><td>{row.item || '—'}</td><td className="money">{numberText(row.quantity)}</td><td className="money">{money(row.unit_price)}</td><td className="money">{money(row.amount)}</td><td>{row.buyer || '—'}</td><td>{row.user || '—'}</td></tr>)}
        {!purchaseRows.length && <tr><td colSpan="7">Không có dữ liệu phù hợp bộ lọc.</td></tr>}
      </tbody></table></div></div>}
      {activeTab === 'audit' && isAdmin && <section data-ui-key="u-563f57362ebb" className="report-box"><h3>LỊCH SỬ SỬA, XÓA <button data-ui-key="u-e22766ca7947" data-ui-label-default="Xuất Excel" type="button" className="secondary-button compact" onClick={async () => { const params = new URLSearchParams({ time_range: detailPreset }); if (detailPreset === 'custom') { params.set('start', detailStart); params.set('end', detailEnd) } const response = await fetch(`${apiBase}/v2/revenue/audit/export.xlsx?${params}`, { headers: await authorizedHeaders() }); if (!response.ok) throw new Error('Không xuất được lịch sử.'); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'VERA_LichSu_SuaXoa_ThuChi.xlsx'; link.click(); URL.revokeObjectURL(url) }}><Download size={14}/><UiCustomText uiKey="u-e22766ca7947">Xuất Excel</UiCustomText></button></h3><div className="report-scroll"><table data-ui-key="u-c0e7008926f8" className="report-table"><thead><tr><th data-ui-key="u-ac5f4e3ba3ef" data-ui-label-default="Thời điểm"><UiCustomText uiKey="u-ac5f4e3ba3ef">Thời điểm</UiCustomText></th><th data-ui-key="u-61a907a8bf21" data-ui-label-default="Hành động"><UiCustomText uiKey="u-61a907a8bf21">Hành động</UiCustomText></th><th data-ui-key="u-6d99bf82ca20" data-ui-label-default="Mã dòng"><UiCustomText uiKey="u-6d99bf82ca20">Mã dòng</UiCustomText></th><th data-ui-key="u-a8ba0288f3fd" data-ui-label-default="Người thao tác"><UiCustomText uiKey="u-a8ba0288f3fd">Người thao tác</UiCustomText></th><th data-ui-key="u-c6a8df28f9e3" data-ui-label-default="Trước"><UiCustomText uiKey="u-c6a8df28f9e3">Trước</UiCustomText></th><th data-ui-key="u-aacbefd60e4d" data-ui-label-default="Sau"><UiCustomText uiKey="u-aacbefd60e4d">Sau</UiCustomText></th></tr></thead><tbody>{auditPagination.rows.map(row => <tr key={row.id}><td>{row.audited_at_label}</td><td>{row.action_label}</td><td>{row.entry_id}</td><td>{row.actor || '—'}</td><td className="audit-payload">{row.before?.transaction_type} · {money(row.before?.amount)} · {row.before?.note || '—'}</td><td className="audit-payload">{row.after ? `${row.after.transaction_type} · ${money(row.after.amount)} · ${row.after.note || '—'}` : 'Đã xóa'}</td></tr>)}{!auditData.rows?.length && <tr><td colSpan="6">Chưa có lịch sử sửa hoặc xóa trong kỳ.</td></tr>}</tbody></table></div></section>}
      {activeTab === 'duplicates' && isAdmin && <section data-ui-key="u-b8af6fb801ee" className="report-box"><h3>KIỂM TRA DỮ LIỆU TRÙNG <button data-ui-key="u-7ef61e03ae3b" data-ui-label-default="Xuất Excel" type="button" className="secondary-button compact" onClick={async () => { const params = new URLSearchParams({ time_range: detailPreset }); if (detailPreset === 'custom') { params.set('start', detailStart); params.set('end', detailEnd) } const response = await fetch(`${apiBase}/v2/revenue/duplicates/export.xlsx?${params}`, { headers: await authorizedHeaders() }); if (!response.ok) throw new Error('Không xuất được dữ liệu trùng.'); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'VERA_KiemTra_DuLieuTrung_ThuChi.xlsx'; link.click(); URL.revokeObjectURL(url) }}><Download size={14}/><UiCustomText uiKey="u-7ef61e03ae3b">Xuất Excel</UiCustomText></button></h3><div className="duplicate-summary"><strong>{duplicateData.group_count || 0} nhóm trùng</strong><span>{duplicateData.duplicate_row_count || 0} dòng dư · {money(duplicateData.duplicate_amount)}</span></div><div className="report-scroll"><table data-ui-key="u-9f90a50a326c" className="report-table"><thead><tr><th data-ui-key="u-92200f0b4436" data-ui-label-default="Ngày"><UiCustomText uiKey="u-92200f0b4436">Ngày</UiCustomText></th><th data-ui-key="u-8a016edf1e9e" data-ui-label-default="Loại"><UiCustomText uiKey="u-8a016edf1e9e">Loại</UiCustomText></th><th data-ui-key="u-d9539f83a1bf" data-ui-label-default="Số tiền"><UiCustomText uiKey="u-d9539f83a1bf">Số tiền</UiCustomText></th><th data-ui-key="u-4aeb6c3fa75e" data-ui-label-default="Ghi chú"><UiCustomText uiKey="u-4aeb6c3fa75e">Ghi chú</UiCustomText></th><th data-ui-key="u-99424f72cc01" data-ui-label-default="Số dòng"><UiCustomText uiKey="u-99424f72cc01">Số dòng</UiCustomText></th><th data-ui-key="u-67345e23d144" data-ui-label-default="Người nhập"><UiCustomText uiKey="u-67345e23d144">Người nhập</UiCustomText></th></tr></thead><tbody>{duplicatePagination.rows.map(group => <tr key={group.entry_ids.join('-')}><td>{group.date_label}</td><td>{group.type}</td><td className="money">{money(group.amount)}</td><td>{group.note || '—'}</td><td>{group.count}</td><td>{group.entered_by.join(', ') || '—'}</td></tr>)}{!duplicateData.groups?.length && <tr><td colSpan="6">Không phát hiện dữ liệu trùng chính xác trong kỳ.</td></tr>}</tbody></table></div></section>}
    </section>}

    {canViewAdminRevenueSummary && activeTab === 'overview' && <section data-ui-key="u-d6d755ba1342" className="reconcile-panel">
      <div className="reconcile-head">
        <div><span className="eyebrow"><FileSpreadsheet size={14}/> Đối chiếu chi mua hàng</span><h2>BÁO CÁO MUA HÀNG ↔ QUẢN LÝ THU CHI</h2><p>So sánh từng ngày: tổng cột Thành Tiền của BaoCaoMuaHang với các dòng Input có B = Chi và nội dung mua hàng, số tiền lấy từ cột C. Chênh lệch từ 1đ đến 5.000đ được xếp GẦN KHỚP; trên 5.000đ là KHÔNG KHỚP.</p></div>
        <div className="reconcile-filter">
          <label>Bộ lọc thời gian<select value={filterPreset} onChange={(event) => setFilterPreset(event.target.value)}>{reconcileFilters.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
          {filterPreset === 'custom' && <><label>Từ ngày<VeraDateInput aria-label="Từ ngày" value={customStart} onChange={(event) => setCustomStart(event.target.value)} /></label><label>Đến ngày<VeraDateInput aria-label="Đến ngày" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} /></label></>}
        </div>
      </div>

      {filterPreset === 'custom' && (!customStart || !customEnd) && <div className="revenue-meta">Chọn đủ Từ ngày và Đến ngày để xem hai báo cáo.</div>}
      <StableFeedback>{reconcileError && <div className="error-box">{reconcileError}</div>}</StableFeedback>
      {reconcileBusy && !reconcile && <div className="revenue-meta">Đang đọc BaoCaoMuaHang và Quản lý Thu Chi…</div>}

      {reconcile && <>
        <TablePager pagination={comparisonPagination} label="Đối chiếu mua hàng"/>
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
          <div className="report-scroll"><table data-ui-key="u-0957ba74e58d" className="report-table comparison-table"><thead><tr><th data-ui-key="u-2e8b67a05fa0" data-ui-label-default="Ngày"><UiCustomText uiKey="u-2e8b67a05fa0">Ngày</UiCustomText></th><th data-ui-key="u-f60c1cff5bea" data-ui-label-default="BaoCaoMuaHang" className="money"><UiCustomText uiKey="u-f60c1cff5bea">BaoCaoMuaHang</UiCustomText></th><th data-ui-key="u-55bb581952d1" data-ui-label-default="Thu Chi · Mua hàng" className="money"><UiCustomText uiKey="u-55bb581952d1">Thu Chi · Mua hàng</UiCustomText></th><th data-ui-key="u-5226d5d29e1e" data-ui-label-default="Chênh lệch" className="money"><UiCustomText uiKey="u-5226d5d29e1e">Chênh lệch</UiCustomText></th><th data-ui-key="u-67a0a91eb11b" data-ui-label-default="Trạng thái"><UiCustomText uiKey="u-67a0a91eb11b">Trạng thái</UiCustomText></th><th data-ui-key="u-60096cdffb64" data-ui-label-default="Chi tiết nội dung"><UiCustomText uiKey="u-60096cdffb64">Chi tiết nội dung</UiCustomText></th></tr></thead><tbody>
            {comparisonPagination.rows.map((row) => <tr key={row.date} className={statusClass(row.status)}><td>{row.date_label}</td><td className="money">{money(row.purchase_total)}</td><td className="money">{money(row.ledger_purchase_total)}</td><td className="money">{money(row.difference)}</td><td className={statusTextClass(row.status)}>{row.status || '—'}</td><td className="detail-cell"><div><strong>BaoCaoMuaHang:</strong> {row.purchase_detail_text || '—'}</div><div><strong>Thu Chi:</strong> {row.ledger_detail_text || '—'}</div></td></tr>)}
            {!comparisonRows.length && <tr><td colSpan="6">Không có dữ liệu phù hợp với bộ lọc Chênh lệch / Trạng thái.</td></tr>}
          </tbody></table></div>
        </div>

        <div className="revenue-meta">Ngày trong dữ liệu Thu/Chi ưu tiên lấy từ ngày ghi trong cột Ghi chú, sau đó mới dùng cột Ngày giao dịch. Khi phát hiện một ngày có trạng thái <strong>KHÔNG KHỚP</strong> hoặc số liệu của ngày KHÔNG KHỚP thay đổi, hệ thống tự gửi Web Push chi tiết cho <strong>Admin, Quản lý và Lễ tân</strong>; cùng một trạng thái/số liệu sẽ không gửi lặp lại chỉ vì làm mới trang.</div>
      </>}
    </section>}
    {entryEditor && !autoMode && <div className="revenue-editor-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setEntryEditor(null) }}><section data-ui-key="u-182f1caba9f8" className="revenue-editor-dialog" role="dialog" aria-modal="true" aria-label={entryEditor.mode === 'delete' ? 'Xóa giao dịch Thu Chi' : 'Sửa giao dịch Thu Chi'}><header><div><span>PHIẾU THU CHI</span><h2>{entryEditor.mode === 'delete' ? 'Xác nhận xóa giao dịch' : 'Sửa nội dung giao dịch'}</h2></div><button data-ui-key="u-04ec8d69120b" data-ui-label-default="Đóng" type="button" className="secondary-button compact" onClick={() => setEntryEditor(null)}><UiCustomText uiKey="u-04ec8d69120b">Đóng</UiCustomText></button></header><div className="revenue-editor-form"><label>Loại giao dịch<select value={entryEditor.type} disabled={entryEditor.mode === 'delete'} onChange={event => setEntryEditor(current => ({ ...current, type: event.target.value }))}><option>Thu</option><option>Chi</option></select></label><label>Ngày giao dịch<VeraDateInput value={entryEditor.date} disabled={entryEditor.mode === 'delete'} onChange={event => setEntryEditor(current => ({ ...current, date: event.target.value }))}/></label><label>Số tiền<VeraMoneyInput value={entryEditor.amount} disabled={entryEditor.mode === 'delete'} onChange={event => setEntryEditor(current => ({ ...current, amount: event.target.value }))}/></label><label className="editor-note">Ghi chú<input value={entryEditor.note} disabled={entryEditor.mode === 'delete'} onChange={event => setEntryEditor(current => ({ ...current, note: event.target.value }))}/></label><label>Ngày nhập<VeraDateInput value={entryEditor.enteredDate} disabled={entryEditor.mode === 'delete'} onChange={event => setEntryEditor(current => ({ ...current, enteredDate: event.target.value }))}/></label><label>Giờ nhập<input value={entryEditor.enteredTime} disabled={entryEditor.mode === 'delete'} onChange={event => setEntryEditor(current => ({ ...current, enteredTime: event.target.value }))}/></label><label className="editor-entered-by">Người nhập<input value={entryEditor.enteredBy} disabled={entryEditor.mode === 'delete'} onChange={event => setEntryEditor(current => ({ ...current, enteredBy: event.target.value }))}/></label></div>{entryEditor.mode === 'delete' && <p className="delete-warning">Bản ghi sẽ không còn xuất hiện trong Doanh thu-Chi phí. Toàn bộ dữ liệu trước khi xóa vẫn được giữ tại tab Lịch sử sửa, xóa.</p>}<footer><button data-ui-key="u-aa46b08215a3" data-ui-label-default="Hủy" type="button" className="secondary-button" onClick={() => setEntryEditor(null)}><UiCustomText uiKey="u-aa46b08215a3">Hủy</UiCustomText></button><button data-ui-key="u-de9b1f798a22" type="button" className={`primary-button ${entryEditor.mode === 'delete' ? 'danger-button' : ''}`} onClick={saveManualRevenue}>{entryEditor.mode === 'delete' ? 'Xác nhận xóa' : 'Lưu thay đổi'}</button></footer></section></div>}
  </div>
}
