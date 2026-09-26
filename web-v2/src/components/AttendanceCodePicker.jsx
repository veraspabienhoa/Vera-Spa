import { useState } from 'react'
import { veraApi } from '../lib/api'

const statuses = { matched: 'Đã khớp', missing: 'Chưa có mã', conflict: 'Cần đối chiếu mã trùng' }
export default function AttendanceCodePicker({ onChoose }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const load = async action => {
    setBusy(true); setError('')
    try { setData(await action()) }
    catch (cause) { setError(cause.message || 'Không lấy được mã chấm công.') }
    finally { setBusy(false) }
  }
  const search = query.trim().toLocaleLowerCase('vi')
  const employees = (data?.employees || []).filter(row => [row.username, row.full_name, ...row.codes.flatMap(code => [code.attendance_code, code.employee_code])].join(' ').toLocaleLowerCase('vi').includes(search))
  return <section className="attendance-code-picker">
    <h3>Lấy mã chấm công để ánh xạ</h3>
    <div className="device-actions"><button type="button" className="secondary-button" disabled={busy} onClick={() => load(veraApi.attendanceCodes)}>Lấy mã TimeSoft đã đồng bộ</button>
      <label>Đối chiếu báo cáo TimeSoft (.xlsx)<input type="file" accept=".xlsx" disabled={busy} onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) load(() => veraApi.previewAttendanceCodes(file)) }}/></label></div>
    <p>Mã chấm công, mã nhân viên TimeSoft và ID hồ sơ FaceGate là các trường riêng. Chọn mã chỉ điền biểu mẫu; cần đối chiếu hồ sơ và bấm xác nhận để lưu ánh xạ.</p>
    {busy && <p role="status">Đang đối chiếu mã…</p>}{error && <p role="alert">{error}</p>}
    {data && <><p>{data.source} · Khớp {data.matched_count}/{data.total_count} nhân viên.</p>
      <label>Tìm nhân viên hoặc mã<input type="search" value={query} onChange={event => setQuery(event.target.value)}/></label>
      <div className="responsive-data-table"><table><thead><tr><th>Nhân viên VERA</th><th>Mã chấm công</th><th>Mã nhân viên TimeSoft</th><th>Đối chiếu</th></tr></thead><tbody>{employees.map(row => <tr key={row.username}><td>{row.username}{row.full_name && ` · ${row.full_name}`}</td><td>{[...new Set(row.codes.map(code => code.attendance_code))].join(', ') || '—'}</td><td>{[...new Set(row.codes.map(code => code.employee_code).filter(Boolean))].join(', ') || '—'}</td><td>{statuses[row.status]}{row.status === 'matched' && <button type="button" className="secondary-button compact" disabled={busy} onClick={() => onChoose(row.username, row.codes[0].attendance_code)}>Chọn mã</button>}</td></tr>)}</tbody></table></div>
      {!!data.unmatched?.length && <details><summary>{data.unmatched.length} mã chưa khớp chắc chắn với nhân viên VERA</summary>{data.unmatched.map((row, index) => <p key={index}>{row.name} · Mã chấm công {row.attendance_code} · Mã nhân viên {row.employee_code || '—'}</p>)}</details>}
    </>}
  </section>
}
