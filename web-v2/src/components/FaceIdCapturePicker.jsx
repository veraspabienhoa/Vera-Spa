import { useEffect, useMemo, useState } from 'react'
import { faceIdApi } from '../lib/staffSecurityApi'
import { formatVeraDateTime } from '../lib/veraDate'

function CaptureImage({ username, day, record, busy, onSelect }) {
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true, url = ''
    setPreview(null); setError('')
    faceIdApi.capture(username, day, record.event_id).then(blob => {
      if (!active) return
      url = URL.createObjectURL(blob); setPreview({ blob, url })
    }).catch(e => { if (active) setError(e.message) })
    return () => { active = false; if (url) URL.revokeObjectURL(url) }
  }, [username, day, record.event_id])
  return <figure className="face-id-capture-preview">
    {preview ? <img src={preview.url} alt={`Ảnh chụp FaceID #${record.event_id}`} /> : <p role="status">{error || 'Đang tải ảnh…'}</p>}
    <figcaption>{formatVeraDateTime(record.occurred_at)}</figcaption>
    <button type="button" className="primary-button compact" disabled={Boolean(busy) || !preview} onClick={() => onSelect(new File([preview.blob], 'FaceID.jpg', { type: preview.blob.type }))}>Chọn ảnh này</button>
  </figure>
}

export default function FaceIdCapturePicker({ username, day, busy, onSelect, compact = false, dateControl }) {
  const [revision, setRevision] = useState(0)
  const [page, setPage] = useState(0)
  const [fromTime, setFromTime] = useState('')
  const [toTime, setToTime] = useState('')
  const pageSize = 4
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const invalidRange = Boolean(fromTime && toTime && fromTime > toTime)
  const hasTimeFilter = Boolean(fromTime || toTime)
  const records = useMemo(() => {
    if (invalidRange) return []
    if (!hasTimeFilter) return data?.records || []
    return (data?.records || []).filter(record => {
      // Match the Vietnam time shown on each photo, including the entire end minute.
      const time = formatVeraDateTime(record.occurred_at, '').slice(11, 16)
      return time && (!fromTime || time >= fromTime) && (!toTime || time <= toTime)
    })
  }, [data, fromTime, toTime, invalidRange, hasTimeFilter])
  useEffect(() => {
    let active = true
    setData(null); setPage(0); setError(''); setLoading(false)
    if (!day) return undefined
    setLoading(true)
    faceIdApi.captures(username, day).then(result => {
      if (!active) return
      const records = [...(result.records || [])].sort((a, b) =>
        String(b.occurred_at || '').localeCompare(String(a.occurred_at || '')) || Number(b.event_id) - Number(a.event_id))
      setData({ ...result, records })
    }).catch(e => { if (active) setError(e.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [username, day, revision])
  return <div className="face-id-capture-picker">
    <div className="face-id-capture-toolbar">
      {dateControl && <div className="face-id-capture-date"><span>Ngày</span>{dateControl}</div>}
      <label className="face-id-capture-time">Từ giờ<input type="time" step="60" aria-label="Ảnh FaceID · Từ giờ" value={fromTime} disabled={Boolean(busy)} aria-invalid={invalidRange} onChange={event => { setFromTime(event.target.value); setPage(0) }}/></label>
      <label className="face-id-capture-time">Đến giờ<input type="time" step="60" aria-label="Ảnh FaceID · Đến giờ" value={toTime} disabled={Boolean(busy)} aria-invalid={invalidRange} onChange={event => { setToTime(event.target.value); setPage(0) }}/></label>
      <div className="face-id-capture-filter-actions">
        {hasTimeFilter && <button type="button" className="secondary-button compact" disabled={Boolean(busy)} onClick={() => { setFromTime(''); setToTime(''); setPage(0) }}>Clear</button>}
        <button type="button" className="secondary-button compact" disabled={Boolean(busy) || loading || !day} onClick={() => setRevision(value => value + 1)}>{compact ? 'Làm mới' : 'Từ ảnh chụp trên FaceID · Làm mới'}</button>
      </div>
    </div>
    {invalidRange && <p role="alert">Giờ kết thúc phải bằng hoặc sau giờ bắt đầu trong ngày đã chọn.</p>}
    {loading && <p role="status">Đang tải danh sách ảnh chụp…</p>}
    {error && <p role="status">Không tải được ảnh FaceID: {error}. Bấm Làm mới để thử lại.</p>}
    {data && <>
      <p>Kiểm tra đúng nhân viên trước khi chọn ảnh; ảnh thiết bị chưa được xác minh danh tính.</p>
      {data.truncated && <p>Danh sách thiết bị trả về chưa đầy đủ; các trang chỉ gồm ảnh đã tải.</p>}
      {!invalidRange && !records.length && <p>{hasTimeFilter ? 'Không có ảnh chụp trong khoảng giờ đã chọn.' : 'Không có ảnh chụp trong ngày đã chọn.'}</p>}
      <div className="face-id-capture-gallery" aria-label="Ảnh chụp FaceID · 4 ảnh mỗi trang">
        {records.slice(page * pageSize, (page + 1) * pageSize).map(record => <CaptureImage key={`${revision}:${record.event_id}`} username={username} day={day} record={record} busy={busy} onSelect={onSelect}/>)}
      </div>
      {!!records.length && <nav aria-label="Phân trang ảnh FaceID" className="face-id-capture-pagination">
        <button type="button" className="secondary-button compact" disabled={Boolean(busy) || loading || page === 0} onClick={() => setPage(value => value - 1)}>Trang trước</button>
        <span role="status">Trang {page + 1}/{Math.ceil(records.length / pageSize)} · {records.length} ảnh</span>
        <button type="button" className="secondary-button compact" disabled={Boolean(busy) || loading || (page + 1) * pageSize >= records.length} onClick={() => setPage(value => value + 1)}>Trang sau</button>
      </nav>}
    </>}
  </div>
}
