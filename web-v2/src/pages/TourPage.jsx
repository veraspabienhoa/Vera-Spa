import { Clock3, Crown, DoorOpen, ExternalLink, LayoutGrid, Link2, RefreshCw, Save, Search } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { veraApi } from '../lib/api'

const EMPTY_TOUR = { columns: [], records: [], stats: [] }
const TOUR_CACHE_MAX_AGE = 10 * 60 * 1000
const VIP_ROOMS = ['16', '17', '18', '19', '20', '21']
const VIP_ROOM_KEYS = new Set(VIP_ROOMS)
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

function isCurrentlyOnBreak(record) {
  return record?._attendance_break_active === true
}

function matchesPriority(record, priorityGroup) {
  if (priorityGroup === 'break') return isCurrentlyOnBreak(record)
  return Array.isArray(record?._tour_groups) && record._tour_groups.includes(priorityGroup)
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
    const leftMatches = matchesPriority(left.record, priorityGroup)
    const rightMatches = matchesPriority(right.record, priorityGroup)
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
  if (key === 'break') return isCurrentlyOnBreak(record)
  return Array.isArray(record?._tour_groups) && record._tour_groups.includes(key)
}

function groupCount(records, key) {
  return records.reduce((count, record) => count + (hasGroup(record, key) ? 1 : 0), 0)
}

function employeeCountFromStt(records, columns) {
  const values = records.map((record) => sttValue(record, columns)).filter(Boolean)
  return new Set(values).size
}

function roomKey(value) {
  return normalizedColumn(value).replace(/^PHONG\s*/, '').replace(/\s+/g, ' ').trim()
}

function compareRooms(left, right) {
  return roomKey(left).localeCompare(roomKey(right), 'vi', { numeric: true, sensitivity: 'base' })
}

function isVipRoom(room) {
  return VIP_ROOM_KEYS.has(roomKey(room))
}

function roomLabel(room) {
  return isVipRoom(room) ? `VIP ${room}` : `Phòng ${room}`
}

function roomRecordPriority(record) {
  if (isCurrentlyOnBreak(record)) return 5
  if (hasGroup(record, 'doing')) return 4
  if (hasGroup(record, 'waiting')) return 3
  if (record?._countdown_deadline) return 2
  return 1
}

function pickRoomRecord(records, remainingColumn) {
  return [...records].sort((left, right) => {
    const priority = roomRecordPriority(right) - roomRecordPriority(left)
    if (priority) return priority
    const leftRaw = cellValue(left, remainingColumn)
    const rightRaw = cellValue(right, remainingColumn)
    const leftRemaining = leftRaw === '' ? null : Number(leftRaw)
    const rightRemaining = rightRaw === '' ? null : Number(rightRaw)
    if (Number.isFinite(leftRemaining) && Number.isFinite(rightRemaining)) return leftRemaining - rightRemaining
    return 0
  })[0] || null
}

function roomState(record, available, clockMs) {
  if (!record) return available ? 'blank' : 'default'
  if (isCurrentlyOnBreak(record)) return 'break'
  if (hasGroup(record, 'waiting')) return 'waiting'
  const deadlineMs = record._countdown_deadline ? new Date(record._countdown_deadline).getTime() : NaN
  if (Number.isFinite(deadlineMs) && Math.ceil((deadlineMs - clockMs) / 1000) <= -15 * 60) return 'red'
  return ['green', 'yellow', 'red', 'break', 'idle', 'leave', 'work'].includes(record._row_style)
    ? record._row_style
    : 'default'
}

function durationText(seconds) {
  const total = Math.max(0, Math.floor(Math.abs(Number(seconds || 0))))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  return `${hours ? `${hours}:` : ''}${`${minutes}`.padStart(2, '0')}:${`${secs}`.padStart(2, '0')}`
}

function roomCountdown(record, remainingColumn, clockMs, available, occupied) {
  if (!record) return available ? 'Đang trống' : occupied ? 'Đang sử dụng' : 'Chưa có dữ liệu'
  const deadlineMs = record._countdown_deadline ? new Date(record._countdown_deadline).getTime() : NaN
  if (Number.isFinite(deadlineMs)) {
    const delta = Math.ceil((deadlineMs - clockMs) / 1000)
    if (delta <= -15 * 60) return 'Đã hết giờ'
    return delta >= 0 ? `Còn ${durationText(delta)}` : `Trễ ${durationText(-delta)}`
  }
  const remainingRaw = cellValue(record, remainingColumn)
  const remaining = remainingRaw === '' ? null : Number(remainingRaw)
  if (Number.isFinite(remaining)) return remaining >= 0 ? `Còn ${remaining} phút` : `Trễ ${Math.abs(remaining)} phút`
  if (hasGroup(record, 'waiting')) return 'Đang chờ'
  if (hasGroup(record, 'doing')) return 'Đang thực hiện'
  return 'Chưa có thời gian'
}

function isPrivateService(value) {
  const normalized = normalizedColumn(value).replace(/\s+/g, ' ')
  return /(^|[^A-Z0-9])PR(?=$|[^A-Z0-9])/.test(normalized)
    || /(^|[^A-Z0-9])P\s*\.?\s*RIENG(?=$|[^A-Z0-9])/.test(normalized)
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
  const [roomSegment, setRoomSegment] = useState('all')
  const [selectedRoomKey, setSelectedRoomKey] = useState('')
  const [clockMs, setClockMs] = useState(Date.now())
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const [showAdminTools, setShowAdminTools] = useState(false)
  const [tourSource, setTourSource] = useState(null)
  const [tourSourceDraft, setTourSourceDraft] = useState('')
  const [tourSourceBusy, setTourSourceBusy] = useState(false)
  const [tourSourceNotice, setTourSourceNotice] = useState({ text: '', error: false })
  const stickyTopRef = useRef(null)
  const recordsTableRef = useRef(null)
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
    // Máy chủ giữ cache mỗi 1 phút; client chỉ thăm dò cache này mỗi 10 giây.
    void load(false, initiallyCached.current)
    const interval = window.setInterval(() => { void load(false, true) }, 10000)
    return () => window.clearInterval(interval)
  }, [load])

  useEffect(() => {
    const interval = window.setInterval(() => setClockMs(Date.now()), 1000)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    if (!isAdmin || !showAdminTools) return undefined
    let mounted = true
    veraApi.tourSource().then((source) => {
      if (!mounted) return
      setTourSource(source)
      setTourSourceDraft(source?.url || '')
    }).catch((err) => {
      if (mounted) setTourSourceNotice({ text: err.message || 'Không đọc được link TourVera hiện tại.', error: true })
    })
    return () => { mounted = false }
  }, [isAdmin, showAdminTools])

  const openStandaloneTour = () => {
    const url = new URL(window.location.href)
    url.searchParams.set('page', 'tour')
    url.searchParams.set('standalone', '1')
    window.open(url.toString(), '_blank', 'noopener,noreferrer')
  }

  const saveTourSource = async (event) => {
    event.preventDefault()
    if (!tourSourceDraft.trim() || tourSourceBusy) return
    setTourSourceBusy(true)
    setTourSourceNotice({ text: '', error: false })
    try {
      const source = await veraApi.saveTourSource({ url: tourSourceDraft.trim() })
      setTourSource(source)
      setTourSourceDraft(source?.url || tourSourceDraft.trim())
      setTourSourceNotice({ text: 'Đã lưu link TourVera và làm mới cache Bảng tua.', error: false })
      await load(true, true)
    } catch (err) {
      setTourSourceNotice({ text: err.message || 'Không lưu được link TourVera.', error: true })
    } finally {
      setTourSourceBusy(false)
    }
  }

  const columns = useMemo(() => data.columns || [], [data.columns])
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
  useEffect(() => {
    let frame = 0
    const updateStickyTableHeader = () => {
      window.cancelAnimationFrame(frame)
      frame = window.requestAnimationFrame(() => {
        const table = recordsTableRef.current
        const stickyTop = stickyTopRef.current
        if (!table || !stickyTop || window.matchMedia('(max-width: 640px)').matches) {
          table?.style.removeProperty('--tour-table-head-offset')
          return
        }
        const tableRect = table.getBoundingClientRect()
        const stickyRect = stickyTop.getBoundingClientRect()
        const headerHeight = table.querySelector('thead')?.getBoundingClientRect().height || 0
        const requestedOffset = Math.max(0, stickyRect.bottom + 4 - tableRect.top)
        const maximumOffset = Math.max(0, tableRect.height - headerHeight)
        table.style.setProperty(
          '--tour-table-head-offset',
          `${Math.min(requestedOffset, maximumOffset)}px`,
        )
      })
    }
    const observer = new ResizeObserver(updateStickyTableHeader)
    if (recordsTableRef.current) observer.observe(recordsTableRef.current)
    if (stickyTopRef.current) observer.observe(stickyTopRef.current)
    window.addEventListener('scroll', updateStickyTableHeader, { passive: true })
    window.addEventListener('resize', updateStickyTableHeader)
    updateStickyTableHeader()
    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
      window.removeEventListener('scroll', updateStickyTableHeader)
      window.removeEventListener('resize', updateStickyTableHeader)
    }
  }, [columns, displayedRecords.length])
  const availableRooms = useMemo(
    () => (Array.isArray(data.available_rooms) ? data.available_rooms : []),
    [data.available_rooms],
  )
  const roomColumn = findColumn(columns, ['PHONG'])
  const remainingColumn = findColumn(columns, ['TG CON LAI', 'THOI GIAN CON LAI'])
  const roomRecords = useMemo(() => {
    const grouped = new Map()
    validRecords.forEach((record) => {
      const key = roomKey(cellValue(record, roomColumn))
      if (!key) return
      grouped.set(key, [...(grouped.get(key) || []), record])
    })
    return grouped
  }, [roomColumn, validRecords])
  const roomCatalog = useMemo(() => {
    const sourceRooms = [
      ...(Array.isArray(data.rooms?.all) ? data.rooms.all : []),
      ...availableRooms,
      ...[...roomRecords.keys()],
    ]
    if (!sourceRooms.length && !data.rooms) return []
    const uniqueRooms = new Map(sourceRooms.map((room) => [roomKey(room), String(room).replace(/^phòng\s*/i, '').trim()]))
    VIP_ROOMS.forEach((room) => uniqueRooms.set(room, room))
    return [...uniqueRooms.values()].filter(Boolean).sort(compareRooms)
  }, [availableRooms, data.rooms, roomRecords])
  const standardRooms = useMemo(() => roomCatalog.filter((room) => !isVipRoom(room)), [roomCatalog])
  const vipRooms = useMemo(() => roomCatalog.filter(isVipRoom), [roomCatalog])
  const displayedRooms = roomSegment === 'vip' ? vipRooms : roomSegment === 'standard' ? standardRooms : roomCatalog
  const availableRoomKeys = useMemo(() => new Set(availableRooms.map(roomKey)), [availableRooms])
  const occupiedRoomKeys = useMemo(() => new Set((data.rooms?.occupied || []).map(roomKey)), [data.rooms?.occupied])
  const employeeColumn = employeeNameColumn(columns)
  const searchedRoomKeys = useMemo(() => {
    const needle = normalizedColumn(employeeSearch)
    if (!needle || !employeeColumn || !roomColumn) return new Set()
    return new Set(shiftRecords.flatMap((record) => {
      const employee = normalizedColumn(cellValue(record, employeeColumn))
      const key = roomKey(cellValue(record, roomColumn))
      return employee.includes(needle) && key ? [key] : []
    }))
  }, [employeeColumn, employeeSearch, roomColumn, shiftRecords])
  const statusColumn = findColumn(columns, ['TRANG THAI'])
  const serviceColumn = columns.find((column) => {
    const key = normalizedColumn(column)
    return key === 'DICH VU' || key.startsWith('DICH VU (')
  }) || ''
  const selectedRoom = roomCatalog.find((room) => roomKey(room) === selectedRoomKey) || ''
  const selectedRoomRecords = selectedRoomKey ? roomRecords.get(selectedRoomKey) || [] : []
  const retainedMetric = data.metric_snapshots?.[shiftFilter] || null
  const breakTotal = retainedMetric?.break_total_count ?? retainedMetric?.break_count ?? groupCount(shiftRecords, 'break')
  const breakActive = retainedMetric?.break_active_count ?? groupCount(shiftRecords, 'break')
  const metrics = useMemo(() => [
    { key: 'available', label: 'Có thể lên tua', value: groupCount(shiftRecords, 'available'), className: 'tour-available-metric' },
    { key: 'doing', label: 'Đang thực hiện', value: groupCount(shiftRecords, 'doing'), className: '' },
    { key: 'all', label: 'Số nhân viên', value: employeeCountFromStt(shiftRecords, columns), className: '' },
    { key: 'leave', label: 'Nghỉ phép', value: groupCount(shiftRecords, 'leave'), className: '' },
    { key: 'finishing', label: 'Sắp xong', value: groupCount(shiftRecords, 'finishing'), className: '' },
    { key: 'waiting', label: 'Đang chờ', value: groupCount(shiftRecords, 'waiting'), className: '' },
    { key: 'working', label: 'Đi làm', value: groupCount(shiftRecords, 'working'), className: '' },
    { key: 'break', label: 'Nghỉ giữa Ca', value: `${breakTotal}-${breakActive}`, className: 'tour-break-metric' },
  ], [breakActive, breakTotal, columns, shiftRecords])
  const chooseFilter = (key) => setActiveFilter((current) => key === 'all' || current === key ? 'all' : key)

  return <div className="feature-page tour-page">
    <style>{`
      .tour-page{gap:5px}
      .page-wrap.tour-page-wrap{padding-top:4px}
      .tour-page>.setup-note{padding:6px 9px;font-size:9px}
      .tour-sticky-top{display:grid;gap:4px;background:var(--paper,#f7faf8)}
      .tour-topbar{display:grid;grid-template-columns:minmax(260px,.72fr) minmax(330px,1fr) auto;align-items:center;gap:10px}
      .tour-heading-title{min-width:0}.tour-heading-title h1{margin:3px 0 0;color:var(--green-950);font-family:Georgia,serif;font-size:18px;line-height:.95}
      .tour-table tr.tour-row-waiting:not(.tour-row-break) td{color:#3f245d;background:var(--tour-row-waiting);font-weight:900}
      .tour-legend-grid .waiting{color:#3f245d;background:var(--tour-row-waiting);border-color:#c9aee7;font-weight:900}
      .tour-shift-filter{display:flex;align-items:center;justify-content:center;gap:4px;flex-wrap:wrap;margin:0}
      .tour-shift-filter button{min-width:66px;padding:5px 9px;border-radius:8px;font-size:10px}
      .tour-heading-actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.tour-heading-actions button{min-height:34px;padding:6px 10px;font-size:10px}.tour-admin-tools-toggle.active{color:#fff;background:#8c6b30;border-color:#8c6b30}
      .tour-control-layout{display:grid;grid-template-columns:minmax(520px,1fr) minmax(330px,.62fr);gap:4px;align-items:stretch}
      .tour-control-layout .tour-metrics{grid-template-columns:repeat(4,minmax(0,1fr));gap:4px}
      .metric-grid.small .metric-card.tour-metric-card{min-height:27px;gap:3px;border-radius:7px;padding:2px 6px}
      .metric-grid.small .metric-card.tour-metric-card span{font-size:7px}.metric-grid.small .metric-card.tour-metric-card strong{font-size:15px}
      .tour-room-segment-buttons{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px}
      .tour-room-segment-button{min-width:0;min-height:100%;border:1px solid transparent;border-radius:8px;padding:4px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;color:#fff;font-weight:900;text-align:center;letter-spacing:.02em}
      .tour-room-segment-button.all{background:linear-gradient(180deg,#426d5b,#294d3e);border-color:#244638}.tour-room-segment-button.standard{background:#155b78;border-color:#0d465f}.tour-room-segment-button.vip{background:linear-gradient(180deg,#bd9243,#92702f);border-color:#7d5c22}
      .tour-room-segment-button svg{width:15px;height:15px}.tour-room-segment-button span{font-size:9px;line-height:1}.tour-room-segment-button small{color:inherit;font-size:7px;opacity:.88}
      .tour-room-segment-button.active{outline:2px solid rgba(23,51,41,.18);outline-offset:1px;box-shadow:0 5px 12px rgba(22,51,41,.17)}
      .tour-table-panel{padding:5px}.tour-table th{padding-top:5px;padding-bottom:5px}.tour-table td{padding-top:5px;padding-bottom:5px}.tour-records-panel{min-height:0}.tour-records-panel .tour-table{max-height:none;overflow-x:auto;overflow-y:visible}.tour-records-panel .tour-table thead{position:relative;z-index:7;transform:translateY(var(--tour-table-head-offset,0));will-change:transform}.tour-records-panel .tour-table th{position:static}
      .tour-quick-tools{display:flex;gap:5px;align-items:center;flex-wrap:wrap;margin:3px 0 0}.tour-employee-search{position:relative;flex:1 1 260px;max-width:360px}.tour-employee-search svg{position:absolute;left:8px;top:50%;transform:translateY(-50%);pointer-events:none;color:#60756b}.tour-employee-search input{width:100%;height:27px;padding:4px 7px 4px 27px;box-sizing:border-box;font-size:9px}
      .tour-room-panel{margin:0;padding:5px;border:1px solid #cfe1d8;border-radius:9px;background:#f3faf6}.tour-room-panel-head{display:grid;grid-template-columns:minmax(520px,1fr) minmax(330px,.62fr);align-items:center;gap:4px;margin-bottom:3px}.tour-room-panel-title{display:flex;align-items:center;gap:4px;color:#173c30;font-size:11px;font-weight:900}.tour-room-panel-head small{justify-self:center;min-width:160px;color:#3f574c;font-size:15px;font-weight:950;line-height:1;text-align:center}.tour-room-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(108px,1fr));gap:3px}
      .tour-room-card{--room-segment:#155b78;position:relative;width:100%;min-width:0;min-height:53px;display:grid;align-content:space-between;gap:1px;border:1px solid rgba(0,0,0,.13);border-radius:7px;padding:4px;color:inherit;background:#fff;text-align:left;appearance:none;box-shadow:inset 0 2px 0 var(--room-segment),0 2px 5px rgba(28,52,42,.06);transition:transform .16s ease,box-shadow .16s ease}.tour-room-card.vip{--room-segment:#b58a31;border:3px solid #c59a3d;padding:2px;box-shadow:inset 0 2px 0 #f3cf72,0 2px 7px rgba(130,92,19,.16)}.tour-room-card.has-private-service{padding-right:29px}.tour-room-card:hover{transform:translateY(-1px);box-shadow:inset 0 2px 0 var(--room-segment),0 5px 10px rgba(28,52,42,.11)}.tour-room-card.vip:hover{box-shadow:inset 0 2px 0 #f3cf72,0 5px 11px rgba(130,92,19,.24)}.tour-room-card.selected{outline:2px solid #173c30;outline-offset:1px}.tour-room-card.vip.selected{outline-color:#9b6e16}
      @keyframes tour-room-search-pulse{0%,100%{filter:brightness(1);transform:scale(1);box-shadow:0 0 0 2px #ee3f62,0 2px 6px rgba(28,52,42,.08)}50%{filter:brightness(1.13);transform:scale(1.025);background:#55f0cf;box-shadow:0 0 0 4px #ffd54a,0 7px 15px rgba(238,63,98,.34)}}.tour-room-card.search-match{position:relative;z-index:3;animation:tour-room-search-pulse .8s ease-in-out infinite}
      .tour-room-card.state-green{background:var(--tour-row-green)}.tour-room-card.state-yellow{background:var(--tour-row-yellow)}.tour-room-card.state-red{background:var(--tour-row-red)}.tour-room-card.state-break{background:var(--tour-row-break)}.tour-room-card.state-waiting{color:#3f245d;background:var(--tour-row-waiting)}.tour-room-card.state-idle{background:var(--tour-row-idle)}.tour-room-card.state-leave,.tour-room-card.state-work,.tour-room-card.state-default,.tour-room-card.state-blank{background:#fff}.tour-room-card.state-leave{color:#a6a6a6}
      .tour-room-card-head{display:flex;align-items:center;justify-content:space-between;gap:3px}.tour-room-card-head strong{min-width:0;font-size:9px;font-weight:950}.tour-room-type{border-radius:999px;padding:1px 4px;color:#fff;background:var(--room-segment);font-size:5px;font-weight:950;letter-spacing:.04em}.tour-room-countdown{display:flex;align-items:center;gap:3px;font-variant-numeric:tabular-nums;font-size:10px;font-weight:950;white-space:nowrap}.tour-room-countdown svg{width:11px;height:11px;flex:0 0 auto}.tour-room-meta{min-height:8px;overflow:hidden;font-size:6px;font-weight:800;text-overflow:ellipsis;white-space:nowrap;opacity:.8}.tour-room-private-badge{position:absolute;right:4px;bottom:4px;width:21px;height:21px;display:grid;place-items:center;border:2px solid #fff;border-radius:50%;color:#fff;background:#e30057;box-shadow:0 0 0 2px #ffd447,0 4px 10px rgba(167,0,60,.38);font-size:9px;font-weight:950;line-height:1;letter-spacing:-.02em}
      .tour-room-empty{grid-column:1/-1;padding:6px;color:#5d7168;font-size:9px;text-align:center}
      .tour-room-detail{margin-top:5px;padding:6px;border:1px solid #d9e2dd;border-radius:8px;background:#fff}.tour-room-detail-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:4px}.tour-room-detail-head strong{font-size:10px}.tour-room-detail-head small{color:#68776f;font-size:7px;font-weight:800}.tour-room-detail-list{display:grid;gap:3px}.tour-room-detail-row{min-width:0;display:grid;grid-template-columns:minmax(90px,.55fr) minmax(120px,1fr);gap:8px;padding:4px 6px;border-radius:6px;background:#f3f6f4;font-size:8px}.tour-room-detail-row strong,.tour-room-detail-row span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.tour-room-detail-row span{color:#55665e}.tour-room-detail-empty{padding:4px;color:#68776f;font-size:8px}
      .tour-legend{padding:9px}.tour-legend .panel-title-row{margin-bottom:5px}.tour-legend .panel-title-row h2{font-size:14px}.tour-legend .panel-title-row p{font-size:9px}.tour-legend-grid{gap:4px}.tour-legend-grid span{padding:4px 7px;font-size:8px}
      .tour-source-panel{padding:8px}.tour-source-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:5px}.tour-source-head strong{display:flex;align-items:center;gap:5px;font-size:11px}.tour-source-head small{color:#65756e;font-size:8px}.tour-source-form{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px}.tour-source-form input{min-width:0;height:32px;padding:5px 9px;font-size:10px}.tour-source-form button{min-height:32px;padding:5px 10px}.tour-source-meta{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-top:5px;color:#65756e;font-size:8px}.tour-source-meta a{color:#155b78;font-weight:850}.tour-source-notice{font-weight:800;color:#247146}.tour-source-notice.error{color:#a52a22}
      @media(min-width:641px){.tour-sticky-top{position:sticky;top:74px;z-index:18;padding:3px 0 2px;box-shadow:0 6px 12px rgba(25,58,46,.04)}.tour-records-panel .tour-table th{top:0}.tour-room-detail{max-height:100px;overflow:auto}.tour-room-detail.vip-19{max-height:none;overflow:visible}}
      @media(prefers-reduced-motion:reduce){.tour-room-card.search-match{animation:none;outline:4px solid #ee3f62;outline-offset:1px;background:#55f0cf}}
      @media(max-width:640px){
        .tour-sticky-top{position:static}.tour-topbar{grid-template-columns:1fr;gap:6px}.tour-heading-title h1{font-size:14.5px}.tour-shift-filter{order:3}.tour-records-panel .tour-table{max-height:none;overflow-x:hidden;overflow-y:visible}
        .tour-shift-filter{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px;margin-bottom:7px}
        .tour-shift-filter button{min-width:0;padding:7px 4px;font-size:11px}
        .tour-heading-actions{width:100%;justify-content:stretch}.tour-heading-actions button{flex:1}
        .tour-metrics{grid-template-columns:repeat(4,minmax(0,1fr));gap:5px}
        .metric-grid.small .metric-card.tour-metric-card{min-height:31px;display:flex;flex-direction:column;justify-content:center;gap:1px;padding:2px;text-align:center}
        .metric-grid.small .metric-card.tour-metric-card span{font-size:8px;line-height:1.05}
        .metric-grid.small .metric-card.tour-metric-card strong{font-size:14px}
        .tour-control-layout{grid-template-columns:1fr;gap:4px}.tour-room-segment-button{min-height:42px;padding:3px 2px}.tour-room-segment-button svg{width:12px;height:12px}.tour-room-segment-button span{font-size:7px}.tour-room-segment-button small{font-size:6px}
        .tour-table-panel{padding:5px}
        .tour-quick-tools{display:grid;grid-template-columns:minmax(0,1fr);gap:4px;margin:4px 0}
        .tour-employee-search{min-width:0;max-width:none}
        .tour-employee-search input{min-width:0;height:29px;padding:5px 5px 5px 27px;font-size:8px}
        .tour-employee-search svg{left:8px;width:14px}
        .tour-source-head{align-items:flex-start;flex-direction:column}.tour-source-form{grid-template-columns:1fr}.tour-source-form button{width:100%}
        .tour-room-panel{padding:5px}.tour-room-panel-head{grid-template-columns:1fr;margin-bottom:4px}.tour-room-panel-title{font-size:9px}.tour-room-panel-head small{min-width:125px;font-size:12px}.tour-room-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:3px}.tour-room-card{min-height:58px;padding:4px}.tour-room-card.vip{padding:2px}.tour-room-card-head strong{font-size:8px}.tour-room-type{padding:2px 3px;font-size:4px}.tour-room-countdown{font-size:9px}.tour-room-countdown svg{width:10px;height:10px}.tour-room-meta{font-size:6px}.tour-room-detail-row{grid-template-columns:minmax(75px,.55fr) minmax(0,1fr);gap:4px;padding:4px;font-size:7px}
      }
      @media(max-width:420px){
        .tour-room-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
      }
    `}</style>
    <div className="tour-sticky-top" ref={stickyTopRef}>
      <div className="tour-topbar">
        <div className="tour-heading-title"><h1>BẢNG TUA</h1></div>
        <div className="tour-shift-filter" aria-label="Lọc Bảng tua theo ca">
          <button type="button" className={shiftFilter === 'all' ? 'primary-button' : 'secondary-button'} onClick={() => setShiftFilter('all')}>Tất cả</button>
          <button type="button" className={shiftFilter === 'ca1' ? 'primary-button' : 'secondary-button'} onClick={() => setShiftFilter('ca1')}>Ca 1</button>
          <button type="button" className={shiftFilter === 'ca2' ? 'primary-button' : 'secondary-button'} onClick={() => setShiftFilter('ca2')}>Ca 2</button>
        </div>
        <div className="tour-heading-actions">{isAdmin && <button type="button" className={`secondary-button tour-admin-tools-toggle ${showAdminTools ? 'active' : ''}`.trim()} onClick={() => setShowAdminTools((current) => !current)} aria-expanded={showAdminTools}><Link2 size={16} /> {showAdminTools ? 'Ẩn Link & màu dòng' : 'Hiện Link & màu dòng'}</button>}<button type="button" className="secondary-button" onClick={openStandaloneTour}><ExternalLink size={16} /> Mở tab riêng</button>{user?.permissions?.tour_refresh && <button className="secondary-button" onClick={() => load(true)} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới Bảng tua</button>}</div>
      </div>
      {error && <div className="error-box">{error}</div>}
      {data.countdown_error && <div className="warning-box">Countdown Bảng tua: {data.countdown_error}</div>}
      {data.metrics_retained_until_10 && <div className="setup-note">Số khách và tổng lượt Nghỉ giữa ca đang giữ số ngày {String(data.metrics_business_date || '').split('-').reverse().join('/')} đến 10:00 sáng. Nghỉ giữa ca hiển thị Tổng lượt-Đang ở ngoài.</div>}
      <div className="tour-control-layout">
        <div className="metric-grid small tour-metrics">{metrics.map(({ key, label, value, className }) => <button type="button" className={`metric-card tour-metric-card ${className} ${activeFilter === key ? 'active' : ''}`.trim()} onClick={() => chooseFilter(key)} aria-pressed={activeFilter === key} title={key === 'all' ? 'Khôi phục thứ tự danh sách' : key === 'finishing' ? 'Ưu tiên Đang rảnh và Sắp xong lên đầu danh sách' : `Ưu tiên ${label} lên đầu danh sách`} key={key}><span>{label}</span><strong>{value}</strong></button>)}</div>
        <div className="tour-room-segment-buttons" aria-label="Chọn phân khúc phòng">
          <button type="button" className={`tour-room-segment-button all ${roomSegment === 'all' ? 'active' : ''}`} onClick={() => { setRoomSegment('all'); setSelectedRoomKey('') }} aria-pressed={roomSegment === 'all'}><LayoutGrid size={18}/><span>TẤT CẢ<br/>PHÒNG</span><small>{roomCatalog.length} phòng</small></button>
          <button type="button" className={`tour-room-segment-button standard ${roomSegment === 'standard' ? 'active' : ''}`} onClick={() => { setRoomSegment('standard'); setSelectedRoomKey('') }} aria-pressed={roomSegment === 'standard'}><DoorOpen size={20}/><span>STANDARD<br/>ROOM</span><small>{standardRooms.length} phòng</small></button>
          <button type="button" className={`tour-room-segment-button vip ${roomSegment === 'vip' ? 'active' : ''}`} onClick={() => { setRoomSegment('vip'); setSelectedRoomKey('') }} aria-pressed={roomSegment === 'vip'}><Crown size={20}/><span>VIP ROOM</span><small>{vipRooms.length} phòng</small></button>
        </div>
      </div>
      <section className="panel tour-table-panel tour-room-table-panel">
      <div className={`tour-room-panel ${roomSegment}`}>
        <div className="tour-room-panel-head"><div className="tour-room-panel-title">{roomSegment === 'vip' ? <Crown size={16}/> : roomSegment === 'standard' ? <DoorOpen size={16}/> : <LayoutGrid size={16}/>} {roomSegment === 'vip' ? 'Phòng VIP' : roomSegment === 'standard' ? 'Phòng Standard' : 'Tất cả phòng'}</div><small>{displayedRooms.filter((room) => availableRoomKeys.has(roomKey(room))).length} phòng đang trống</small></div>
        <div className="tour-room-grid">
          {displayedRooms.map((room) => {
            const key = roomKey(room)
            const records = roomRecords.get(key) || []
            const record = pickRoomRecord(records, remainingColumn)
            const available = availableRoomKeys.has(key)
            const occupied = occupiedRoomKeys.has(key)
            const state = roomState(record, available, clockMs)
            const employee = cellValue(record, employeeColumn)
            const status = cellValue(record, statusColumn)
            const hasPrivateService = records.some((item) => isPrivateService(cellValue(item, serviceColumn)))
            return <button type="button" className={`tour-room-card ${isVipRoom(room) ? 'vip' : 'standard'} state-${state} ${hasPrivateService ? 'has-private-service' : ''} ${selectedRoomKey === key ? 'selected' : ''} ${searchedRoomKeys.has(key) ? 'search-match' : ''}`.trim()} key={key} onClick={() => setSelectedRoomKey((current) => current === key ? '' : key)} aria-expanded={selectedRoomKey === key}>
              <div className="tour-room-card-head"><strong>{roomLabel(room)}</strong><span className="tour-room-type">{isVipRoom(room) ? 'VIP' : 'STANDARD'}</span></div>
              <div className="tour-room-countdown"><Clock3 size={16}/><span>{roomCountdown(record, remainingColumn, clockMs, available, occupied)}</span></div>
              <div className="tour-room-meta" title={[employee, status].filter(Boolean).join(' · ')}>{[employee, status].filter(Boolean).join(' · ') || (available ? 'Sẵn sàng nhận khách' : 'Chưa có nhân viên')}</div>
              {hasPrivateService && <span className="tour-room-private-badge" aria-label="Dịch vụ phòng riêng">PR</span>}
            </button>
          })}
          {!displayedRooms.length && <div className="tour-room-empty">Chưa có dữ liệu phòng {roomSegment === 'vip' ? 'VIP' : roomSegment === 'standard' ? 'Standard' : ''}.</div>}
        </div>
        {selectedRoomKey && selectedRoom && <div className={`tour-room-detail ${roomKey(selectedRoom) === '19' ? 'vip-19' : ''}`.trim()} role="region" aria-label={`Chi tiết ${roomLabel(selectedRoom)}`}>
          <div className="tour-room-detail-head"><strong>{roomLabel(selectedRoom)} · Danh sách nhân viên</strong><small>{selectedRoomRecords.length} nhân viên · Bấm lại phòng để đóng</small></div>
          {selectedRoomRecords.length ? <div className="tour-room-detail-list">{selectedRoomRecords.map((item, index) => {
            const employee = cellValue(item, employeeColumn) || 'Chưa có tên nhân viên'
            const service = cellValue(item, serviceColumn) || 'Chưa có dịch vụ'
            return <div className="tour-room-detail-row" key={`${sttValue(item, columns)}:${index}`}><strong title={employee}>{employee}</strong><span title={service}>{service}</span></div>
          })}</div> : <div className="tour-room-detail-empty">Phòng đang trống, chưa có nhân viên và dịch vụ.</div>}
        </div>}
      </div>
      <div className="tour-quick-tools">
        <label className="tour-employee-search" aria-label="Tìm nhanh tên nhân viên"><Search size={16}/><input type="search" value={employeeSearch} placeholder="Tìm nhanh tên nhân viên…" onChange={(event) => setEmployeeSearch(event.target.value)} /></label>
      </div>
      </section>
    </div>
    <section className="panel tour-table-panel tour-records-panel">
      <div className="responsive-data-table tour-table" ref={recordsTableRef} tabIndex="0" aria-label="Danh sách Bảng tua"><table><thead><tr>{columns.map((column) => <th className={columnClass(column)} key={column}>{column}</th>)}</tr></thead><tbody>{displayedRecords.map((item, index) => <tr className={rowClass(item)} key={`${sttValue(item, columns)}:${index}`}>{columns.map((column) => <td className={columnClass(column)} key={column}>{String(item[column] ?? '')}</td>)}</tr>)}</tbody></table></div>
      {!busy && !displayedRecords.length && <div className="setup-note">Không có nhân viên phù hợp với ca/bộ lọc đang chọn.</div>}
    </section>
    {isAdmin && showAdminTools && <>
    <section className="panel tour-source-panel">
      <div className="tour-source-head"><strong><Link2 size={15}/> Link file TourVera</strong><small>Chỉ Admin · cấu hình dùng chung, không cần sửa code khi đổi file</small></div>
      <form className="tour-source-form" onSubmit={saveTourSource}>
        <input type="url" value={tourSourceDraft} onChange={(event) => setTourSourceDraft(event.target.value)} placeholder="Dán link Google Drive của TourVera.xlsm" aria-label="Link Google Drive của TourVera" required />
        <button type="submit" className="primary-button" disabled={tourSourceBusy || !tourSourceDraft.trim()}><Save size={15}/> {tourSourceBusy ? 'Đang kiểm tra…' : 'Lưu link'}</button>
      </form>
      <div className="tour-source-meta">
        {tourSource?.name && <span>File hiện tại: <strong>{tourSource.name}</strong></span>}
        {tourSource?.url && <a href={tourSource.url} target="_blank" rel="noreferrer">Mở trên Google Drive</a>}
        {tourSourceNotice.text && <span className={`tour-source-notice ${tourSourceNotice.error ? 'error' : ''}`}>{tourSourceNotice.text}</span>}
      </div>
    </section>
    <section className="panel tour-legend"><div className="panel-title-row"><div><h2>MÀU DÒNG</h2><p>Màu áp dụng cho toàn bộ dòng và Break luôn được ưu tiên cao nhất.</p></div></div><div className="tour-legend-grid"><span className="green">≥15 phút · Xanh</span><span className="yellow">0–&lt;15 · Vàng</span><span className="red">-15–&lt;0 · Đỏ</span><span className="blank">≤-15 · Làm trống</span><span className="break">Break · Cam</span><span className="waiting">Đang chờ · Tím</span><span className="idle">Đi làm + Vào ca + đang rảnh</span><span className="leave">Nghỉ phép · Chữ mờ</span></div></section>
    </>}
    <div className="setup-note tour-countdown-note">Thời gian còn lại do hệ thống tự đếm: Yêu cầu trống dùng “TG bắt đầu thực hiện”; Yêu cầu YC dùng “TG bắt đầu thực hiện YC”; cả hai cộng theo Thời lượng.</div>
  </div>
}
