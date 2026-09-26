import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { faceIdApi } from '../lib/staffSecurityApi'
import { IdentityImageEditor } from '../pages/EmployeeIdentityPanel'
import useDialogFocus from '../lib/useDialogFocus'
import { formatVeraDateTime } from '../lib/veraDate'
import './FacegateCaptureAssignment.css'

const searchKey = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').toLocaleLowerCase('vi')
function useBlobUrl(blob) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    if (!blob) { setUrl(''); return undefined }
    const next = URL.createObjectURL(blob)
    setUrl(next)
    return () => URL.revokeObjectURL(next)
  }, [blob])
  return url
}

export default function FacegateCaptureAssignment({ capture, onClose, onSaved }) {
  const [employees, setEmployees] = useState(null)
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [username, setUsername] = useState('')
  const [metadata, setMetadata] = useState(null)
  const [existingBlob, setExistingBlob] = useState(null)
  const [prepared, setPrepared] = useState(null)
  const [editing, setEditing] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [conflict, setConflict] = useState(false)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const requestId = useRef(0)
  const saving = useRef(false)
  const ref = useDialogFocus(() => { if (!saving.current && !editing) onClose() })
  const sourceUrl = useBlobUrl(prepared || capture.blob)
  const existingUrl = useBlobUrl(existingBlob)
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    faceIdApi.assignmentEmployees().then(result => { if (active) setEmployees(result.employees || []) })
      .catch(cause => { if (active) setError(cause.message || 'Không tải được danh sách nhân viên.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [reload])
  useEffect(() => () => { requestId.current += 1 }, [])

  const selectEmployee = async name => {
    const id = ++requestId.current
    setUsername(name); setMetadata(null); setExistingBlob(null); setConfirmed(false); setConflict(false); setError('')
    if (!name) { setBusy(false); return }
    setBusy(true)
    try {
      const value = await faceIdApi.metadata(name)
      if (requestId.current !== id) return
      if (!value.can_manage) throw Error('Bạn chưa có quyền thay ảnh FACE ID của nhân viên này.')
      if (value.photo) {
        const blob = await faceIdApi.identityBlob(name)
        if (requestId.current !== id) return
        setExistingBlob(blob)
      }
      setMetadata(value)
    } catch (cause) { if (requestId.current === id) setError(cause.message || 'Không kiểm tra được ảnh hiện có.') }
    finally { if (requestId.current === id) setBusy(false) }
  }
  const save = async () => {
    if (saving.current || busy || !metadata || !confirmed || conflict) return
    saving.current = true; setBusy(true); setError('')
    try {
      await faceIdApi.assignCapturePhoto(username, prepared || capture.blob, metadata.photo?.sha256 || null)
      window.dispatchEvent(new CustomEvent('vera-profile-updated'))
      onSaved(username)
    } catch (cause) {
      if (cause.status === 409) { setConflict(true); setConfirmed(false) }
      setError(cause.message || 'Chưa lưu được ảnh. Bạn có thể thử lại.')
    } finally { saving.current = false; setBusy(false) }
  }
  const choices = (employees || []).filter(row => searchKey(`${row.username} ${row.full_name}`).includes(searchKey(query)) || row.username === username)
  return createPortal(<div className="capture-assignment-backdrop">
    <section ref={ref} tabIndex={-1} className="capture-assignment-dialog" role={editing ? undefined : 'dialog'} aria-modal={editing ? undefined : true} aria-label="Chọn ảnh FACE ID cho nhân viên">
      {editing ? <IdentityImageEditor file={capture.blob} title={username || 'FACE ID'} mediaLabel="FACE ID" aspectRatio={null}
        confirmLabel="Dùng ảnh đã chỉnh" onCancel={() => setEditing(false)}
        onConfirm={async blob => { setPrepared(blob); setConfirmed(false); setEditing(false) }}/> : <>
        <header><h2>Chọn ảnh cho nhân viên</h2><button type="button" className="secondary-button" disabled={busy} onClick={onClose}>Đóng</button></header>
        <p>Ảnh Capture #{capture.record.event_id} · {formatVeraDateTime(capture.record.occurred_at)}</p>
        <p>Lưu vào mục ẢNH FACE ID trong hồ sơ nhân viên VERA. Chưa đăng ký ảnh lên máy FaceGate hoặc xác nhận ánh xạ chấm công.</p>
        {loading && <p role="status">Đang tải danh sách nhân viên…</p>}
        {!loading && !employees && <button type="button" className="secondary-button" onClick={() => setReload(n => n + 1)}>Tải lại danh sách nhân viên</button>}
        {employees && <><label>Tìm theo tên nhân viên<input type="search" value={query} disabled={busy} onChange={event => setQuery(event.target.value)} /></label>
          <label>Nhân viên VERA<select value={username} disabled={busy} onChange={event => selectEmployee(event.target.value)}>
            <option value="">Chọn nhân viên</option>{choices.map(row => <option key={row.username} value={row.username}>{row.username}{row.full_name ? ` · ${row.full_name}` : ''}</option>)}
          </select></label></>}
        <div className="capture-assignment-images"><figure><figcaption>{prepared ? 'Ảnh mới đã chỉnh' : 'Ảnh đang chọn'}</figcaption><img src={sourceUrl} alt="Ảnh Capture đã chọn" /></figure>
          {existingUrl && <figure><figcaption>Ảnh FACE ID hiện có</figcaption><img src={existingUrl} alt={`Ảnh FACE ID hiện có của ${username}`} /></figure>}</div>
        <button type="button" className="secondary-button" disabled={busy} onClick={() => setEditing(true)}>{prepared ? 'Chỉnh lại ảnh' : 'Cắt / xoay ảnh (tùy chọn)'}</button>
        {busy && <p role="status">{saving.current ? 'Đang lưu ảnh…' : 'Đang kiểm tra ảnh hiện có…'}</p>}
        {metadata && <p>{metadata.photo ? `Lưu sẽ thay ảnh FACE ID hiện có của ${username}.` : `${username} chưa có ảnh FACE ID.`}</p>}
        <label className="capture-assignment-confirm"><input type="checkbox" checked={confirmed} disabled={busy || !metadata || conflict} onChange={event => setConfirmed(event.target.checked)} />
          Tôi đã kiểm tra ảnh đúng nhân viên {username || 'đã chọn'}{metadata?.photo ? ' và đồng ý thay ảnh FACE ID hiện có' : ''}.</label>
        {error && <p role="alert">{error}</p>}
        {(conflict || (username && !metadata && !busy)) && <button type="button" className="secondary-button" disabled={busy} onClick={() => selectEmployee(username)}>Kiểm tra lại ảnh hiện có</button>}
        <footer><button type="button" className="secondary-button" disabled={busy} onClick={onClose}>Hủy</button>
          <button type="button" className="primary-button" disabled={busy || !metadata || !confirmed || conflict} onClick={save}>Lưu ảnh FACE ID</button></footer>
      </>}
    </section>
  </div>, document.body)
}
