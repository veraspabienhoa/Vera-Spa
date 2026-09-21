import { useCallback, useEffect, useState } from 'react'
import { Plus, PencilLine, Trash2, RefreshCw, Save } from 'lucide-react'
import { veraApi } from '../lib/api'
import './KtvShiftSettingsPanel.css'

const EMPTY = { name: '', main_shift: 'Ca 1', start: '09:00', end: '17:00', fixed: false }

export default function KtvShiftSettingsPanel({ onChanged }) {
  const [data, setData] = useState(null)
  const [draft, setDraft] = useState(null)
  const [cycles, setCycles] = useState(null)
  const [cycleDraft, setCycleDraft] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const load = useCallback(async () => {
    setBusy(true); setError('')
    try { const [shiftData, cycleData] = await Promise.all([veraApi.ktvShifts(), veraApi.ktvCycles()]); setData(shiftData); setCycles(cycleData); setDraft(null); setCycleDraft(null) }
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
  const saveCycle = async (event) => {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try { setCycles(await veraApi.saveKtvCycle(cycleDraft.id, { name: cycleDraft.name, days: Number(cycleDraft.days), expected_revision: cycles.revision })); setCycleDraft(null); setNotice('Đã lưu chu kỳ.'); await onChanged?.() }
    catch (err) { setError(err.message || 'Không lưu được chu kỳ.') } finally { setBusy(false) }
  }
  const removeCycle = async (row) => {
    if (row.system || !window.confirm(`Xóa chu kỳ “${row.label}”?`)) return
    setBusy(true); setError(''); try { setCycles(await veraApi.deleteKtvCycle(row.id, cycles.revision)); setNotice('Đã xóa chu kỳ.'); await onChanged?.() }
    catch (err) { setError(err.message || 'Không xóa được chu kỳ.') } finally { setBusy(false) }
  }
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
    <h3>Chu kỳ làm việc</h3>
    <p><strong>Theo chu kỳ Tuần</strong>: đổi Ca 1 ↔ Ca 2 mỗi 7 ngày. <strong>Cố định</strong>: không tự đổi. Admin có thể tạo chu kỳ đổi ca mỗi N ngày.</p>
    {cycles?.can_manage && <div className="ktv-shift-toolbar"><button type="button" className="primary-button" disabled={busy} onClick={() => setCycleDraft({ name: '', days: 1 })}><Plus size={16}/> Thêm chu kỳ</button></div>}
    <div className="ktv-shift-table-wrap"><table><thead><tr><th>Chu kỳ</th><th>Đổi ca mỗi</th><th>Thao tác</th></tr></thead><tbody>{(cycles?.cycles || []).map(row => <tr key={row.id}><td>{row.label}</td><td>{row.days ? `${row.days} ngày` : 'Không đổi'}</td><td><div className="ktv-shift-toolbar">{cycles?.can_manage && !row.system && <><button type="button" className="secondary-button" onClick={() => setCycleDraft({ ...row })}><PencilLine size={15}/> Sửa</button><button type="button" className="secondary-button danger-button" onClick={() => removeCycle(row)}><Trash2 size={15}/> Xóa</button></>}</div></td></tr>)}</tbody></table></div>
    {cycleDraft && <form className="ktv-shift-form" onSubmit={saveCycle}><label>Tên chu kỳ<input required maxLength={80} value={cycleDraft.name} onChange={e => setCycleDraft(current => ({ ...current, name: e.target.value }))}/></label><label>Đổi ca mỗi (ngày)<input type="number" min="1" max="365" required value={cycleDraft.days} onChange={e => setCycleDraft(current => ({ ...current, days: e.target.value }))}/></label><div className="ktv-shift-toolbar"><button className="primary-button" type="submit"><Save size={16}/> Lưu chu kỳ</button><button className="secondary-button" type="button" onClick={() => setCycleDraft(null)}>Hủy</button></div></form>}
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
