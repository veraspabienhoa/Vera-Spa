import { useCallback, useEffect, useState } from 'react'
import { veraApi } from '../lib/api'
import './KtvShiftSettingsPanel.css'

const labels = { letan: 'Lễ tân', locker: 'Locker', quanly: 'Quản lý', tapvu: 'Tạp vụ' }

export default function DepartmentShiftSettingsPanel() {
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
  return <section className="panel ktv-shift-settings">
    <h2>Cài đặt ca · Lễ tân / Locker / Quản lý / Tạp vụ</h2>
    <div className="ktv-shift-toolbar">{(data?.allowed_departments || []).map(key => <button className="secondary-button" type="button" key={key} disabled={busy} aria-pressed={department === key} onClick={() => {
      if (drafts && !window.confirm('Bỏ các thay đổi ca chưa lưu?')) return
      setDepartment(key); setDrafts(null); setError(''); setNotice('')
    }}>{labels[key]}</button>)}<button className="secondary-button" type="button" disabled={busy} onClick={() => { if (!drafts || window.confirm('Bỏ các thay đổi ca chưa lưu?')) void load() }}>Làm mới</button></div>
    {error && <p className="error-box" role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {busy && <p role="status">Đang xử lý…</p>}
    {department === 'quanly' ? <p>Quản lý dùng giờ làm theo từng ngày. Đặt giờ bắt đầu, giờ kết thúc và tăng ca tại Lịch làm việc → Quản lý.</p> : data && <>
      <h3>{labels[department]}</h3>
      {!drafts ? <><div className="ktv-shift-table-wrap"><table><thead><tr><th>Tên ca</th><th>Bắt đầu</th><th>Kết thúc</th></tr></thead><tbody>{rows.map(row => <tr key={row.shift_code}><td>{row.shift_code}</td><td>{row.start_time}</td><td>{row.end_time}</td></tr>)}</tbody></table></div>{data.can_edit && <button className="secondary-button" type="button" disabled={busy} onClick={() => setDrafts(rows)}>Tạo / sửa ca</button>}</> : <form onSubmit={save}>
        {drafts.map((row, index) => <div className="ktv-shift-form" key={index}>
          <label>Tên ca<input required maxLength={50} disabled={busy} value={row.shift_code} onChange={event => change(index, 'shift_code', event.target.value)} /></label>
          <label>Bắt đầu<input type="time" required disabled={busy} value={row.start_time} onChange={event => change(index, 'start_time', event.target.value)} /></label>
          <label>Kết thúc<input type="time" required disabled={busy} value={row.end_time} onChange={event => change(index, 'end_time', event.target.value)} /></label>
          <button className="secondary-button danger-button" type="button" disabled={busy || drafts.length <= 1} onClick={() => setDrafts(current => current.filter((_, i) => i !== index))}>Xóa ca</button>
        </div>)}
        <div className="ktv-shift-toolbar"><button className="secondary-button" type="button" disabled={busy || drafts.length >= 20} onClick={() => setDrafts(current => [...current, { shift_code: '', start_time: '09:00', end_time: '17:00' }])}>Thêm ca</button><button className="primary-button" disabled={busy || !drafts.length}>Lưu cấu hình ca</button><button className="secondary-button" type="button" disabled={busy} onClick={() => setDrafts(null)}>Hủy</button></div>
      </form>}
    </>}
  </section>
}
