import { Compass, DoorOpen, RefreshCw, Search } from 'lucide-react'
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

function findColumn(columns, acceptedNames) {
  const wanted = new Set(acceptedNames)
  return columns.find((column) => wanted.has(normalizedColumn(column))) || ''
}

function cellValue(record, column) {
  return column ? String(record?.[column] ?? '').trim() : ''
}

function sttColumn(columns) {
  return findColumn(columns, ['STT', 'SO THU TU'])
}

function employeeNameColumn(columns) {
  return findColumn(columns, ['TEN NHAN VIEN', 'NHAN VIEN', 'HO VA TEN', 'HO TEN'])
}

function validTourRecord(record, columns) {
  const stt = cellValue(record, sttColumn(columns))
  const employeeName = cellValue(record, employeeNameColumn(columns))
  return Boolean(stt && employeeName)
}

function sttValue(record, columns) {
  return cellValue(record, sttColumn(columns))
}

function columnClass(column) {
  const key = normalizedColumn(column)
  if (key === 'STT' || key === 'SO THU TU') return 'tour-col-stt center'
  if (['TEN NHAN VIEN', 'NHAN VIEN', 'HO VA TEN', 'HO TEN'].includes(key)) return 'tour-col-employee'
  if (key === 'TRANG THAI') return 'tour-col-status center'
  if (key === 'TG CON LAI' || key === 'THOI GIAN CON LAI') return 'tour-col-remaining center'
  if (key === 'PHONG' || key.startsWith('PHONG (')) return 'tour-col-room center'
  if (key === 'YEU CAU' || key.startsWith('YEU CAU (')) return 'tour-col-request center'
  if (key.includes('LICH HEN')) return 'tour-col-appointment'
  return 'tour-col-mobile-hidden'
}

function rowClass(record) {
  const base = `tour-row-${record?._row_style || 'default'}`
  const waiting = Array.isArray(record?._tour_groups) && record._tour_groups.includes('waiting')
  return `${base}${waiting ? ' tour-row-waiting' : ''}`
}

function prioritizeRecords(records, columns, activeFilter) {
  if (activeFilter === 'all') return records
  const priorityGroup = activeFilter === 'finishing' ? 'available' : activeFilter
  const remainingColumn = columns.find((column) => {
    const key = normalizedColumn(column)
    return key === 'TG CON LAI' || key === 'THOI GIAN CON LAI'
  })
  const remainingOrder = (record) => {
    const raw = remainingColumn ? record[remainingColumn] : ''
    if (raw === '' || raw === null || raw === undefined) return [0, 0]
    const value = Number(String(raw).replace(',', '.'))
    return Number.isFinite(value) ? [1, value] : [2, 0]
  }
  return records.map((record, index) => ({ record, index })).sort((left, right) => {
    const leftMatches = Array.isArray(left.record._tour_groups) && left.record._tour_groups.includes(priorityGroup)
    const rightMatches = Array.isArray(right.record._tour_groups) && right.record._tour_groups.includes(priorityGroup)
    if (leftMatches !== rightMatches) return leftMatches ? -1 : 1
    if (leftMatches && rightMatches) {
      const [leftRank, leftTime] = remainingOrder(left.record)
      const [rightRank, rightTime] = remainingOrder(right.record)
      if (leftRank !== rightRank) return leftRank - rightRank
      if (leftTime !== rightTime) return leftTime - rightTime
    }
    return left.index - right.index
  }).map(({ record }) => record)
}

function shiftValue(record, columns) {
  const shiftColumn = findColumn(columns, ['VAO CA', 'GIO VAO CA', 'THOI GIAN VAO CA'])
  return cellValue(record, shiftColumn)
}

function shiftBucket(record, columns) {
  const raw = shiftValue(record, columns)
  if (!raw) return ''

  const normalized = normalizedColumn(raw).replace(/\s+/g, ' ')
  if (/(^|\s)CA\s*1(\s|$)/.test(normalized) || normalized === 'CA1') return 'ca1'
  if (/(^|\s)CA\s*2(\s|$)/.test(normalized) || normalized === 'CA2') return 'ca2'

  const timeMatch = raw.match(/(?:^|\s)(\d{1,2})\s*[:Hh]\s*(\d{2})?/)
  if (timeMatch) {
    const hour = Number(timeMatch[1])
    if (Number.isFinite(hour)) return hour < 12 ? 'ca1' : 'ca2'
  }

  const compact = normalized.replace(/\s+/g, '')
  if (['10', '10H', '10H00'].includes(compact)) return 'ca1'
  if (['12', '12H', '12H00', '14', '14H', '14H00'].includes(compact)) return 'ca2'
  return ''
}

function matchesShift(record, columns, shiftFilter) {
  if (shiftFilter === 'all') return true
  return shiftBucket(record, columns) === shiftFilter
}

function hasGroup(record, key) {
  return Array.isArray(record?._tour_groups) && record._tour_groups.includes(key)
}

function groupCount(records, key) {
  return records.reduce((count, record) => count + (hasGroup(record, key) ? 1 : 0), 0)
}

function numberValue(value) {
  const parsed = Number(String(value ?? '').replace(/[^0-9-]/g, ''))
  return Number.isFinite(parsed) ? parsed : 0
}

function employeeCountFromStt(records, columns) {
  const values = records.map((record) => sttValue(record, columns)).filter(Boolean)
  return new Set(values).size
}

export default function TourPage({ user }) {
  const tourCacheKey = cacheKey(user)
  const [data, setData] = useState(() => readCachedTour(tourCacheKey))
  const initiallyCached = useRef(Boolean(data.records.length))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [activeFilter, setActiveFilter] = useState('all')
  const [shiftFilter, setShiftFilter] = useState('all')
  const [employeeSearch, setEmployeeSearch] = useState('')
  const [showAvailableRooms, setShowAvailableRooms] = useState(false)
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
    void load(true, initiallyCached.current)
    const interval = window.setInterval(() => { void load(true, true) }, 10000)
    return () => window.clearInterval(interval)
  }, [load])

  const columns = data.columns || []
  const validRecords = useMemo(
    () => (data.records || []).filter((record) => validTourRecord(record, columns)),
    [columns, data.records],
  )
  const shiftRecords = useMemo(
    () => validRecords.filter((record) => matchesShift(record, columns, shiftFilter)),
    [columns, shiftFilter, validRecords],
  )
  const searchedRecords = useMemo(() => {
    const needle = normalizedColumn(employeeSearch)
    if (!needle) return shiftRecords
    const nameColumn = employeeNameColumn(columns)
    return shiftRecords.filter((record) => normalizedColumn(cellValue(record, nameColumn)).includes(needle))
  }, [columns, employeeSearch, shiftRecords])
  const displayedRecords = useMemo(
    () => prioritizeRecords(searchedRecords, columns, activeFilter),
    [activeFilter, columns, searchedRecords],
  )
  const availableRooms = Array.isArray(data.available_rooms) ? data.available_rooms : []
  const retainedMetric = data.metric_snapshots?.[shiftFilter] || null
  const breakTotal = retainedMetric?.break_total_count ?? retainedMetric?.break_count ?? groupCount(shiftRecords, 'break')
  const breakActive = retainedMetric?.break_active_count ?? groupCount(shiftRecords, 'break')
  const customerCount = useMemo(() => {
    if (retainedMetric && Number.isFinite(Number(retainedMetric.customer_count))) return Number(retainedMetric.customer_count)
    const totalColumn = findColumn(columns, ['TONG SL', 'TONG SO LUONG'])
    return shiftRecords.reduce((sum, record) => sum + numberValue(record[totalColumn]), 0)
      + groupCount(shiftRecords, 'waiting')
  }, [columns, retainedMetric, shiftRecords])
  const metrics = useMemo(() => [
    { key: 'available', label: 'Có thể lên tua', value: groupCount(shiftRecords, 'available'), className: 'tour-available-metric' },
    { key: 'all', label: 'Số nhân viên', value: employeeCountFromStt(shiftRecords, columns), className: '' },
    { key: 'finishing', label: 'Sắp xong', value: groupCount(shiftRecords, 'finishing'), className: '' },
    { key: 'working', label: 'Đi làm', value: groupCount(shiftRecords, 'working'), className: '' },
    { key: 'waiting', label: 'Đang chờ', value: groupCount(shiftRecords, 'waiting'), className: '' },
    { key: 'leave', label: 'Nghỉ phép', value: groupCount(shiftRecords, 'leave'), className: '' },
    { key: 'doing', label: 'Đang thực hiện', value: groupCount(shiftRecords, 'doing'), className: '' },
    { key: 'break', label: 'Nghỉ giữa Ca', value: `${breakTotal}-${breakActive}`, className: 'tour-break-metric' },
  ], [breakActive, breakTotal, columns, retainedMetric, shiftRecords])
  const chooseFilter = (key) => setActiveFilter((current) => key === 'all' || current === key ? 'all' : key)

  return <div className="feature-page">
    <style>{`
      .tour-table tr.tour-row-waiting:not(.tour-row-break) td{color:#3f245d;background:#d9c2f0;font-weight:900}
      .tour-legend-grid .waiting{color:#3f245d;background:#efe4fb;border-color:#c9aee7;font-weight:900}
      .tour-shift-filter{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 12px}
      .tour-shift-filter button{min-width:82px}
      .tour-heading-actions{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end}
      .tour-quick-tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 12px}.tour-employee-search{position:relative;flex:1 1 260px;max-width:430px}.tour-employee-search svg{position:absolute;left:11px;top:50%;transform:translateY(-50%);pointer-events:none;color:#60756b}.tour-employee-search input{width:100%;padding-left:36px;box-sizing:border-box}.tour-room-button{display:inline-flex;align-items:center;gap:7px}.tour-room-panel{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:-4px 0 14px;padding:11px 12px;border:1px solid #cfe1d8;border-radius:12px;background:#f3faf6}.tour-room-panel span{padding:6px 10px;border-radius:999px;background:#d9f1e4;color:#17573d;font-weight:900}.tour-room-panel small{color:#5d7168}
      @media(max-width:640px){
        .tour-shift-filter{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px;margin-bottom:7px}
        .tour-shift-filter button{min-width:0;padding:7px 4px;font-size:11px}
        .tour-heading-actions{width:100%;justify-content:stretch}.tour-heading-actions button{flex:1}
        .tour-metrics{grid-template-columns:repeat(4,minmax(0,1fr));gap:5px}
        .metric-grid.small .metric-card.tour-metric-card{min-height:48px;display:flex;flex-direction:column;justify-content:center;gap:2px;padding:4px 3px;text-align:center}
        .metric-grid.small .metric-card.tour-metric-card span{font-size:8px;line-height:1.05}
        .metric-grid.small .metric-card.tour-metric-card strong{font-size:20px}
        .tour-table-panel{padding:8px}
        .tour-quick-tools{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:5px;margin-bottom:7px}
        .tour-employee-search{min-width:0;max-width:none}
        .tour-employee-search input{min-width:0;height:38px;padding:7px 7px 7px 30px;font-size:10px}
        .tour-employee-search svg{left:8px;width:14px}
        .tour-room-button{min-width:0;justify-content:center;gap:4px;padding:7px 5px;font-size:9px;white-space:nowrap}
        .tour-room-button svg{width:14px}
      }
    `}</style>
    <div className="page-heading"><div><span className="eyebrow"><Compass size={14} /> Vận hành</span><h1>BẢNG TUA</h1><p>Cache máy chủ Bảng tua làm mới tối đa mỗi 1 phút; màn hình tự kiểm tra dữ liệu mới mỗi 10 giây.</p></div><div className="tour-heading-actions">{user?.permissions?.tour_refresh && <button className="secondary-button" onClick={() => load(true)} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới Bảng tua</button>}</div></div>
    {error && <div className="error-box">{error}</div>}
    {data.countdown_error && <div className="warning-box">Countdown Bảng tua: {data.countdown_error}</div>}
    <div className="tour-shift-filter" aria-label="Lọc Bảng tua theo ca" data-tour-customer-count={customerCount}>
      <button type="button" className={shiftFilter === 'all' ? 'primary-button' : 'secondary-button'} onClick={() => setShiftFilter('all')}>Tất cả</button>
      <button type="button" className={shiftFilter === 'ca1' ? 'primary-button' : 'secondary-button'} onClick={() => setShiftFilter('ca1')}>Ca 1</button>
      <button type="button" className={shiftFilter === 'ca2' ? 'primary-button' : 'secondary-button'} onClick={() => setShiftFilter('ca2')}>Ca 2</button>
      <small>Đang hiển thị {displayedRecords.length}/{validRecords.length} nhân viên</small>
    </div>
    {data.metrics_retained_until_10 && <div className="setup-note">Số khách và tổng lượt Nghỉ giữa ca đang giữ số ngày {String(data.metrics_business_date || '').split('-').reverse().join('/')} đến 10:00 sáng. Nghỉ giữa ca hiển thị Tổng lượt-Đang ở ngoài.</div>}
    <div className="metric-grid small tour-metrics">{metrics.map(({ key, label, value, className }) => <button type="button" className={`metric-card tour-metric-card ${className} ${activeFilter === key ? 'active' : ''}`.trim()} onClick={() => chooseFilter(key)} aria-pressed={activeFilter === key} title={key === 'all' ? 'Khôi phục thứ tự danh sách' : key === 'finishing' ? 'Ưu tiên Đang rảnh và Sắp xong lên đầu danh sách' : `Ưu tiên ${label} lên đầu danh sách`} key={key}><span>{label}</span><strong>{value}</strong></button>)}</div>
    <section className="panel tour-table-panel">
      <div className="tour-quick-tools">
        <label className="tour-employee-search" aria-label="Tìm nhanh tên nhân viên"><Search size={16}/><input type="search" value={employeeSearch} placeholder="Tìm nhanh tên nhân viên…" onChange={(event) => setEmployeeSearch(event.target.value)} /></label>
        <button type="button" className={showAvailableRooms ? 'primary-button tour-room-button' : 'secondary-button tour-room-button'} onClick={() => setShowAvailableRooms((value) => !value)} aria-expanded={showAvailableRooms}><DoorOpen size={16}/> Phòng đang trống ({availableRooms.length})</button>
      </div>
      {showAvailableRooms && <div className="tour-room-panel">{availableRooms.length ? availableRooms.map((room) => <span key={room}>Phòng {room}</span>) : <small>Hiện không có phòng trống theo sheet Room và cột PHÒNG trên Bảng tua.</small>}</div>}
      <div className="responsive-data-table tour-table" tabIndex="0" aria-label="Danh sách Bảng tua"><table><thead><tr>{columns.map((column) => <th className={columnClass(column)} key={column}>{column}</th>)}</tr></thead><tbody>{displayedRecords.map((item, index) => <tr className={rowClass(item)} key={`${sttValue(item, columns)}:${index}`}>{columns.map((column) => <td className={columnClass(column)} key={column}>{String(item[column] ?? '')}</td>)}</tr>)}</tbody></table></div>
      {!busy && !displayedRecords.length && <div className="setup-note">Không có nhân viên phù hợp với ca/bộ lọc đang chọn.</div>}
    </section>
    <section className="panel tour-legend"><div className="panel-title-row"><div><h2>MÀU DÒNG</h2><p>Màu áp dụng cho toàn bộ dòng và Break luôn được ưu tiên cao nhất.</p></div></div><div className="tour-legend-grid"><span className="green">≥15 phút · Xanh</span><span className="yellow">0–&lt;15 · Vàng</span><span className="red">-15–&lt;0 · Đỏ</span><span className="blank">≤-15 · Làm trống</span><span className="break">Break · Cam</span><span className="waiting">Đang chờ · Tím</span><span className="idle">Đi làm + Vào ca + đang rảnh</span><span className="leave">Nghỉ phép · Chữ mờ</span></div></section>
    <div className="setup-note tour-countdown-note">Thời gian còn lại do hệ thống tự đếm: Yêu cầu trống dùng “TG bắt đầu thực hiện”; Yêu cầu YC dùng “TG bắt đầu thực hiện YC”; cả hai cộng theo Thời lượng.</div>
  </div>
}
