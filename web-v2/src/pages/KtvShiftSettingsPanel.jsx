import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import { useCallback, useEffect, useState } from 'react'
import { Plus, PencilLine, Trash2, RefreshCw, Save } from 'lucide-react'
import { veraApi } from '../lib/api'
import './KtvShiftSettingsPanel.css'

const EMPTY = { name: '', main_shift: 'Ca 1', start: '09:00', end: '17:00', fixed: false }

export default function KtvShiftSettingsPanel({ onChanged }) {
  usePageRefresh(() => load(), () => Boolean(busy || draft || cycleDraft))
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
    <UiToolbar data-ui-key="u-7e100304754e" className="ktv-shift-toolbar">
      <button data-ui-key="u-ee5fac9c6358" data-ui-label-default="Làm mới" type="button" className="secondary-button" disabled={busy} onClick={load}><RefreshCw size={16}/><UiCustomText uiKey="u-ee5fac9c6358"> Làm mới</UiCustomText></button>
      {data?.permissions?.create && <button data-ui-key="u-7574b5707176" data-ui-label-default="Thêm ca" type="button" className="primary-button" disabled={busy} onClick={() => { setDraft({ ...EMPTY }); setError(''); setNotice('') }}><Plus size={16}/><UiCustomText uiKey="u-7574b5707176"> Thêm ca</UiCustomText></button>}
    </UiToolbar>
    <StableFeedback>{error && <p className="error-box" role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}</StableFeedback>
    <div className="ktv-shift-table-wrap"><table data-ui-key="u-1d53041d87e4"><thead><tr><th data-ui-key="u-c2a9cddbdbbd" data-ui-label-default="Tên ca"><UiCustomText uiKey="u-c2a9cddbdbbd">Tên ca</UiCustomText></th><th data-ui-key="u-452fbb35f75c" data-ui-label-default="Ca chính"><UiCustomText uiKey="u-452fbb35f75c">Ca chính</UiCustomText></th><th data-ui-key="u-84e4e06dbbbf" data-ui-label-default="Bắt đầu"><UiCustomText uiKey="u-84e4e06dbbbf">Bắt đầu</UiCustomText></th><th data-ui-key="u-fbb590a52a7a" data-ui-label-default="Kết thúc"><UiCustomText uiKey="u-fbb590a52a7a">Kết thúc</UiCustomText></th><th data-ui-key="u-ed9378a74ce0" data-ui-label-default="Cố định"><UiCustomText uiKey="u-ed9378a74ce0">Cố định</UiCustomText></th><th data-ui-key="u-a3e002589a6b" data-ui-label-default="Thao tác"><UiCustomText uiKey="u-a3e002589a6b">Thao tác</UiCustomText></th></tr></thead><tbody>
      {(data?.shifts || []).map(row => <tr key={row.id}><td>{row.name}</td><td>{row.main_shift || 'Chưa chọn'}</td><td>{row.start}</td><td>{row.end}</td><td>{row.fixed ? 'Có' : 'Không'}</td><td><UiToolbar data-ui-key="u-cfc5c3b1a061" className="ktv-shift-toolbar">
        {data.permissions.edit && <button data-ui-key="u-df30c4862522" data-ui-label-default="Sửa" type="button" className="secondary-button" disabled={busy} aria-label={`Sửa ca ${row.name}`} onClick={() => { setDraft({ ...row, main_shift: row.main_shift || 'Ca 1' }); setError(''); setNotice('') }}><PencilLine size={15}/><UiCustomText uiKey="u-df30c4862522"> Sửa</UiCustomText></button>}
        {data.permissions.delete && <button data-ui-key="u-028e956dab20" data-ui-label-default="Xóa" type="button" className="secondary-button danger-button" disabled={busy} aria-label={`Xóa ca ${row.name}`} onClick={() => remove(row)}><Trash2 size={15}/><UiCustomText uiKey="u-028e956dab20"> Xóa</UiCustomText></button>}
      </UiToolbar></td></tr>)}
      {data && !data.shifts.length && <tr><td colSpan="6">Chưa có ca. Bấm Thêm ca để tạo.</td></tr>}
    </tbody></table></div>
    <h3>Chu kỳ làm việc</h3>
    <p><strong>Theo chu kỳ Tuần</strong>: đổi Ca 1 ↔ Ca 2 mỗi 7 ngày. <strong>Cố định</strong>: không tự đổi. Admin có thể tạo chu kỳ đổi ca mỗi N ngày.</p>
    {cycles?.can_manage && <UiToolbar data-ui-key="u-5180d392face" className="ktv-shift-toolbar"><button data-ui-key="u-e12ac15a9554" data-ui-label-default="Thêm chu kỳ" type="button" className="primary-button" disabled={busy} onClick={() => setCycleDraft({ name: '', days: 1 })}><Plus size={16}/><UiCustomText uiKey="u-e12ac15a9554"> Thêm chu kỳ</UiCustomText></button></UiToolbar>}
    <div className="ktv-shift-table-wrap"><table data-ui-key="u-7aaba08dcd28"><thead><tr><th data-ui-key="u-711f343fb73e" data-ui-label-default="Chu kỳ"><UiCustomText uiKey="u-711f343fb73e">Chu kỳ</UiCustomText></th><th data-ui-key="u-e2ba81e132e1" data-ui-label-default="Đổi ca mỗi"><UiCustomText uiKey="u-e2ba81e132e1">Đổi ca mỗi</UiCustomText></th><th data-ui-key="u-dfec75f3ff19" data-ui-label-default="Thao tác"><UiCustomText uiKey="u-dfec75f3ff19">Thao tác</UiCustomText></th></tr></thead><tbody>{(cycles?.cycles || []).map(row => <tr key={row.id}><td>{row.label}</td><td>{row.days ? `${row.days} ngày` : 'Không đổi'}</td><td><UiToolbar data-ui-key="u-b4716151e1dc" className="ktv-shift-toolbar">{cycles?.can_manage && !row.system && <><button data-ui-key="u-155dd729ca63" data-ui-label-default="Sửa" type="button" className="secondary-button" onClick={() => setCycleDraft({ ...row })}><PencilLine size={15}/><UiCustomText uiKey="u-155dd729ca63"> Sửa</UiCustomText></button><button data-ui-key="u-2386e426178e" data-ui-label-default="Xóa" type="button" className="secondary-button danger-button" onClick={() => removeCycle(row)}><Trash2 size={15}/><UiCustomText uiKey="u-2386e426178e"> Xóa</UiCustomText></button></>}</UiToolbar></td></tr>)}</tbody></table></div>
    {cycleDraft && <form className="ktv-shift-form" onSubmit={saveCycle}><label>Tên chu kỳ<input required maxLength={80} value={cycleDraft.name} onChange={e => setCycleDraft(current => ({ ...current, name: e.target.value }))}/></label><label>Đổi ca mỗi (ngày)<input type="number" min="1" max="365" required value={cycleDraft.days} onChange={e => setCycleDraft(current => ({ ...current, days: e.target.value }))}/></label><UiToolbar data-ui-key="u-48545566b4ab" className="ktv-shift-toolbar"><button data-ui-key="u-ba44e916c797" data-ui-label-default="Lưu chu kỳ" className="primary-button" type="submit"><Save size={16}/><UiCustomText uiKey="u-ba44e916c797"> Lưu chu kỳ</UiCustomText></button><button data-ui-key="u-b7daa1d42082" data-ui-label-default="Hủy" className="secondary-button" type="button" onClick={() => setCycleDraft(null)}><UiCustomText uiKey="u-b7daa1d42082">Hủy</UiCustomText></button></UiToolbar></form>}
    {draft && <form className="ktv-shift-form" onSubmit={save}>
      <label>Tên ca<input required maxLength={100} disabled={busy} value={draft.name} placeholder="Cố định Ca 1" onChange={e => update('name', e.target.value)}/></label>
      <label>Ca chính<select required disabled={busy} value={draft.main_shift} onChange={e => update('main_shift', e.target.value)}><option>Ca 1</option><option>Ca 2</option></select></label>
      <label>Giờ bắt đầu<input type="time" required disabled={busy} value={draft.start} onChange={e => update('start', e.target.value)}/></label>
      <label>Giờ kết thúc<input type="time" required disabled={busy} value={draft.end} onChange={e => update('end', e.target.value)}/></label>
      <label className="ktv-shift-fixed"><input type="checkbox" disabled={busy} checked={draft.fixed} onChange={e => update('fixed', e.target.checked)}/> Ca cố định (không đổi)</label>
      <UiToolbar data-ui-key="u-af6d8b5db56f" className="ktv-shift-toolbar"><button data-ui-key="u-3b5ac15a5117" data-ui-label-default="Lưu ca" className="primary-button" disabled={busy} type="submit"><Save size={16}/><UiCustomText uiKey="u-3b5ac15a5117"> Lưu ca</UiCustomText></button><button data-ui-key="u-b0a0c46da08e" data-ui-label-default="Hủy" className="secondary-button" disabled={busy} type="button" onClick={() => setDraft(null)}><UiCustomText uiKey="u-b0a0c46da08e">Hủy</UiCustomText></button></UiToolbar>
    </form>}
  </details>
}
