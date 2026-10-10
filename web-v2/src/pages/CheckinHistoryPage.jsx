import LiveTourSearchSelect from '../components/LiveTourSearchSelect'
import { checkinLookupOptions } from '../lib/checkinHistory'
import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Download, RefreshCw } from 'lucide-react'
import VeraDateInput from '../components/VeraDateInput'
import { veraApi } from '../lib/api'
import { formatVeraDate, formatVeraDateTime } from '../lib/veraDate'

import { CHECKIN_PRESETS, EMPTY_CHECKIN_DETAILS, checkinDateRange, checkinQuery, checkinRangeError, initialCheckinFilters } from '../lib/checkinHistory'
import './DevicesAndCheckin.css'

const FacegateCaptureAssignment = lazy(() => import('../components/FacegateCaptureAssignment'))

function MappingCheck({ record }) {
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const check = async () => {
    setBusy(true); setResult(null)
    try { setResult(await veraApi.checkFacegateMapping(record.registration_ref)) }
    catch (error) { setResult({ message: error.message || 'Không xác minh được hồ sơ thiết bị.' }) }
    finally { setBusy(false) }
  }
  return <div><button type="button" className="secondary-button" disabled={busy || !record.registration_ref} onClick={check}>{busy ? 'Đang kiểm tra…' : 'Đối chiếu'}</button>
    {result && <p role="status">{result.status === 'reference_match' && <strong>{result.username} · {result.employee_code}<br /></strong>}{result.message}</p>}</div>
}

function CaptureImageButton({ record, onChoose }) {
  const [imageUrl, setImageUrl] = useState('')
  const [imageBlob, setImageBlob] = useState(null)
  const active = useRef(true)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => () => { if (imageUrl) URL.revokeObjectURL(imageUrl) }, [imageUrl])

  const toggle = async () => {
    if (imageUrl) { setOpen(value => !value); return }
    setBusy(true); setError('')
    try {
      const blob = await veraApi.facegateCaptureImage(record.image_ref)
      if (!active.current) return
      if (!String(blob.type || '').toLowerCase().startsWith('image/')) throw new Error('Thiết bị không trả về dữ liệu ảnh.')
      setImageBlob(blob); setImageUrl(URL.createObjectURL(blob)); setOpen(true)
    } catch (cause) {
      if (active.current) setError(cause.message || 'Không tải được ảnh capture.')
    } finally { if (active.current) setBusy(false) }
  }

  return <div>
    <button className="secondary-button" type="button" disabled={busy} onClick={toggle}>{busy ? 'Đang tải ảnh…' : open ? 'Ẩn ảnh' : 'Xem ảnh'}</button>
    {error && <small role="alert">{error}</small>}
    {open && imageUrl && <div><img src={imageUrl} alt={`Ảnh capture sự kiện ${record.event_id}`} loading="lazy" style={{ display: 'block', width: 120, height: 160, objectFit: 'contain', marginTop: 8 }} />{onChoose && <button type="button" className="secondary-button" onClick={() => onChoose(record, imageBlob)}>Chọn ảnh cho nhân viên</button>}</div>}
  </div>
}

export default function CheckinHistoryPage({ user, embedded = false }) {
  usePageRefresh(() => load(), () => Boolean(busy || exporting || selectedCapture))
  const [selectedCapture, setSelectedCapture] = useState(null)
  const [assignmentNotice, setAssignmentNotice] = useState('')
  const canAssign = user?.role === 'admin' || user?.permissions?.employee_face_id_manage || user?.permissions?.employee_face_id_all_users_edit
  const [filters, setFilters] = useState(initialCheckinFilters)
  const [records, setRecords] = useState(null)
  const [loadedQuery, setLoadedQuery] = useState(null)
  const [lookup, setLookup] = useState({ key: '', rows: [] })
  const [lookupError, setLookupError] = useState('')
  const [options, setOptions] = useState({ statuses: [], types: [] })
  const [truncated, setTruncated] = useState(false)
  const [attendancePolicy, setAttendancePolicy] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [dirty, setDirty] = useState(false)
  const formRef = useRef(null)
  const requestId = useRef(0)
  useEffect(() => () => { requestId.current += 1 }, [])
  const source = filters.source
  const change = patch => { setFilters(value => ({ ...value, ...patch })); setDirty(true); setError('') }
  const lookupQuery = checkinQuery({ ...filters, employee: '', event_id: '' })
  const lookupKey = JSON.stringify(lookupQuery)
  const hasLookupText = Boolean(filters.employee || filters.event_id)
  useEffect(() => {
    if (!hasLookupText || lookup.key === lookupKey || !['facegate_saved', 'timesoft'].includes(source) || checkinRangeError(filters)) return undefined
    let active = true
    const timer = window.setTimeout(() => {
      setLookupError('')
      veraApi.checkinHistory(JSON.parse(lookupKey)).then(response => {
        if (active) setLookup({ key: lookupKey, rows: response.records || [] })
      }).catch(error => { if (active) setLookupError(error.message || 'Không tải được gợi ý tìm kiếm.') })
    }, 180)
    return () => { active = false; window.clearTimeout(timer) }
  }, [hasLookupText, lookup.key, lookupKey, source, filters])
  const lookupRows = lookup.key === lookupKey ? lookup.rows : []
  const lookupOptions = checkinLookupOptions(lookupRows)
  const preset = value => change({ preset: value, ...checkinDateRange(value), event_date: '' })
  const load = async (event, queryFilters = filters) => {
    event?.preventDefault()
    if (!formRef.current?.reportValidity()) return
    const invalid = checkinRangeError(queryFilters)
    if (invalid) { setError(invalid); return }
    const id = ++requestId.current
    const query = checkinQuery(queryFilters)
    setBusy(true); setError('')
    try {
      const response = await veraApi.checkinHistory(query)
      if (requestId.current !== id) return
      setRecords(response.records || [])
      setAttendancePolicy(response.attendance_policy || null)
      if (!query.employee && !query.event_id) setLookup({ key: JSON.stringify({ ...query, employee: '', event_id: '' }), rows: response.records || [] })
      setTruncated(Boolean(response.truncated))
      setOptions(response.options || { statuses: [], types: [] })
      setLoadedQuery(query); setDirty(false)
    } catch (cause) {
      if (requestId.current === id) {
        setError(cause.message || 'Không tải được lịch sử checkin.')
        if ([401, 403].includes(cause.status)) setRecords(null)
      }
    } finally { if (requestId.current === id) setBusy(false) }
  }
  const loadFromFacegate = async () => {
    const directFilters = { ...filters, source: 'facegate', status: '', event_type: '' }
    setFilters(directFilters)
    setRecords(null)
    setLoadedQuery(null)
    setTruncated(false)
    setOptions({ statuses: [], types: [] })
    setDirty(false)
    await load(null, directFilters)
  }
  const exportExcel = async () => {
    if (!formRef.current?.reportValidity() || dirty || !loadedQuery) return
    setExporting(true); setError('')
    try { await veraApi.exportCheckinHistory(loadedQuery) }
    catch (cause) { setError(cause.message || 'Không xuất được Excel.') }
    finally { setExporting(false) }
  }
  const visible = records || []

  return <section className="checkin-history-page">
    <div className="page-heading"><div>{embedded ? <h2>LỊCH SỬ CHECK IN</h2> : <h1>LỊCH SỬ CHECK IN</h1>}<p>Tra cứu nhật ký thiết bị hoặc dữ liệu chấm công đã đồng bộ vào VERA.</p></div></div>
    <form ref={formRef} className="checkin-filters" onSubmit={load} onInput={() => setDirty(true)}>
      <fieldset disabled={busy || exporting}>
        <div className="checkin-filter-dates">
          <label>Thời gian<select value={filters.preset} onChange={event => preset(event.target.value)}>{CHECKIN_PRESETS.map(([id, label]) => <option value={id} key={id}>{label}</option>)}</select></label>
          <label>Từ ngày<VeraDateInput value={filters.date_from} max={filters.date_to} onChange={event => change({ date_from: event.target.value, preset: 'custom' })} required /></label>
          <label>Đến ngày<VeraDateInput value={filters.date_to} min={filters.date_from} onChange={event => change({ date_to: event.target.value, preset: 'custom' })} required /></label>
        </div>
        <div className="checkin-filter-details">
          <label>Ngày cụ thể<VeraDateInput value={filters.event_date} min={filters.date_from} max={filters.date_to} onChange={event => change({ event_date: event.target.value })} /></label>
          <label>Nguồn dữ liệu<select value={source} onChange={event => { change({ source: event.target.value, ...EMPTY_CHECKIN_DETAILS }); setRecords(null); setOptions({ statuses: [], types: [] }) }}><option value="facegate_saved">FaceGate · Đã lưu trong VERA</option><option value="facegate">FaceGate · Trực tiếp từ máy</option><option value="capture">FaceGate · Capture Log</option><option value="timesoft">TimeSoft · Đã đồng bộ VERA</option></select></label>
          <label>{source === 'timesoft' ? 'Trạng thái ra' : 'Loại sự kiện'}<select value={filters.event_type} onChange={event => change({ event_type: event.target.value })}><option value="">Tất cả</option>{options.types.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
          <label>{source === 'facegate' ? 'Tên trên máy' : 'Tên / mã nhân viên'}<LiveTourSearchSelect hideLabel label={source === 'facegate' ? 'Tên trên máy' : 'Tên / mã nhân viên'} value={filters.employee} searchValue={filters.employee} disabled={busy || exporting || source === 'capture'} options={lookupOptions.employees} onSearch={value => change({ employee: value.slice(0, 200) })} onChange={value => change({ employee: value })} placeholder={source === 'capture' ? 'Capture không có mã nhân viên' : 'Tìm tên hoặc mã'} emptyLabel="Tất cả nhân viên" /></label>
          <label>Mã sự kiện<LiveTourSearchSelect hideLabel label="Mã sự kiện" value={filters.event_id} searchValue={filters.event_id} disabled={busy || exporting || source === 'timesoft'} options={lookupOptions.events} onSearch={value => change({ event_id: value.slice(0, 64) })} onChange={value => change({ event_id: value })} placeholder="Tìm mã sự kiện" emptyLabel="Tất cả sự kiện" /></label>
          <label>{source === 'timesoft' ? 'Trạng thái vào' : 'Trạng thái'}<select value={filters.status} onChange={event => change({ status: event.target.value })}><option value="">Tất cả</option>{options.statuses.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
        </div>
        <div className="checkin-quick-dates">{CHECKIN_PRESETS.filter(([id]) => id !== 'custom').map(([id, label]) => <button key={id} type="button" className="secondary-button" aria-pressed={filters.preset === id} onClick={() => preset(id)}>{label}</button>)}<button type="button" className="secondary-button" onClick={() => change(EMPTY_CHECKIN_DETAILS)}>Xóa lọc chi tiết</button></div>
        <div className="device-actions checkin-history-actions">
          <button className="secondary-button" type="submit"><RefreshCw size={16} className={busy ? 'spin' : ''} /><span>{busy ? 'Đang tải…' : 'Xem lịch sử'}</span></button>
          <button className="secondary-button checkin-live-device-button" type="button" disabled={busy || exporting} onClick={loadFromFacegate}><RefreshCw size={16} className={busy && source === 'facegate' ? 'spin' : ''} /><span>{busy && source === 'facegate' ? 'Đang tải từ máy…' : 'Tải từ Face ID'}</span></button>
          <button className="secondary-button" type="button" disabled={busy || !records?.length || dirty || truncated} onClick={exportExcel}><Download size={16} /><span>{exporting ? 'Đang xuất…' : 'Xuất excel'}</span></button>
        </div>
      </fieldset>
    </form>
    {dirty && records && <p role="status">Bộ lọc đã thay đổi. Bấm Xem lịch sử để cập nhật bảng và xuất Excel.</p>}
    {lookupError && <p role="alert">{lookupError}</p>}
    <StableFeedback>{error && <p role="alert">{error}</p>}</StableFeedback>
    {records && <>
      <p>Dữ liệu đã tải: {formatVeraDate(loadedQuery.start)} – {formatVeraDate(loadedQuery.end)}.</p>
      {visible.length === 0 && <p role="status">Không có bản ghi phù hợp bộ lọc.</p>}
      {(source === 'facegate' || source === 'facegate_saved') ? <>
        <p>{visible.length} sự kiện FaceGate {source === 'facegate_saved' ? 'đã lưu trong VERA' : 'đọc trực tiếp từ máy'} trong kỳ. {source === 'facegate_saved' ? 'Ánh xạ hiển thị theo hồ sơ Admin đã xác nhận.' : 'Bấm Đối chiếu để kiểm tra hồ sơ đã ánh xạ.'} {attendancePolicy?.source === 'facegate' ? `FaceGate là nguồn chấm công từ ${formatVeraDate(attendancePolicy.effective_date)}. Chỉ dữ liệu đã đồng bộ, xác minh và đủ điều kiện mới được dùng tính công/lương; số sự kiện ở đây không phải số ngày công.` : attendancePolicy?.source === 'timesoft' ? 'Nguồn tính công hiện tại là TimeSoft; nhật ký FaceGate ở đây dùng để tra cứu.' : 'Xem nguồn tính công hiện tại tại Quản lý thiết bị. Nhật ký sự kiện không phải bảng công đã xác nhận.'}</p>
        {source === 'facegate_saved' && <p role="status">Đã khớp: {visible.filter(item => item.mapping_status === 'reference_match').length} · Chưa ánh xạ: {visible.filter(item => item.mapping_status !== 'reference_match').length}.</p>}
        {truncated && <p role="status">Kết quả đã chạm giới hạn truy vấn. Hãy thu hẹp khoảng ngày để xem và xuất đầy đủ dữ liệu.</p>}
        <div className="responsive-data-table"><table><thead><tr><th>Mã sự kiện</th><th>Thời điểm</th><th>Tên hiển thị trên máy</th><th>Mã trạng thái</th><th>Mã loại trên máy</th><th>Đối chiếu nhân viên</th></tr></thead><tbody>
          {visible.map(item => <tr key={`${item.event_id}-${item.occurred_at}`}>
            <td data-label="Mã sự kiện">{item.event_id}</td><td data-label="Thời điểm">{formatVeraDateTime(item.occurred_at, '—')}</td>
            <td data-label="Tên hiển thị trên máy">{item.device_name || '—'}</td><td data-label="Mã trạng thái">{item.status_code ?? '—'}</td><td data-label="Mã loại trên máy">{item.type_code ?? '—'}</td>
            <td data-label="Đối chiếu nhân viên">{source === 'facegate_saved' ? (item.mapping_status === 'reference_match' ? `${item.employee_name} · ${item.employee_code}` : 'Chưa ánh xạ') : <MappingCheck key={`${item.event_id}-${JSON.stringify(item.registration_ref)}`} record={item} />}</td>
          </tr>)}
        </tbody></table></div>
      </> : source === 'capture' ? <>
        <p>{visible.length} ảnh/sự kiện Capture Log trong kỳ. Ảnh chỉ tải khi bấm Xem ảnh. Kiểm tra đúng nhân viên trước khi chọn và lưu vào ẢNH FACE ID; thao tác này chưa đăng ký ảnh lên máy hoặc thay đổi chấm công.</p>
        {truncated && <p role="status">Kết quả đã chạm giới hạn truy vấn. Hãy thu hẹp khoảng ngày để xem và xuất đầy đủ dữ liệu.</p>}
        <div className="responsive-data-table"><table><thead><tr><th>Mã sự kiện</th><th>Thời điểm</th><th>Loại sự kiện</th><th>Trạng thái trên máy</th><th>Ảnh capture</th></tr></thead><tbody>
          {visible.map(item => <tr key={item.event_id}>
            <td data-label="Mã sự kiện">{item.event_id}</td><td data-label="Thời điểm">{formatVeraDateTime(item.occurred_at, '—')}</td>
            <td data-label="Loại sự kiện">{item.event_text || '—'}</td><td data-label="Trạng thái trên máy">{item.event_status || '—'}</td>
            <td data-label="Ảnh capture">{item.image_available ? <CaptureImageButton key={`${item.event_id}-${JSON.stringify(item.image_ref)}`} record={item} onChoose={canAssign ? (record, blob) => { setAssignmentNotice(''); setSelectedCapture({ record, blob }) } : undefined} /> : 'Không có ảnh'}</td>
          </tr>)}
        </tbody></table></div>
      </> : <>
        <p>{visible.length} bản ghi trong kỳ đã chọn. Nguồn: TimeSoft đã đồng bộ; không phải log trực tiếp từ thiết bị.</p>
        <div className="responsive-data-table"><table><thead><tr><th>Ngày</th><th>Mã nhân viên</th><th>Nhân viên</th><th>Giờ vào</th><th>Các lần chấm</th><th>Giờ ra</th></tr></thead><tbody>
          {visible.map((item, index) => <tr key={`${item.date}-${item.employee_code}-${index}`}>
            <td data-label="Ngày">{formatVeraDate(item.date, '—')}</td><td data-label="Mã nhân viên">{item.employee_code || '—'}</td>
            <td data-label="Nhân viên">{item.employee_name || '—'}</td><td data-label="Giờ vào">{item.check_in || '—'}</td>
            <td data-label="Các lần chấm">{(item.punch_times || []).join(' · ') || '—'}</td><td data-label="Giờ ra">{item.check_out || '—'}</td>
          </tr>)}
        </tbody></table></div>
      </>}
    </>}
    {assignmentNotice && <p role="status">{assignmentNotice}</p>}
    {selectedCapture && <Suspense fallback={<p role="status">Đang mở chọn ảnh…</p>}><FacegateCaptureAssignment capture={selectedCapture}
      onClose={() => setSelectedCapture(null)} onSaved={username => {
        setAssignmentNotice(`Đã lưu ẢNH FACE ID cho ${username} trong VERA SPA. Chưa đăng ký ảnh lên máy FaceGate.`)
        setSelectedCapture(null)
      }}/></Suspense>}
  </section>
}
