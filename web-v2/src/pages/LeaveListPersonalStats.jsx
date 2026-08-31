import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { veraApi } from '../lib/api'
import { emptyLeaveDaySummary, formatLeaveDays } from '../lib/leaveStats'

const parseDisplayDate = (value) => { const match = String(value || '').trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/); return match ? `${match[3]}-${match[2]}-${match[1]}` : '' }
const sameContext = (a, b) => a.start === b.start && a.end === b.end && a.employee === b.employee && a.displayStart === b.displayStart && a.displayEnd === b.displayEnd

export default function LeaveListPersonalStats({ user }) {
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const [target, setTarget] = useState(null)
  const [context, setContext] = useState({ start: '', end: '', employee: '', displayStart: '', displayEnd: '' })
  const [summary, setSummary] = useState(emptyLeaveDaySummary)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const contextRef = useRef(context)
  const requestRevisionRef = useRef(0)

  useEffect(() => {
    let cancelled = false; let ownedHost = null; let timer = null
    const syncFromList = () => {
      if (cancelled) return
      const panel = document.querySelector('.leave-list-panel'); const tableWrap = panel?.querySelector('.leave-list-wrap')
      if (!panel || !tableWrap) return
      let host = panel.querySelector('[data-leave-list-personal-stats="true"]')
      if (!host) { host = document.createElement('div'); host.dataset.leaveListPersonalStats = 'true'; panel.insertBefore(host, tableWrap); ownedHost = host }
      setTarget((current) => current === host ? current : host)
      const description = String(panel.querySelector('.panel-title-row p')?.textContent || '')
      const rangeMatch = description.match(/Bộ lọc\s+(\d{2}\/\d{2}\/\d{4})\s*[–-]\s*(\d{2}\/\d{2}\/\d{4})/)
      if (!rangeMatch) return
      const searchValue = String(panel.querySelector('.employee-search-field input[type="search"]')?.value || '').trim()
      const next = { start: parseDisplayDate(rangeMatch[1]), end: parseDisplayDate(rangeMatch[2]), employee: searchValue, displayStart: rangeMatch[1], displayEnd: rangeMatch[2] }
      if (!next.start || !next.end) return
      if (sameContext(contextRef.current, next)) return
      contextRef.current = next
      requestRevisionRef.current += 1
      setSummary(emptyLeaveDaySummary())
      setError('')
      setBusy(true)
      setContext(next)
    }
    const scheduleSync = (event) => {
      if (event?.type === 'input' && event.target?.matches?.('.leave-list-panel .employee-search-field input[type="search"]')) {
        syncFromList()
        return
      }
      if (timer) window.clearTimeout(timer)
      timer = window.setTimeout(syncFromList, 30)
    }
    syncFromList()
    const observer = new MutationObserver(scheduleSync); observer.observe(document.body, { childList: true, subtree: true, characterData: true })
    document.addEventListener('input', scheduleSync, true); document.addEventListener('change', scheduleSync, true); document.addEventListener('click', scheduleSync, true)
    return () => { cancelled = true; if (timer) window.clearTimeout(timer); observer.disconnect(); document.removeEventListener('input', scheduleSync, true); document.removeEventListener('change', scheduleSync, true); document.removeEventListener('click', scheduleSync, true); if (ownedHost?.isConnected) ownedHost.remove() }
  }, [])

  useEffect(() => {
    if (!context.start || !context.end) return undefined
    let cancelled = false
    const revision = ++requestRevisionRef.current
    const load = async () => {
      setBusy(true); setError(''); setSummary(emptyLeaveDaySummary())
      try {
        const result = await veraApi.leaveListStats(context.start, context.end, context.employee)
        if (!cancelled && revision === requestRevisionRef.current) setSummary({ ...emptyLeaveDaySummary(), ...(result.summary || {}) })
      } catch (err) {
        if (!cancelled && revision === requestRevisionRef.current) { setSummary(emptyLeaveDaySummary()); setError(err.message || 'Không tải được thống kê nghỉ.') }
      } finally {
        if (!cancelled && revision === requestRevisionRef.current) setBusy(false)
      }
    }
    void load(); return () => { cancelled = true }
  }, [context.start, context.end, context.employee])

  const subtitle = useMemo(() => {
    const range = context.displayStart && context.displayEnd ? `${context.displayStart} – ${context.displayEnd}` : ''
    return context.employee ? `Nhân viên: ${context.employee}${range ? ` · ${range}` : ''}` : `Tất cả nhân viên${range ? ` · ${range}` : ''}`
  }, [context.displayEnd, context.displayStart, context.employee])

  if (!target) return null
  const stats = [
    { key: 'total', label: 'TỔNG NGÀY NGHỈ', icon: '', value: formatLeaveDays(summary.total_leave) },
    { key: 'paid', label: 'CÓ PHÉP', icon: '✅', value: formatLeaveDays(summary.paid) },
    { key: 'generated', label: 'PHÁT SINH', icon: '⚠️', value: formatLeaveDays(summary.generated) },
    { key: 'unpaid', label: 'KHÔNG PHÉP', icon: '❌', value: formatLeaveDays(summary.unpaid) },
  ]
  if (isAdmin) stats.push({ key: 'penalty', label: 'TỔNG TIỀN PHẠT', icon: '💰', value: `${Number(summary.total_penalty || 0).toLocaleString('vi-VN')}đ` })

  return createPortal(<>
    <style>{`
      .leave-list-personal-summary{margin:12px 0 14px;border:1px solid #e4e8e6;border-radius:14px;background:#fff;overflow:hidden}
      .leave-list-personal-summary-head{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:10px 14px;border-bottom:1px solid #edf0ef;background:#f8faf9}
      .leave-list-personal-summary-head strong{font-size:14px}.leave-list-personal-summary-head span{font-size:12px;color:#68736f;text-align:right}
      .leave-list-personal-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))}.leave-list-personal-summary.admin .leave-list-personal-summary-grid{grid-template-columns:repeat(5,minmax(0,1fr))}
      .leave-list-personal-stat{padding:12px 10px;text-align:center;border-right:1px solid #edf0ef}.leave-list-personal-stat:last-child{border-right:0}
      .leave-list-personal-stat-label{display:flex;gap:6px;align-items:center;justify-content:center;font-size:12px;font-weight:800;color:#68736f;white-space:nowrap}.leave-list-personal-stat-value{margin-top:8px;font-size:16px;font-weight:800;color:#0f201a}.leave-list-personal-stat.paid .leave-list-personal-stat-value{color:#c7192d}
      .leave-list-personal-summary-note{padding:8px 14px;font-size:12px;color:#68736f;border-top:1px solid #edf0ef}.leave-list-personal-summary-error{padding:8px 14px;color:#b42318;background:#fff6f5;border-top:1px solid #ffd9d5;font-size:12px}
      @media(max-width:760px){
        .leave-list-personal-summary{margin:8px 0 10px;border-radius:10px}.leave-list-personal-summary-head{padding:7px 9px;gap:3px;align-items:flex-start;flex-direction:column}.leave-list-personal-summary-head strong{font-size:12px;line-height:1.15}.leave-list-personal-summary-head span{font-size:10px;line-height:1.15;text-align:left}
        .leave-list-personal-stat{min-width:0;padding:6px 2px;border-bottom:0}.leave-list-personal-stat-label{gap:2px;font-size:9px;line-height:1.05;white-space:normal;min-height:20px}.leave-list-personal-stat-label>span{font-size:11px;line-height:1}.leave-list-personal-stat-value{margin-top:3px;font-size:14px;line-height:1.05}.leave-list-personal-summary-note{padding:5px 8px;font-size:9px;line-height:1.2}
        .leave-records-table.with-leave-type-column.without-penalty .leave-col-select{width:7%!important}.leave-records-table.with-leave-type-column.without-penalty .leave-col-date{width:11%!important}.leave-records-table.with-leave-type-column.without-penalty .leave-col-weekday{width:8%!important}.leave-records-table.with-leave-type-column.without-penalty .leave-col-employee{width:15%!important}.leave-records-table.with-leave-type-column.without-penalty .leave-col-reason{width:30%!important}.leave-records-table.with-leave-type-column.without-penalty .leave-col-type{width:17%!important}.leave-records-table.with-leave-type-column.without-penalty .leave-col-detail{width:12%!important}
        .leave-records-table.with-leave-type-column.with-penalty .leave-col-select{width:6%!important}.leave-records-table.with-leave-type-column.with-penalty .leave-col-date{width:10%!important}.leave-records-table.with-leave-type-column.with-penalty .leave-col-weekday{width:7%!important}.leave-records-table.with-leave-type-column.with-penalty .leave-col-employee{width:14%!important}.leave-records-table.with-leave-type-column.with-penalty .leave-col-reason{width:27%!important}.leave-records-table.with-leave-type-column.with-penalty .leave-col-type{width:15%!important}.leave-records-table.with-leave-type-column.with-penalty .leave-col-detail{width:10%!important}.leave-records-table.with-leave-type-column.with-penalty .leave-col-penalty{width:11%!important}
      }
      ${!isAdmin ? `.leave-list-panel .penalty-chip,.daily-summary-panel .penalty-chip,.leave-list-panel .leave-records-table.with-penalty th:last-child,.leave-list-panel .leave-records-table.with-penalty td:last-child,.daily-summary-panel .daily-summary-table.with-penalty th:last-child,.daily-summary-panel .daily-summary-table.with-penalty td:last-child{display:none!important}` : ''}
    `}</style>
    <section className={`leave-list-personal-summary ${isAdmin ? 'admin' : ''}`} aria-live="polite">
      <div className="leave-list-personal-summary-head"><strong>THỐNG KÊ TRONG DANH SÁCH</strong><span>{subtitle}</span></div>
      <div className="leave-list-personal-summary-grid">{stats.map((item) => <div className={`leave-list-personal-stat ${item.key}`} key={item.key}><div className="leave-list-personal-stat-label">{item.icon && <span aria-hidden="true">{item.icon}</span>}{item.label}</div><div className="leave-list-personal-stat-value">{busy ? '…' : item.value}</div></div>)}</div>
      <div className="leave-list-personal-summary-note">Tổng ngày nghỉ/Có phép cộng theo ngày thực tế (0,5 tính đúng 0,5); Phát sinh/Không phép đếm số bản ghi.{!isAdmin && ' Tiền vi phạm không hiển thị cho tài khoản này.'}</div>
      {error && <div className="leave-list-personal-summary-error">{error}</div>}
    </section>
  </>, target)
}
