import { Compass, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { veraApi } from '../lib/api'

const EMPTY_TOUR = { columns: [], records: [], stats: [] }
const TOUR_CACHE_MAX_AGE = 10 * 60 * 1000

function cacheKey(user) {
  const identity = user?.employee_username || user?.email || 'viewer'
  return `vera-tour-cache:${identity}`
}

function readCachedTour(key) {
  try {
    const cached = JSON.parse(window.sessionStorage.getItem(key) || 'null')
    if (!cached?.savedAt || Date.now() - cached.savedAt > TOUR_CACHE_MAX_AGE) return EMPTY_TOUR
    if (!Array.isArray(cached.data?.columns) || !Array.isArray(cached.data?.records)) return EMPTY_TOUR
    return cached.data
  } catch {
    return EMPTY_TOUR
  }
}

function saveCachedTour(key, data) {
  try {
    window.sessionStorage.setItem(key, JSON.stringify({ savedAt: Date.now(), data }))
  } catch {
    // A full sessionStorage quota must never block the live Bảng tua response.
  }
}

function normalizedColumn(column) {
  return String(column || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').trim().toUpperCase()
}

function columnClass(column) {
  const key = normalizedColumn(column)
  if (key === 'TG CON LAI' || key === 'THOI GIAN CON LAI') return 'tour-col-remaining center'
  if (key.includes('LICH HEN')) return 'tour-col-appointment'
  return ''
}

function prioritizeRecords(records, columns, activeFilter) {
  if (activeFilter === 'all') return records
  const remainingColumn = columns.find((column) => {
    const key = normalizedColumn(column)
    return key === 'TG CON LAI' || key === 'THOI GIAN CON LAI'
  })
  const remainingValue = (record) => {
    const raw = remainingColumn ? record[remainingColumn] : ''
    if (raw === '' || raw === null || raw === undefined) return Number.POSITIVE_INFINITY
    const value = Number(String(raw).replace(',', '.'))
    return Number.isFinite(value) ? value : Number.POSITIVE_INFINITY
  }
  return records.map((record, index) => ({ record, index })).sort((left, right) => {
    const leftMatches = Array.isArray(left.record._tour_groups) && left.record._tour_groups.includes(activeFilter)
    const rightMatches = Array.isArray(right.record._tour_groups) && right.record._tour_groups.includes(activeFilter)
    if (leftMatches !== rightMatches) return leftMatches ? -1 : 1
    if (leftMatches && rightMatches) {
      const leftTime = remainingValue(left.record)
      const rightTime = remainingValue(right.record)
      if (leftTime !== rightTime) return leftTime < rightTime ? -1 : 1
    }
    return left.index - right.index
  }).map(({ record }) => record)
}

export default function TourPage({ user }) {
  const tourCacheKey = cacheKey(user)
  const [data, setData] = useState(() => readCachedTour(tourCacheKey))
  const initiallyCached = useRef(Boolean(data.records.length))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [activeFilter, setActiveFilter] = useState('all')
  const load = useCallback(async (refresh = false, quiet = false) => {
    if (!quiet) setBusy(true)
    setError('')
    try {
      const nextData = await veraApi.tour(refresh)
      setData(nextData)
      saveCachedTour(tourCacheKey, nextData)
    } catch (err) {
      setError(err.message)
    } finally {
      if (!quiet) setBusy(false)
    }
  }, [tourCacheKey])

  useEffect(() => {
    void load(false, initiallyCached.current)
    const interval = window.setInterval(() => { void load(false, true) }, 30000)
    return () => window.clearInterval(interval)
  }, [load])

  const metrics = [
    { key: 'available', label: 'Có thể lên tua', value: data.available || 0, className: 'tour-available-metric' },
    { key: 'all', label: 'Số nhân viên', value: data.employee_count ?? data.count ?? 0, className: '' },
    { key: 'finishing', label: 'Sắp xong', value: data.finishing_count || 0, className: '' },
    { key: 'working', label: 'Đi làm', value: data.working_count || 0, className: '' },
    { key: 'waiting', label: 'Đang chờ', value: data.waiting_count || 0, className: '' },
    { key: 'leave', label: 'Nghỉ phép', value: data.leave_count || 0, className: '' },
    { key: 'doing', label: 'Đang thực hiện', value: data.doing_count || 0, className: '' },
    { key: 'break', label: 'Nghỉ giữa Ca', value: data.break_count || 0, className: 'tour-break-metric' },
  ]
  const displayedRecords = useMemo(
    () => prioritizeRecords(data.records || [], data.columns || [], activeFilter),
    [activeFilter, data.columns, data.records],
  )
  const chooseFilter = (key) => setActiveFilter((current) => key === 'all' || current === key ? 'all' : key)

  return <div className="feature-page">
    <div className="page-heading"><div><span className="eyebrow"><Compass size={14} /> Vận hành</span><h1>BẢNG TUA</h1><p>Countdown cập nhật mỗi 30 giây; file TourVera được đọc lại tối đa mỗi 1 phút.</p></div>{user?.permissions?.tour_refresh && <button className="secondary-button" onClick={() => load(true)} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới Bảng tua</button>}</div>
    {error && <div className="error-box">{error}</div>}
    {data.countdown_error && <div className="warning-box">Countdown Bảng tua: {data.countdown_error}</div>}
    <div className="metric-grid small tour-metrics">{metrics.map(({ key, label, value, className }) => <button type="button" className={`metric-card tour-metric-card ${className} ${activeFilter === key ? 'active' : ''}`.trim()} onClick={() => chooseFilter(key)} aria-pressed={activeFilter === key} title={key === 'all' ? 'Khôi phục thứ tự danh sách' : `Ưu tiên ${label} lên đầu danh sách`} key={key}><span>{label}</span><strong>{value}</strong></button>)}</div>
    <section className="panel tour-table-panel"><div className="responsive-data-table tour-table" tabIndex="0" aria-label="Danh sách Bảng tua"><table><thead><tr>{data.columns.map((column) => <th className={columnClass(column)} key={column}>{column}</th>)}</tr></thead><tbody>{displayedRecords.map((item, index) => <tr className={`tour-row-${item._row_style || 'default'}`} key={index}>{data.columns.map((column) => <td className={columnClass(column)} key={column}>{String(item[column] ?? '')}</td>)}</tr>)}</tbody></table></div>{!busy && !data.records.length && <div className="setup-note">Bảng tua hiện chưa có dữ liệu.</div>}</section>
    <section className="panel tour-legend"><div className="panel-title-row"><div><h2>MÀU DÒNG</h2><p>Màu áp dụng cho toàn bộ dòng và Break luôn được ưu tiên cao nhất.</p></div></div><div className="tour-legend-grid"><span className="green">≥15 phút · Xanh</span><span className="yellow">0–&lt;15 · Vàng</span><span className="red">-15–&lt;0 · Đỏ</span><span className="blank">≤-15 · Làm trống</span><span className="break">Break · Cam</span><span className="idle">Đi làm + Vào ca + đang rảnh</span><span className="leave">Nghỉ phép · Chữ mờ</span></div></section>
    <div className="setup-note tour-countdown-note">Thời gian còn lại do hệ thống tự đếm: Yêu cầu trống dùng “TG bắt đầu thực hiện”; Yêu cầu YC dùng “TG bắt đầu thực hiện YC”; cả hai cộng theo Thời lượng.</div>
  </div>
}
