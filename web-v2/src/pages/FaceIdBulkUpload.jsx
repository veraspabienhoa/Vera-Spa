import { useEffect, useRef, useState } from 'react'
import { faceIdApi } from '../lib/staffSecurityApi'
import { FACE_STATUS, prepareFacePhoto, uploadFaceBatch, validateBatchFiles } from '../lib/faceIdBatch'
import { IdentityImageEditor } from './EmployeeIdentityPanel'
import './FaceIdBulkUpload.css'

export default function FaceIdBulkUpload({ onBusyChange = () => {} }) {
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [editor, setEditor] = useState(null)
  const urls = useRef(new Set())
  const active = useRef(true)
  const gate = useRef(false)
  useEffect(() => { active.current = true; const tracked = urls.current; return () => { active.current = false; tracked.forEach(url => URL.revokeObjectURL(url)); tracked.clear() } }, [])
  const update = (id, patch) => setRows(current => current.map(row => row.id === id ? { ...row, ...patch } : row))
  const setWorking = value => { gate.current = value; setBusy(value); onBusyChange(value) }
  const preview = blob => { const url = URL.createObjectURL(blob); urls.current.add(url); return url }
  const selectFiles = async event => {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    if (!files.length || gate.current) return
    try { validateBatchFiles(files) } catch (error) { setNotice(error.message); return }
    setWorking(true); setNotice('Đang đối chiếu tên file và chuẩn bị ảnh…')
    try {
      const plan = await faceIdApi.batchPlan(files.map(file => file.name))
      const next = []
      for (let index = 0; index < files.length; index++) {
        if (!active.current) break
        const row = { ...plan.records[index], id: index, file: files[index], selected: false, state: 'ready' }
        if (row.status !== 'ready') row.message = FACE_STATUS[row.status] || 'Không thể ghép ảnh'
        else {
          try {
            row.blob = await prepareFacePhoto(row.file)
            if (!active.current) break
            row.url = preview(row.blob); row.selected = !row.existing_sha256
            row.message = row.existing_sha256 ? 'Đã có ảnh — chọn ô bên trái nếu muốn thay' : 'Sẵn sàng lưu'
          } catch (error) { row.message = error.message; row.state = 'prepare_error' }
        }
        next.push(row)
      }
      if (active.current) {
        const keep = new Set(next.map(row => row.url))
        urls.current.forEach(url => { if (!keep.has(url)) { URL.revokeObjectURL(url); urls.current.delete(url) } })
        setRows(next); setNotice('Kiểm tra tên và ảnh xem trước, rồi bấm lưu các ảnh đã chọn.')
      }
    } catch (error) { if (active.current) setNotice(error.message) }
    finally { if (active.current) setWorking(false) }
  }
  const save = async () => {
    if (gate.current) return
    setWorking(true); setNotice('Đang lưu lần lượt từng ảnh…')
    try {
      await uploadFaceBatch(rows, faceIdApi.uploadBatchPhoto, update, () => active.current)
      if (active.current) setNotice('Đã xử lý lô ảnh. Xem trạng thái từng dòng; ảnh đã lưu sẽ không được gửi lại.')
    } finally { if (active.current) setWorking(false) }
  }
  const chosen = rows.filter(row => row.selected && row.blob && row.state !== 'saved').length
  return <section className="face-batch">
    <h2 id="employee-profile-modal-title">TẢI ẢNH FACE ID HÀNG LOẠT</h2>
    <p>Tên file = <strong>Tên nhân viên / tài khoản VERA</strong>, không phải Họ tên đầy đủ. Ví dụ: <strong>Tuyết Nhi.jpg</strong>. Giữ đúng dấu tiếng Việt; không thêm số hoặc hậu tố.</p>
    <p>Tối đa 50 ảnh/lần, JPG/PNG/WebP. Ảnh được nén và thêm viền theo tỷ lệ 3:4 để giữ toàn bộ ảnh; bạn có thể cắt và xoay từng ảnh trước khi lưu.</p>
    <label className="secondary-button">Chọn nhiều ảnh<input aria-label="Chọn nhiều ảnh FACE ID" type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={busy || Boolean(editor)} onChange={selectFiles}/></label>
    <p role="status">{notice}</p>
    {rows.length > 0 && <>
      <div className="face-batch-table"><table><thead><tr><th>Lưu</th><th>Ảnh</th><th>Tên file</th><th>Tên nhân viên</th><th>Trạng thái</th><th>Chỉnh ảnh</th></tr></thead><tbody>
        {rows.map(row => <tr key={row.id}>
          <td><input type="checkbox" aria-label={`Lưu ${row.filename}`} checked={row.selected} disabled={busy || !row.blob || row.state === 'saved'} onChange={event => update(row.id, {selected: event.target.checked})}/></td>
          <td>{row.url && <img src={row.url} alt={`Ảnh FACE ID dự kiến cho ${row.username}`}/>}</td>
          <td>{row.filename}</td><td>{row.username || '—'}</td><td>{row.message}</td>
          <td>{row.status === 'ready' && row.state !== 'saved' && <button type="button" className="secondary-button compact" disabled={busy} onClick={() => setEditor(row)}>Crop / Xoay / Nén</button>}</td>
        </tr>)}
      </tbody></table></div>
      <button type="button" className="primary-button" disabled={busy || !chosen || Boolean(editor)} onClick={save}>{busy ? 'Đang xử lý…' : `Lưu ${chosen} ảnh đã chọn`}</button>
      <p>Đã lưu {rows.filter(row => row.state === 'saved').length}/{rows.length} ảnh. Ảnh trùng tên, không khớp hoặc chưa được chọn sẽ không được lưu.</p>
    </>}
    {editor && <IdentityImageEditor file={editor.file} title={`FACE ID · ${editor.username}`} mediaLabel="FACE ID" aspectRatio={3 / 4} confirmLabel="Áp dụng vào lô ảnh" onCancel={() => setEditor(null)} onConfirm={async blob => {
      if (editor.url) { URL.revokeObjectURL(editor.url); urls.current.delete(editor.url) }
      update(editor.id, {blob, url: preview(blob), state:'ready', message:'Đã chỉnh ảnh — sẵn sàng lưu', selected: editor.selected || !editor.existing_sha256})
      setEditor(null)
    }}/>} 
  </section>
}
