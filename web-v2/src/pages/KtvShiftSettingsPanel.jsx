import { useCallback, useEffect, useState } from 'react'
import { Plus, PencilLine, Trash2, RefreshCw, Save } from 'lucide-react'
import { veraApi } from '../lib/api'
import './KtvShiftSettingsPanel.css'

const EMPTY = { name: '', main_shift: 'Ca 1', start: '09:00', end: '17:00', fixed: false }

export default function KtvShiftSettingsPanel({ onChanged }) {
  const [data, setData] = useState(null)
  const [draft, setDraft] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const load = useCallback(async () => {
    setBusy(true); setError('')
    try { setData(await veraApi.ktvShifts()); setDraft(null) }
    catch (err) { setError(err.message || 'Không tải được danh mục ca.') }
    finally { setBusy(false) }
  }, [])
  useEffect(() => { void load() }, [load])
  const save = async (event) => {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      setData(await veraApi.saveKtvShift(draft.id, { ...draft, expected_revision: data.revision }))
      setDraft(null); setNotice('Đã lưu ca làm việc.'); await onChanged?.()
    } catch (err) { setError(err.message || 'Không lưu được ca.') }
    finally { setBusy(false) }
  }
  const remove = async (row) => {
    if (!window.confirm(`Xóa ca “${row.name}”?`)) return
    setBusy(true); setError(''); setNotice('')
    try {
      setData(await veraApi.deleteKtvShift(row.id, data.revision))
      setDraft(null); setNotice('Đã xóa ca.'); await onChanged?.()
    } catch (err) { setError(err.message || 'Không xóa được ca.') }
    finally { setBusy(false) }
  }
  const update = (field, value) => setDraft(current => ({ ...current, [field]: value }))
  return <details className="panel ktv-shift-settings">
    <summary>Cài đặt ca · Leader / Nhân viên</summary>
    <p>Tên ca được đặt riêng, ví dụ “Cố định Ca 1”. Ca chính xác định Ca 1 hoặc Ca 2 trên bảng tua.</p>
    <div className="ktv-shift-toolbar">
      <button type="button" className="secondary-button" disabled={busy} onClick={load}><RefreshCw size={16}/> Làm mới</button>
      {data?.permissions?.create && <button type="button" className="primary-button" disabled={busy} onClick={() => { setDraft({ ...EMPTY }); setError(''); setNotice('') }}><Plus size={16}/> Thêm ca</button>}
    </div>
    {error && <p className="error-box" role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <div className="ktv-shift-table-wrap"><table><thead><tr><th>Tên ca</th><th>Ca chính</th><th>Bắt đầu</th><th>Kết thúc</th><th>Cố định</th><th>Thao tác</th></tr></thead><tbody>
      {(data?.shifts || []).map(row => <tr key={row.id}><td>{row.name}</td><td>{row.main_shift || 'Chưa chọn'}</td><td>{row.start}</td><td>{row.end}</td><td>{row.fixed ? 'Có' : 'Không'}</td><td><div className="ktv-shift-toolbar">
        {data.permissions.edit && <button type="button" className="secondary-button" disabled={busy} aria-label={`Sửa ca ${row.name}`} onClick={() => { setDraft({ ...row, main_shift: row.main_shift || 'Ca 1' }); setError(''); setNotice('') }}><PencilLine size={15}/> Sửa</button>}
        {data.permissions.delete && <button type="button" className="secondary-button danger-button" disabled={busy} aria-label={`Xóa ca ${row.name}`} onClick={() => remove(row)}><Trash2 size={15}/> Xóa</button>}
      </div></td></tr>)}
      {data && !data.shifts.length && <tr><td colSpan="6">Chưa có ca. Bấm Thêm ca để tạo.</td></tr>}
    </tbody></table></div>
    {draft && <form className="ktv-shift-form" onSubmit={save}>
      <label>Tên ca<input required maxLength={100} disabled={busy} value={draft.name} placeholder="Cố định Ca 1" onChange={e => update('name', e.target.value)}/></label>
      <label>Ca chính<select required disabled={busy} value={draft.main_shift} onChange={e => update('main_shift', e.target.value)}><option>Ca 1</option><option>Ca 2</option></select></label>
      <label>Giờ bắt đầu<input type="time" required disabled={busy} value={draft.start} onChange={e => update('start', e.target.value)}/></label>
      <label>Giờ kết thúc<input type="time" required disabled={busy} value={draft.end} onChange={e => update('end', e.target.value)}/></label>
      <label className="ktv-shift-fixed"><input type="checkbox" disabled={busy} checked={draft.fixed} onChange={e => update('fixed', e.target.checked)}/> Ca cố định (không đổi)</label>
      <div className="ktv-shift-toolbar"><button className="primary-button" disabled={busy} type="submit"><Save size={16}/> Lưu ca</button><button className="secondary-button" disabled={busy} type="button" onClick={() => setDraft(null)}>Hủy</button></div>
    </form>}
  </details>
}
