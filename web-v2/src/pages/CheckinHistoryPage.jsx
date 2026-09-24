import { useEffect, useRef, useState } from 'react'
import { Download, History, RefreshCw } from 'lucide-react'
import VeraDateInput from '../components/VeraDateInput'
import { veraApi } from '../lib/api'
import { formatVeraDate, formatVeraDateTime } from '../lib/veraDate'

import { CHECKIN_PRESETS, EMPTY_CHECKIN_DETAILS, checkinDateRange, checkinQuery, checkinRangeError, initialCheckinFilters } from '../lib/checkinHistory'
import './DevicesAndCheckin.css'

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

function FacegateMappings() {
  const [data, setData] = useState(null)
  const [profileId, setProfileId] = useState('')
  const [profile, setProfile] = useState(null)
  const [username, setUsername] = useState('')
  const [code, setCode] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const run = async (action) => {
    setBusy(true); setMessage('')
    try { await action() } catch (error) { setMessage(error.message || 'Không thực hiện được yêu cầu.') }
    finally { setBusy(false) }
  }
  return <details><summary>Ánh xạ hồ sơ FaceGate với nhân viên</summary>
    <p>Admin chọn nhân viên VERA và nhập mã TimeSoft đã kiểm tra. Kết quả đối chiếu ảnh chỉ dùng tra cứu; ảnh đăng ký thay đổi cần xác nhận lại.</p>
    <button type="button" className="secondary-button" disabled={busy} onClick={() => run(async () => setData(await veraApi.facegateMappings()))}>Tải danh sách ánh xạ</button>
    {data && <>
      <form onSubmit={event => { event.preventDefault(); if (!profile) return; run(async () => {
        await veraApi.saveFacegateMapping({ profile_id: profile.profile_id, device_name: profile.device_name, registration_ref: profile.registration_ref, username, employee_code: code.trim(), confirmed })
        setData(await veraApi.facegateMappings()); setConfirmed(false); setMessage('Đã lưu ánh xạ để đối chiếu.')
      }) }}>
        <fieldset disabled={busy}>
          <label>ID hồ sơ FaceGate<input type="number" min="1" max="2147483647" required value={profileId} onChange={event => { setProfileId(event.target.value); setProfile(null); setConfirmed(false) }} /></label>
          <button type="button" className="secondary-button" disabled={!/^[1-9][0-9]*$/.test(profileId)} onClick={() => run(async () => { setProfile(null); setConfirmed(false); setProfile(await veraApi.facegateProfile(profileId)) })}>Đọc hồ sơ thiết bị</button>
          {profile && <p>Hồ sơ {profile.profile_id}: <strong>{profile.device_name || 'Chưa có tên'}</strong></p>}
          <label>Nhân viên VERA<select required value={username} onChange={event => { setUsername(event.target.value); setConfirmed(false) }}><option value="">Chọn nhân viên</option>{data.employees.map(item => <option key={item.username} value={item.username}>{item.username}{item.full_name ? ` · ${item.full_name}` : ''}</option>)}</select></label>
          <label>Mã nhân viên TimeSoft<input required maxLength={64} pattern="[A-Za-z0-9_-]+" value={code} onChange={event => { setCode(event.target.value); setConfirmed(false) }} /></label>
          <label><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />Tôi đã kiểm tra hồ sơ thiết bị và mã TimeSoft thuộc nhân viên đã chọn.</label>
          <button className="secondary-button" type="submit" disabled={!profile || !confirmed || !username || !code.trim()}>Lưu / xác nhận lại ánh xạ</button>
        </fieldset>
      </form>
      <div className="responsive-data-table"><table><thead><tr><th>ID hồ sơ</th><th>Tên trên máy</th><th>Nhân viên VERA</th><th>Mã TimeSoft</th><th>Xác nhận lúc</th></tr></thead><tbody>{data.mappings.map(item => <tr key={item.profile_id}><td>{item.profile_id}</td><td>{item.device_name}</td><td>{item.username}</td><td>{item.employee_code}</td><td>{formatVeraDateTime(item.confirmed_at, '—')}</td></tr>)}</tbody></table></div>
    </>}
    {message && <p role="status">{message}</p>}
  </details>
}

function CaptureImageButton({ record }) {
  const [imageUrl, setImageUrl] = useState('')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => () => { if (imageUrl) URL.revokeObjectURL(imageUrl) }, [imageUrl])

  const toggle = async () => {
    if (imageUrl) { setOpen(value => !value); return }
    setBusy(true); setError('')
    try {
      const blob = await veraApi.facegateCaptureImage(record.image_ref)
      if (!String(blob.type || '').toLowerCase().startsWith('image/')) throw new Error('Thiết bị không trả về dữ liệu ảnh.')
      setImageUrl(URL.createObjectURL(blob)); setOpen(true)
    } catch (cause) {
      setError(cause.message || 'Không tải được ảnh capture.')
    } finally { setBusy(false) }
  }

  return <div>
    <button className="secondary-button" type="button" disabled={busy} onClick={toggle}>{busy ? 'Đang tải ảnh…' : open ? 'Ẩn ảnh' : 'Xem ảnh'}</button>
    {error && <small role="alert">{error}</small>}
    {open && imageUrl && <div><img src={imageUrl} alt={`Ảnh capture sự kiện ${record.event_id}`} loading="lazy" style={{ display: 'block', width: 120, height: 160, objectFit: 'contain', marginTop: 8 }} /></div>}
  </div>
}

export default function CheckinHistoryPage() {
  const [filters, setFilters] = useState(initialCheckinFilters)
  const [records, setRecords] = useState(null)
  const [loadedQuery, setLoadedQuery] = useState(null)
  const [options, setOptions] = useState({ statuses: [], types: [] })
  const [truncated, setTruncated] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [dirty, setDirty] = useState(false)
  const formRef = useRef(null)
  const requestId = useRef(0)
  useEffect(() => () => { requestId.current += 1 }, [])
  const source = filters.source
  const change = patch => { setFilters(value => ({ ...value, ...patch })); setDirty(true); setError('') }
  const preset = value => change({ preset: value, ...checkinDateRange(value), event_date: '' })
  const load = async event => {
    event.preventDefault()
    if (!event.currentTarget.reportValidity()) return
    const invalid = checkinRangeError(filters)
    if (invalid) { setError(invalid); return }
    const id = ++requestId.current
    const query = checkinQuery(filters)
    setBusy(true); setError(''); setRecords(null)
    try {
      const response = await veraApi.checkinHistory(query)
      if (requestId.current !== id) return
      setRecords(response.records || [])
      setTruncated(Boolean(response.truncated))
      setOptions(response.options || { statuses: [], types: [] })
      setLoadedQuery(query); setDirty(false)
    } catch (cause) {
      if (requestId.current === id) setError(cause.message || 'Không tải được lịch sử checkin.')
    } finally { if (requestId.current === id) setBusy(false) }
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
    <div className="page-heading"><div><span className="eyebrow"><History size={16} /> FACE ID · CHẤM CÔNG</span><h1>LỊCH SỬ CHECKIN</h1><p>Tra cứu nhật ký thiết bị hoặc dữ liệu chấm công đã đồng bộ vào VERA.</p></div></div>
    <form ref={formRef} className="checkin-filters" onSubmit={load} onInput={() => setDirty(true)}>
      <fieldset disabled={busy || exporting}>
        <div className="checkin-filter-dates">
          <label>Thời gian<select value={filters.preset} onChange={event => preset(event.target.value)}>{CHECKIN_PRESETS.map(([id, label]) => <option value={id} key={id}>{label}</option>)}</select></label>
          <label>Từ ngày<VeraDateInput value={filters.date_from} max={filters.date_to} onChange={event => change({ date_from: event.target.value, preset: 'custom' })} required /></label>
          <label>Đến ngày<VeraDateInput value={filters.date_to} min={filters.date_from} onChange={event => change({ date_to: event.target.value, preset: 'custom' })} required /></label>
        </div>
        <div className="checkin-filter-details">
          <label>Nguồn dữ liệu<select value={source} onChange={event => { change({ source: event.target.value, ...EMPTY_CHECKIN_DETAILS }); setRecords(null); setOptions({ statuses: [], types: [] }) }}><option value="facegate_saved">FaceGate · Đã lưu trong VERA</option><option value="facegate">FaceGate · Trực tiếp từ máy</option><option value="capture">FaceGate · Capture Log</option><option value="timesoft">TimeSoft · Đã đồng bộ VERA</option></select></label>
          <label>Ngày cụ thể<VeraDateInput value={filters.event_date} min={filters.date_from} max={filters.date_to} onChange={event => change({ event_date: event.target.value })} /></label>
          <label>{source === 'facegate' ? 'Tên trên máy' : 'Tên / mã nhân viên'}<input type="search" disabled={source === 'capture'} maxLength={200} value={filters.employee} onChange={event => change({ employee: event.target.value })} placeholder={source === 'capture' ? 'Capture không có mã nhân viên' : 'Tìm tên hoặc mã'} /></label>
          <label>Mã sự kiện<input type="search" disabled={source === 'timesoft'} maxLength={64} value={filters.event_id} onChange={event => change({ event_id: event.target.value })} placeholder="Tìm mã sự kiện" /></label>
          <label>{source === 'timesoft' ? 'Trạng thái vào' : 'Trạng thái'}<select value={filters.status} onChange={event => change({ status: event.target.value })}><option value="">Tất cả</option>{options.statuses.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
          <label>{source === 'timesoft' ? 'Trạng thái ra' : 'Loại sự kiện'}<select value={filters.event_type} onChange={event => change({ event_type: event.target.value })}><option value="">Tất cả</option>{options.types.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
        </div>
        <div className="checkin-quick-dates">{CHECKIN_PRESETS.filter(([id]) => id !== 'custom').map(([id, label]) => <button key={id} type="button" className="secondary-button" aria-pressed={filters.preset === id} onClick={() => preset(id)}>{label}</button>)}<button type="button" className="secondary-button" onClick={() => change(EMPTY_CHECKIN_DETAILS)}>Xóa lọc chi tiết</button></div>
        <div className="device-actions">
          <button className="secondary-button" type="submit"><RefreshCw size={16} className={busy ? 'spin' : ''} />{busy ? 'Đang tải…' : 'Xem lịch sử'}</button>
          <button className="secondary-button" type="button" disabled={!records?.length || dirty || truncated} onClick={exportExcel}><Download size={16} />{exporting ? 'Đang xuất…' : 'Xuất Excel'}</button>
        </div>
      </fieldset>
      <small>Tra cứu tối đa 63 ngày/lượt. “Tất cả” lấy 63 ngày gần nhất. Danh sách trạng thái và loại sự kiện được cập nhật sau khi tải. Excel lấy dữ liệu mới nhất theo bộ lọc đã áp dụng.</small>
    </form>
    {dirty && records && <p role="status">Bộ lọc đã thay đổi. Bấm Xem lịch sử để cập nhật bảng và xuất Excel.</p>}
    {error && <p role="alert">{error}</p>}
    {records && <>
      <p>Dữ liệu đã tải: {formatVeraDate(loadedQuery.start)} – {formatVeraDate(loadedQuery.end)}.</p>
      {visible.length === 0 && <p role="status">Không có bản ghi phù hợp bộ lọc.</p>}
      {(source === 'facegate' || source === 'facegate_saved') ? <>
        <p>{visible.length} sự kiện FaceGate {source === 'facegate_saved' ? 'đã lưu trong VERA' : 'đọc trực tiếp từ máy'} trong kỳ. {source === 'facegate_saved' ? 'Ánh xạ hiển thị theo hồ sơ Admin đã xác nhận.' : 'Bấm Đối chiếu để kiểm tra hồ sơ đã ánh xạ.'} Chỉ dùng tra cứu, chưa dùng tính công/lương.</p>
        {source === 'facegate_saved' && <p role="status">Đã khớp: {visible.filter(item => item.mapping_status === 'reference_match').length} · Chưa ánh xạ: {visible.filter(item => item.mapping_status !== 'reference_match').length}. Mở “Ánh xạ hồ sơ FaceGate với nhân viên” bên dưới để xác nhận từng hồ sơ còn thiếu.</p>}
        {truncated && <p role="status">Kết quả đã chạm giới hạn truy vấn. Hãy thu hẹp khoảng ngày để xem và xuất đầy đủ dữ liệu.</p>}
        <div className="responsive-data-table"><table><thead><tr><th>Mã sự kiện</th><th>Thời điểm</th><th>Tên hiển thị trên máy</th><th>Mã trạng thái</th><th>Mã loại trên máy</th><th>Đối chiếu nhân viên</th></tr></thead><tbody>
          {visible.map(item => <tr key={`${item.event_id}-${item.occurred_at}`}>
            <td data-label="Mã sự kiện">{item.event_id}</td><td data-label="Thời điểm">{formatVeraDateTime(item.occurred_at, '—')}</td>
            <td data-label="Tên hiển thị trên máy">{item.device_name || '—'}</td><td data-label="Mã trạng thái">{item.status_code ?? '—'}</td><td data-label="Mã loại trên máy">{item.type_code ?? '—'}</td>
            <td data-label="Đối chiếu nhân viên">{source === 'facegate_saved' ? (item.mapping_status === 'reference_match' ? `${item.employee_name} · ${item.employee_code}` : 'Chưa ánh xạ') : <MappingCheck key={`${item.event_id}-${JSON.stringify(item.registration_ref)}`} record={item} />}</td>
          </tr>)}
        </tbody></table></div>
      </> : source === 'capture' ? <>
        <p>{visible.length} ảnh/sự kiện Capture Log trong kỳ. Máy không gửi mã nhân viên trong danh sách này; ảnh chỉ để Admin tra cứu, không ghép hồ sơ và không dùng tính công/lương. Ảnh chỉ tải khi bấm Xem ảnh và không lưu vào VERA.</p>
        {truncated && <p role="status">Kết quả đã chạm giới hạn truy vấn. Hãy thu hẹp khoảng ngày để xem và xuất đầy đủ dữ liệu.</p>}
        <div className="responsive-data-table"><table><thead><tr><th>Mã sự kiện</th><th>Thời điểm</th><th>Loại sự kiện</th><th>Trạng thái trên máy</th><th>Ảnh capture</th></tr></thead><tbody>
          {visible.map(item => <tr key={item.event_id}>
            <td data-label="Mã sự kiện">{item.event_id}</td><td data-label="Thời điểm">{formatVeraDateTime(item.occurred_at, '—')}</td>
            <td data-label="Loại sự kiện">{item.event_text || '—'}</td><td data-label="Trạng thái trên máy">{item.event_status || '—'}</td>
            <td data-label="Ảnh capture">{item.image_available ? <CaptureImageButton record={item} /> : 'Không có ảnh'}</td>
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
    <FacegateMappings />
  </section>
}
