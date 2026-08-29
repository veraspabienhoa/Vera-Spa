import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { veraApi } from '../lib/api'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

const parseDisplayDate = (value) => {
  const match = String(value || '').trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/)
  if (!match) return ''
  return `${match[3]}-${match[2]}-${match[1]}`
}

const normalizeReason = (value) => String(value || '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd')
  .replace(/Đ/g, 'D')
  .toLocaleLowerCase('vi-VN')
  .replace(/\s+/g, ' ')
  .trim()

const fallbackTypeKey = (reason) => {
  const token = normalizeReason(reason)
  if (token.includes('khong phep')) return 'khong_phep'
  if (token.includes('co phep')) return 'co_phep'
  if (token.includes('phat sinh')) return 'phat_sinh'
  return 'khac'
}

const TYPE_OPTIONS = [
  { value: '', label: 'Tất cả' },
  { value: 'co_phep', label: 'Có phép' },
  { value: 'khong_phep', label: 'Không phép' },
  { value: 'vi_pham', label: 'Vi phạm' },
]

async function loadReasonTypeCatalog(signal) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const response = await fetch(`${apiBase}/v2/leave/reason-types`, {
    signal,
    headers: session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {},
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

const emptySummary = {
  totalLeave: 0,
  paid: 0,
  generated: 0,
  unpaid: 0,
  totalPenalty: 0,
}

const sumDailyStats = (days = []) => days.reduce((summary, day) => ({
  totalLeave: summary.totalLeave + Number(day.total_leave || 0),
  paid: summary.paid + Number(day.paid || 0),
  generated: summary.generated + Number(day.generated || 0),
  unpaid: summary.unpaid + Number(day.unpaid || 0),
  totalPenalty: summary.totalPenalty + Number(day.total_penalty || 0),
}), { ...emptySummary })

const sameContext = (left, right) => (
  left.start === right.start
  && left.end === right.end
  && left.employee === right.employee
  && left.displayStart === right.displayStart
  && left.displayEnd === right.displayEnd
)

export default function LeaveListPersonalStats({ user }) {
  const role = String(user?.role || '').toLowerCase()
  const isAdmin = role === 'admin'
  const ownEmployee = String(user?.employee_username || '').trim()
  const [target, setTarget] = useState(null)
  const [context, setContext] = useState({ start: '', end: '', employee: '', displayStart: '', displayEnd: '' })
  const [summary, setSummary] = useState(emptySummary)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [typeCatalog, setTypeCatalog] = useState({})
  const [catalogBusy, setCatalogBusy] = useState(false)
  const [catalogError, setCatalogError] = useState('')
  const [rowCounts, setRowCounts] = useState({ visible: 0, total: 0 })

  useEffect(() => {
    let cancelled = false
    let ownedHost = null
    let timer = null

    const syncFromList = () => {
      if (cancelled) return
      const panel = document.querySelector('.leave-list-panel')
      const tableWrap = panel?.querySelector('.leave-list-wrap')
      if (!panel || !tableWrap) return

      let host = panel.querySelector('[data-leave-list-personal-stats="true"]')
      if (!host) {
        host = document.createElement('div')
        host.dataset.leaveListPersonalStats = 'true'
        panel.insertBefore(host, tableWrap)
        ownedHost = host
      }
      setTarget((current) => current === host ? current : host)

      const description = String(panel.querySelector('.panel-title-row p')?.textContent || '')
      const rangeMatch = description.match(/Bộ lọc\s+(\d{2}\/\d{2}\/\d{4})\s*[–-]\s*(\d{2}\/\d{2}\/\d{4})/)
      if (!rangeMatch) return

      const searchValue = String(panel.querySelector('.employee-search-field input[type="search"]')?.value || '').trim()
      const next = {
        start: parseDisplayDate(rangeMatch[1]),
        end: parseDisplayDate(rangeMatch[2]),
        employee: isAdmin ? searchValue : ownEmployee,
        displayStart: rangeMatch[1],
        displayEnd: rangeMatch[2],
      }
      if (!next.start || !next.end || (!isAdmin && !next.employee)) return
      setContext((current) => sameContext(current, next) ? current : next)
    }

    const scheduleSync = () => {
      if (timer) window.clearTimeout(timer)
      timer = window.setTimeout(syncFromList, 30)
    }

    syncFromList()
    const observer = new MutationObserver(scheduleSync)
    observer.observe(document.body, { childList: true, subtree: true, characterData: true })
    document.addEventListener('input', scheduleSync, true)
    document.addEventListener('change', scheduleSync, true)
    document.addEventListener('click', scheduleSync, true)

    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
      observer.disconnect()
      document.removeEventListener('input', scheduleSync, true)
      document.removeEventListener('change', scheduleSync, true)
      document.removeEventListener('click', scheduleSync, true)
      if (ownedHost?.isConnected) ownedHost.remove()
    }
  }, [isAdmin, ownEmployee])

  useEffect(() => {
    if (!target) return undefined
    const controller = new AbortController()
    setCatalogBusy(true)
    setCatalogError('')
    loadReasonTypeCatalog(controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        const mapping = {}
        for (const item of result.items || []) {
          const key = normalizeReason(item.name)
          if (key) mapping[key] = String(item.type_key || 'khac')
        }
        setTypeCatalog(mapping)
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return
        setTypeCatalog({})
        setTypeFilter('')
        setCatalogError(err.message || 'Không tải được Loại nghỉ từ BẢNG NỘI QUY.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setCatalogBusy(false)
      })
    return () => controller.abort()
  }, [target])

  useEffect(() => {
    if (!target) return undefined
    let timer = null
    const panel = target.closest('.leave-list-panel')
    const tbody = panel?.querySelector('.leave-records-table tbody')
    if (!panel || !tbody) return undefined

    const applyFilter = () => {
      const rows = Array.from(tbody.querySelectorAll('tr'))
      let total = 0
      let visible = 0
      for (const row of rows) {
        if (row.querySelector('.empty-cell')) {
          row.style.display = ''
          continue
        }
        const reasonCell = row.querySelector('.reason-edit-cell')
        if (!reasonCell) continue
        total += 1
        const select = reasonCell.querySelector('select')
        const reason = String(select?.value || reasonCell.textContent || '').trim()
        const typeKey = typeCatalog[normalizeReason(reason)] || fallbackTypeKey(reason)
        const shouldShow = !typeFilter || typeKey === typeFilter
        row.style.display = shouldShow ? '' : 'none'
        if (shouldShow) visible += 1
      }
      setRowCounts((current) => current.visible === visible && current.total === total
        ? current
        : { visible, total })
    }

    const scheduleFilter = () => {
      if (timer) window.clearTimeout(timer)
      timer = window.setTimeout(applyFilter, 20)
    }

    applyFilter()
    const observer = new MutationObserver(scheduleFilter)
    observer.observe(tbody, { childList: true, subtree: true, characterData: true })
    document.addEventListener('change', scheduleFilter, true)
    document.addEventListener('input', scheduleFilter, true)

    return () => {
      if (timer) window.clearTimeout(timer)
      observer.disconnect()
      document.removeEventListener('change', scheduleFilter, true)
      document.removeEventListener('input', scheduleFilter, true)
      for (const row of tbody.querySelectorAll('tr')) row.style.display = ''
    }
  }, [target, typeCatalog, typeFilter])

  useEffect(() => {
    if (!context.start || !context.end || (!isAdmin && !context.employee)) return undefined
    let cancelled = false
    const load = async () => {
      setBusy(true)
      setError('')
      try {
        const result = await veraApi.leaveDailyStats(context.start, context.end, context.employee)
        if (!cancelled) setSummary(sumDailyStats(result.days || []))
      } catch (err) {
        if (!cancelled) {
          setSummary(emptySummary)
          setError(err.message || 'Không tải được thống kê nghỉ.')
        }
      } finally {
        if (!cancelled) setBusy(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [context.start, context.end, context.employee, isAdmin])

  const subtitle = useMemo(() => {
    const range = context.displayStart && context.displayEnd
      ? `${context.displayStart} – ${context.displayEnd}`
      : ''
    if (isAdmin) {
      return context.employee
        ? `Nhân viên: ${context.employee}${range ? ` · ${range}` : ''}`
        : `Tất cả nhân viên${range ? ` · ${range}` : ''}`
    }
    return `Của bạn${range ? ` · ${range}` : ''}`
  }, [context.displayEnd, context.displayStart, context.employee, isAdmin])

  const selectedTypeLabel = TYPE_OPTIONS.find((item) => item.value === typeFilter)?.label || 'Tất cả'

  if (!target) return null

  const stats = [
    { key: 'total', label: 'TỔNG NGHỈ', icon: '', value: summary.totalLeave },
    { key: 'paid', label: 'CÓ PHÉP', icon: '✅', value: summary.paid },
    { key: 'generated', label: 'PHÁT SINH', icon: '⚠️', value: summary.generated },
    { key: 'unpaid', label: 'KHÔNG PHÉP', icon: '❌', value: summary.unpaid },
  ]
  if (isAdmin) stats.push({ key: 'penalty', label: 'TỔNG TIỀN PHẠT', icon: '💰', value: `${summary.totalPenalty.toLocaleString('vi-VN')}đ` })

  return createPortal(<>
    <style>{`
      .leave-list-personal-summary{margin:12px 0 14px;border:1px solid #e4e8e6;border-radius:14px;background:#fff;overflow:hidden}
      .leave-list-personal-summary-head{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:10px 14px;border-bottom:1px solid #edf0ef;background:#f8faf9}
      .leave-list-personal-summary-head strong{font-size:14px}.leave-list-personal-summary-head span{font-size:12px;color:#68736f;text-align:right}
      .leave-list-personal-summary-grid{display:grid;grid-template-columns:minmax(150px,1.25fr) repeat(4,minmax(0,1fr))}
      .leave-list-personal-summary.admin .leave-list-personal-summary-grid{grid-template-columns:minmax(150px,1.25fr) repeat(5,minmax(0,1fr))}
      .leave-list-personal-stat{padding:12px 10px;text-align:center;border-right:1px solid #edf0ef}.leave-list-personal-stat:last-child{border-right:0}
      .leave-list-personal-stat-label{display:flex;gap:6px;align-items:center;justify-content:center;font-size:12px;font-weight:800;color:#68736f;white-space:nowrap}
      .leave-list-personal-stat-value{margin-top:8px;font-size:16px;font-weight:800;color:#0f201a}.leave-list-personal-stat.paid .leave-list-personal-stat-value{color:#c7192d}
      .leave-list-type-filter{padding:8px 10px;border-right:1px solid #edf0ef;background:#fbfcfb;display:flex;flex-direction:column;justify-content:center;gap:5px;min-width:0}
      .leave-list-type-filter label{font-size:11px;font-weight:900;color:#68736f;white-space:nowrap}
      .leave-list-type-filter select{width:100%;min-width:0;height:34px;padding:5px 30px 5px 8px;border:1px solid #d9e1dd;border-radius:9px;background:#fff;color:#16382c;font-weight:800}
      .leave-list-type-filter small{font-size:9px;line-height:1.2;color:#74817b;white-space:normal}
      .leave-list-type-filter .filter-empty{color:#9a5a12;font-weight:800}
      .leave-list-personal-summary-note{padding:8px 14px;font-size:12px;color:#68736f;border-top:1px solid #edf0ef}
      .leave-list-personal-summary-error{padding:8px 14px;color:#b42318;background:#fff6f5;border-top:1px solid #ffd9d5;font-size:12px}
      @media(max-width:760px){
        .leave-list-personal-summary{margin:8px 0 10px;border-radius:10px}
        .leave-list-personal-summary-head{padding:7px 9px;gap:3px;align-items:flex-start;flex-direction:column}
        .leave-list-personal-summary-head strong{font-size:12px;line-height:1.15}
        .leave-list-personal-summary-head span{font-size:10px;line-height:1.15;text-align:left}
        .leave-list-personal-summary-grid{grid-template-columns:repeat(4,minmax(0,1fr))}
        .leave-list-personal-summary.admin .leave-list-personal-summary-grid{grid-template-columns:repeat(5,minmax(0,1fr))}
        .leave-list-type-filter{grid-column:1/-1;display:grid;grid-template-columns:auto minmax(120px,1fr) auto;align-items:center;gap:6px;padding:6px 7px;border-right:0;border-bottom:1px solid #edf0ef}
        .leave-list-type-filter label{font-size:9px}.leave-list-type-filter select{height:30px;font-size:10px;padding-top:3px;padding-bottom:3px}.leave-list-type-filter small{font-size:8px;text-align:right}
        .leave-list-personal-stat{min-width:0;padding:6px 2px;border-bottom:0}
        .leave-list-personal-stat-label{gap:2px;font-size:9px;line-height:1.05;white-space:normal;min-height:20px}
        .leave-list-personal-stat-label>span{font-size:11px;line-height:1}
        .leave-list-personal-stat-value{margin-top:3px;font-size:14px;line-height:1.05}
        .leave-list-personal-summary-note{padding:5px 8px;font-size:9px;line-height:1.2}
        .leave-list-personal-summary-error{padding:5px 8px;font-size:10px}
      }
      @media(max-width:390px){
        .leave-list-personal-summary-head strong{font-size:11px}
        .leave-list-personal-summary-head span{font-size:9px}
        .leave-list-type-filter{grid-template-columns:auto minmax(100px,1fr)}.leave-list-type-filter small{grid-column:1/-1;text-align:left}
        .leave-list-personal-stat{padding:5px 1px}
        .leave-list-personal-stat-label{font-size:8px;gap:1px;min-height:18px}
        .leave-list-personal-stat-label>span{font-size:10px}
        .leave-list-personal-stat-value{font-size:13px;margin-top:2px}
      }
      ${!isAdmin ? `
        .leave-list-panel .penalty-chip,
        .daily-summary-panel .penalty-chip,
        .leave-list-panel .leave-records-table.with-penalty th:last-child,
        .leave-list-panel .leave-records-table.with-penalty td:last-child,
        .daily-summary-panel .daily-summary-table.with-penalty th:last-child,
        .daily-summary-panel .daily-summary-table.with-penalty td:last-child{display:none!important}
      ` : ''}
    `}</style>
    <section className={`leave-list-personal-summary ${isAdmin ? 'admin' : ''}`} aria-live="polite">
      <div className="leave-list-personal-summary-head">
        <strong>THỐNG KÊ TRONG DANH SÁCH</strong>
        <span>{subtitle}</span>
      </div>
      <div className="leave-list-personal-summary-grid">
        <div className="leave-list-type-filter">
          <label htmlFor="leave-list-type-filter">LOẠI NGHỈ</label>
          <select
            id="leave-list-type-filter"
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
            disabled={catalogBusy || Boolean(catalogError)}
            aria-label="Lọc danh sách theo Loại nghỉ"
          >
            {TYPE_OPTIONS.map((item) => <option key={item.value || 'all'} value={item.value}>{item.label}</option>)}
          </select>
          <small className={typeFilter && rowCounts.visible === 0 ? 'filter-empty' : ''}>
            {catalogBusy
              ? 'Đang tải Nội quy…'
              : catalogError
                ? 'Chưa tải được Nội quy'
                : typeFilter
                  ? `${selectedTypeLabel}: ${rowCounts.visible}/${rowCounts.total} lịch`
                  : `${rowCounts.total} lịch`}
          </small>
        </div>
        {stats.map((item) => <div className={`leave-list-personal-stat ${item.key}`} key={item.key}>
          <div className="leave-list-personal-stat-label">{item.icon && <span aria-hidden="true">{item.icon}</span>}{item.label}</div>
          <div className="leave-list-personal-stat-value">{busy ? '…' : item.value}</div>
        </div>)}
      </div>
      {!isAdmin && <div className="leave-list-personal-summary-note">Thống kê này chỉ tính lịch nghỉ của chính tài khoản đang đăng nhập. Tiền vi phạm không hiển thị cho nhân viên.</div>}
      {catalogError && <div className="leave-list-personal-summary-error">Bộ lọc Loại nghỉ chưa sẵn sàng: {catalogError}</div>}
      {error && <div className="leave-list-personal-summary-error">{error}</div>}
    </section>
  </>, target)
}
