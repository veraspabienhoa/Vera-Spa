import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import { useCallback, useEffect, useState } from 'react'
import { veraApi } from '../lib/api'
import './KtvShiftSettingsPanel.css'

const labels = { letan: 'Lễ tân', locker: 'Locker', quanly: 'Quản lý', tapvu: 'Tạp vụ' }

export default function DepartmentShiftSettingsPanel() {
  usePageRefresh(() => load(), () => Boolean(busy || drafts))
  const [data, setData] = useState(null)
  const [department, setDepartment] = useState('')
  const [drafts, setDrafts] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const load = useCallback(async () => {
    setBusy(true); setError('')
    try {
      const result = await veraApi.scheduleShiftSettings()
      setData(result); setDrafts(null)
      setDepartment(current => result.allowed_departments.includes(current) ? current : result.allowed_departments[0] || '')
    } catch (err) { setError(err.message || 'Không tải được cài đặt ca.') }
    finally { setBusy(false) }
  }, [])
  useEffect(() => { void load() }, [load])
  const rows = Object.entries(data?.shift_definitions?.[department] || {}).map(([shift_code, spec]) => ({ shift_code, start_time: spec.start, end_time: spec.end }))
  const change = (index, key, value) => setDrafts(current => current.map((row, i) => i === index ? { ...row, [key]: value } : row))
  const save = async event => {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      const result = await veraApi.saveScheduleShifts({ department, shifts: drafts.map(row => ({ ...row, shift_code: row.shift_code.trim() })) })
      await load(); setNotice(result.message || 'Đã lưu cấu hình ca.')
    } catch (err) { setError(err.message || 'Không lưu được cấu hình ca.') }
    finally { setBusy(false) }
  }
  return <section data-ui-key="u-4f517c915cf7" className="panel ktv-shift-settings">
    <h2>Cài đặt ca · Lễ tân / Locker / Quản lý / Tạp vụ</h2>
    <UiToolbar data-ui-key="u-af74537d90cb" className="ktv-shift-toolbar">{(data?.allowed_departments || []).map(key => <button data-ui-key="u-e3c7e72e1b15" className="secondary-button" type="button" key={key} disabled={busy} aria-pressed={department === key} onClick={() => {
      if (drafts && !window.confirm('Bỏ các thay đổi ca chưa lưu?')) return
      setDepartment(key); setDrafts(null); setError(''); setNotice('')
    }}>{labels[key]}</button>)}<button data-ui-key="u-8f161594a3de" data-ui-label-default="Làm mới" className="secondary-button" type="button" disabled={busy} onClick={() => { if (!drafts || window.confirm('Bỏ các thay đổi ca chưa lưu?')) void load() }}><UiCustomText uiKey="u-8f161594a3de">Làm mới</UiCustomText></button></UiToolbar>
    <StableFeedback>{error && <p className="error-box" role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}</StableFeedback>
    {busy && <p role="status">Đang xử lý…</p>}
    {department === 'quanly' ? <p>Quản lý dùng giờ làm theo từng ngày. Đặt giờ bắt đầu, giờ kết thúc và tăng ca tại Lịch làm việc → Quản lý.</p> : data && <>
      <h3>{labels[department]}</h3>
      {!drafts ? <><div className="ktv-shift-table-wrap"><table data-ui-key="u-f4124be10a1c"><thead><tr><th data-ui-key="u-8af701baf998" data-ui-label-default="Tên ca"><UiCustomText uiKey="u-8af701baf998">Tên ca</UiCustomText></th><th data-ui-key="u-48878fa070e7" data-ui-label-default="Bắt đầu"><UiCustomText uiKey="u-48878fa070e7">Bắt đầu</UiCustomText></th><th data-ui-key="u-9e6b8fb032a7" data-ui-label-default="Kết thúc"><UiCustomText uiKey="u-9e6b8fb032a7">Kết thúc</UiCustomText></th></tr></thead><tbody>{rows.map(row => <tr key={row.shift_code}><td>{row.shift_code}</td><td>{row.start_time}</td><td>{row.end_time}</td></tr>)}</tbody></table></div>{data.can_edit && <button data-ui-key="u-de0f52732339" data-ui-label-default="Tạo / sửa ca" className="secondary-button" type="button" disabled={busy} onClick={() => setDrafts(rows)}><UiCustomText uiKey="u-de0f52732339">Tạo / sửa ca</UiCustomText></button>}</> : <form onSubmit={save}>
        {drafts.map((row, index) => <div className="ktv-shift-form" key={index}>
          <label>Tên ca<input required maxLength={50} disabled={busy} value={row.shift_code} onChange={event => change(index, 'shift_code', event.target.value)} /></label>
          <label>Bắt đầu<input type="time" required disabled={busy} value={row.start_time} onChange={event => change(index, 'start_time', event.target.value)} /></label>
          <label>Kết thúc<input type="time" required disabled={busy} value={row.end_time} onChange={event => change(index, 'end_time', event.target.value)} /></label>
          <button data-ui-key="u-a10320243aff" data-ui-label-default="Xóa ca" className="secondary-button danger-button" type="button" disabled={busy || drafts.length <= 1} onClick={() => setDrafts(current => current.filter((_, i) => i !== index))}><UiCustomText uiKey="u-a10320243aff">Xóa ca</UiCustomText></button>
        </div>)}
        <UiToolbar data-ui-key="u-9ed06c41fef7" className="ktv-shift-toolbar"><button data-ui-key="u-4fb844c2ed9c" data-ui-label-default="Thêm ca" className="secondary-button" type="button" disabled={busy || drafts.length >= 20} onClick={() => setDrafts(current => [...current, { shift_code: '', start_time: '09:00', end_time: '17:00' }])}><UiCustomText uiKey="u-4fb844c2ed9c">Thêm ca</UiCustomText></button><button data-ui-key="u-ecece275030a" data-ui-label-default="Lưu cấu hình ca" className="primary-button" disabled={busy || !drafts.length}><UiCustomText uiKey="u-ecece275030a">Lưu cấu hình ca</UiCustomText></button><button data-ui-key="u-09237c220e01" data-ui-label-default="Hủy" className="secondary-button" type="button" disabled={busy} onClick={() => setDrafts(null)}><UiCustomText uiKey="u-09237c220e01">Hủy</UiCustomText></button></UiToolbar>
      </form>}
    </>}
  </section>
}
