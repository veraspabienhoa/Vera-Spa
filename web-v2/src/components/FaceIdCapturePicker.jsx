import { useEffect, useState } from 'react'
import { faceIdApi } from '../lib/staffSecurityApi'
import { formatVeraDateTime } from '../lib/veraDate'

export default function FaceIdCapturePicker({ username, day, busy, onSelect }) {
  const [revision, setRevision] = useState(0)
  const [data, setData] = useState(null)
  const [selected, setSelected] = useState(null)
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    setData(null); setSelected(null); setPreview(null); setError('')
    if (!day) return undefined
    setLoading(true)
    faceIdApi.captures(username, day).then(result => {
      if (!active) return
      const records = [...(result.records || [])].sort((a, b) =>
        String(b.occurred_at || '').localeCompare(String(a.occurred_at || '')) || Number(b.event_id) - Number(a.event_id))
      setData({ ...result, records }); setSelected(records[0] || null)
    }).catch(e => { if (active) setError(e.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [username, day, revision])
  useEffect(() => {
    let active = true, url = ''
    setPreview(null)
    if (!selected) return undefined
    setError('')
    faceIdApi.capture(username, day, selected.event_id).then(blob => {
      if (!active) return
      url = URL.createObjectURL(blob)
      setPreview({ blob, url, eventId: selected.event_id })
    }).catch(e => { if (active) setError(e.message) })
    return () => { active = false; if (url) URL.revokeObjectURL(url) }
  }, [username, day, selected])
  const ready = preview && preview.eventId === selected?.event_id
  return <div className="face-id-capture-picker">
    <button type="button" className="secondary-button compact" disabled={Boolean(busy) || loading || !day} onClick={() => setRevision(value => value + 1)}>Từ ảnh chụp trên FaceID · Làm mới</button>
    {loading && <p role="status">Đang tải ảnh chụp gần nhất…</p>}
    {error && <p role="status">Không tải được ảnh FaceID: {error}. Bấm Làm mới để thử lại.</p>}
    {data && <>
      <p>Ảnh của thiết bị trong ngày. Hãy kiểm tra đúng nhân viên trước khi lưu; hệ thống chưa xác minh danh tính trong ảnh.</p>
      {data.truncated && <p>Danh sách chưa đầy đủ do giới hạn đọc từ thiết bị. Ảnh gần nhất bên dưới là trong các bản ghi đã tải.</p>}
      {!data.records.length && <p>Không có ảnh chụp trong ngày đã chọn.</p>}
      {selected && <figure className="face-id-capture-preview">
        {ready ? <img src={preview.url} alt={`Ảnh chụp FaceID #${selected.event_id}`} /> : !error && <p role="status">Đang tải ảnh…</p>}
        <figcaption>{selected === data.records[0] ? 'Gần nhất · ' : ''}{formatVeraDateTime(selected.occurred_at)} · #{selected.event_id}</figcaption>
        <button type="button" className="primary-button compact" disabled={Boolean(busy) || !ready} onClick={() => onSelect(new File([preview.blob], 'FaceID.jpg', { type: preview.blob.type }))}>Chọn ảnh này</button>
      </figure>}
      <div className="face-id-capture-list" aria-label="Các ảnh chụp FaceID">
        {data.records.map(record => <button type="button" className="secondary-button compact" key={record.event_id} aria-pressed={record.event_id === selected?.event_id} disabled={Boolean(busy)} onClick={() => setSelected(record)}>{formatVeraDateTime(record.occurred_at)} · #{record.event_id}</button>)}
      </div>
    </>}
  </div>
}
