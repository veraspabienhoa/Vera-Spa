import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import { useEffect, useState } from 'react'
import { veraApi } from '../lib/api'
import './HumanResourcesPage.css'

const modes = { monthly: 'Lương tháng', hourly: 'Lương giờ', tip: 'Tip' }
const empty = { code: '', name: '', salary_mode: 'hourly' }

export default function HumanResourcesPage({ user }) {
  usePageRefresh(() => isAdmin && load(), () => Boolean(busy || editing || JSON.stringify(assignments) !== JSON.stringify(Object.fromEntries((data?.employees || []).map(person => [person.username, person.department])))))
  const [data, setData] = useState(null)
  const [draft, setDraft] = useState(empty)
  const [editing, setEditing] = useState(false)
  const [search, setSearch] = useState('')
  const [departmentFilter, setDepartmentFilter] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [assignments, setAssignments] = useState({})
  const isAdmin = user?.role === 'admin'
  const load = async () => {
    const result = await veraApi.hr()
    setData(result)
    setAssignments(Object.fromEntries(result.employees.map(person => [person.username, person.department])))
  }
  useEffect(() => { if (isAdmin) load().catch(e => setError(e.message)) }, [isAdmin])
  const run = async (action, message) => {
    setBusy(true); setError(''); setNotice('')
    try { await action(); await load(); setNotice(message) }
    catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }
  if (!isAdmin) return <div className="error-box">Chỉ Admin được quản lý Nhân sự.</div>
  const departments = Object.entries(data?.departments || {}).filter(([, item]) => item.active)
  const people = (data?.employees || []).filter(person => (!departmentFilter || person.department === departmentFilter) && `${person.username} ${person.full_name}`.toLocaleLowerCase('vi').includes(search.trim().toLocaleLowerCase('vi')))
  const submit = event => {
    event.preventDefault()
    void run(async () => {
      await veraApi.saveHrDepartment({ ...draft, creating: !editing, revision: data.revision })
      setDraft(empty); setEditing(false)
    }, 'Đã lưu bộ phận. Hình thức lương được áp dụng khi tính bảng lương mới.')
  }
  return <div className="feature-page hr-page">
    <div data-ui-key="u-7fd60f444946" className="page-heading"><div><h1>NHÂN SỰ</h1><p>Quản lý bộ phận và hình thức lương độc lập với phân quyền tài khoản.</p></div><button data-ui-key="u-eca8c9b24429" data-ui-label-default="Làm mới" className="secondary-button" disabled={busy} onClick={() => run(load, 'Đã làm mới.')}><UiCustomText uiKey="u-eca8c9b24429">Làm mới</UiCustomText></button></div>
    <StableFeedback>{error && <div className="error-box" role="alert">{error}</div>}{notice && <div className="success-box" role="status">{notice}</div>}</StableFeedback>
    <section data-ui-key="u-f6aa77c86491" className="panel"><h2>Bộ phận & hình thức lương</h2>
      <p>Lương tháng: lương cơ bản theo 26 ngày công. Lương giờ: theo giờ làm và mức lương từng ca. Tip: dùng cách tính Lương KTV hiện tại, cùng các khoản phụ cấp và khấu trừ.</p>
      <form className="hr-department-form" onSubmit={submit}>
        <label>Mã bộ phận<input required pattern="[a-z][a-z0-9_]*" maxLength={50} disabled={busy || editing} placeholder="Ví dụ: thungan" value={draft.code} onChange={e => setDraft({ ...draft, code: e.target.value })}/></label>
        <label>Tên bộ phận<input required maxLength={100} disabled={busy} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })}/></label>
        <label>Hình thức lương<select disabled={busy} value={draft.salary_mode} onChange={e => setDraft({ ...draft, salary_mode: e.target.value })}>{Object.entries(modes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <button data-ui-key="u-ac237d09b39f" className="primary-button" disabled={busy || !data}>{editing ? 'Lưu thay đổi' : 'Thêm bộ phận'}</button>
        {editing && <button data-ui-key="u-ec758987c031" data-ui-label-default="Hủy sửa" className="secondary-button" type="button" disabled={busy} onClick={() => { setDraft(empty); setEditing(false) }}><UiCustomText uiKey="u-ec758987c031">Hủy sửa</UiCustomText></button>}
      </form>
      <div className="hr-departments">{departments.map(([code, item]) => <article key={code} className={`hr-department ${item.salary_mode}`}><div><strong>{item.name}</strong><small>{code} · {data.employees.filter(person => person.department === code).length} nhân viên</small></div><span>{modes[item.salary_mode]}</span><UiToolbar data-ui-key="u-be6e524a3d36" className="hr-actions"><button data-ui-key="u-33a7b99124f7" data-ui-label-default="Sửa" className="secondary-button" disabled={busy} onClick={() => { setDraft({ code, name: item.name, salary_mode: item.salary_mode }); setEditing(true) }}><UiCustomText uiKey="u-33a7b99124f7">Sửa</UiCustomText></button><button data-ui-key="u-6fdaecbc88cb" data-ui-label-default="Xóa" className="secondary-button danger-button" disabled={busy} onClick={() => { if (window.confirm(`Xóa bộ phận ${item.name}? Bộ phận phải không còn nhân viên.`)) void run(() => veraApi.deleteHrDepartment(code, data.revision), 'Đã xóa bộ phận.') }}><UiCustomText uiKey="u-6fdaecbc88cb">Xóa</UiCustomText></button></UiToolbar></article>)}</div>
    </section>
    <section data-ui-key="u-9017c3335ff8" className="panel"><h2>Phân bộ phận cho nhân viên</h2><p>Ví dụ: bộ phận Thu ngân, quyền Lễ tân. Thay bộ phận không thay đổi quyền tài khoản. Cấu hình mức tiền tại Cấu hình lương; bộ phận Tip dùng Lương KTV.</p>
      <UiToolbar data-ui-key="u-502fc7b27f2d" className="hr-filters"><label>Tìm nhân viên<input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Tên hoặc username…"/></label><label>Bộ phận<select value={departmentFilter} onChange={e => setDepartmentFilter(e.target.value)}><option value="">Tất cả</option>{departments.map(([code, item]) => <option key={code} value={code}>{item.name}</option>)}</select></label></UiToolbar>
      <div className="hr-people">{people.map(person => <article key={person.username}><div><strong>{person.full_name || person.username}</strong><small>{person.username} · Quyền: {person.role} · {person.employment_status}</small></div><label>Bộ phận<select aria-label={`Bộ phận ${person.username}`} disabled={busy} value={assignments[person.username] || ''} onChange={e => setAssignments({ ...assignments, [person.username]: e.target.value })}><option value="" disabled>Chọn bộ phận</option>{!departments.some(([code]) => code === person.department) && <option value={person.department} disabled>Chưa phân bộ phận</option>}{departments.map(([code, item]) => <option key={code} value={code}>{item.name} · {modes[item.salary_mode]}</option>)}</select></label><button data-ui-key="u-02e98dec3eb7" data-ui-label-default="Lưu" className="primary-button" disabled={busy || assignments[person.username] === person.department || !assignments[person.username]} onClick={() => run(() => veraApi.assignHrDepartment(person.username, assignments[person.username], data.revision), 'Đã chuyển bộ phận; quyền tài khoản được giữ nguyên.')}><UiCustomText uiKey="u-02e98dec3eb7">Lưu</UiCustomText></button></article>)}</div>
      {!people.length && <p>Không có nhân viên phù hợp.</p>}
    </section>
  </div>
}
