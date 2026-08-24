import {
  BriefcaseBusiness, Download, FilePenLine, LoaderCircle, LockKeyhole, Plus,
  RefreshCw, Save, Search, Trash2, Upload, UserCheck, UserRoundCog, UsersRound,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { isApiConfigured, veraApi } from '../lib/api'

const ROLE_LABELS = {
  admin: 'Admin', quanly: 'Quản lý', letan: 'Lễ tân', leader: 'Leader',
  nhanvien: 'Nhân viên', locker: 'Locker', tapvu: 'Tạp vụ',
}

const EMPTY_CREATE = {
  username: '', password: '', role: 'nhanvien', full_name: '', birth_date: '',
  phone: '', email: '', address: '', bank_account: '', bank_name: '', employment_start_date: '',
}

const PROFILE_FIELDS = [
  ['full_name', 'Họ và tên đầy đủ'], ['birth_date', 'Ngày sinh'],
  ['employment_start_date', 'Ngày bắt đầu làm'], ['phone', 'Điện thoại'],
  ['email', 'Email'], ['address', 'Địa chỉ'], ['bank_account', 'Số tài khoản ngân hàng'],
  ['bank_name', 'Tên ngân hàng'], ['monthly_generated', 'Phát sinh tháng'],
  ['monthly_leave', 'Có phép tháng'], ['annual_leave', 'Phép năm'],
]

function toInputDate(value) {
  const match = String(value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/)
  return match ? `${match[3]}-${match[2]}-${match[1]}` : String(value || '')
}

function datePayload(value) {
  if (!value) return ''
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value
}

function searchKey(value) {
  return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').trim().toLocaleLowerCase('vi').replace(/\s+/g, ' ')
}

function departmentForRole(role) {
  if (role === 'nhanvien' || role === 'leader') return 'Nhân viên + Leader'
  return { letan: 'Lễ tân', quanly: 'Quản lý', locker: 'Locker', tapvu: 'Tạp vụ' }[role] || 'Khác'
}

function rowDraft(employee) {
  return {
    role: employee.role,
    employment_status: employee.employment_status,
    work_shift: employee.work_shift || '',
    shift_start_date: toInputDate(employee.shift_start_date),
    rotation_cycle: employee.rotation_cycle || '',
    login_locked: Boolean(employee.login_locked),
  }
}

function changedPayload(employee, draft) {
  const payload = {}
  if (draft.role !== employee.role) payload.role = draft.role
  if (draft.employment_status !== employee.employment_status) payload.employment_status = draft.employment_status
  if (draft.work_shift !== (employee.work_shift || '')) payload.work_shift = draft.work_shift
  if (datePayload(draft.shift_start_date) !== (employee.shift_start_date || '')) payload.shift_start_date = datePayload(draft.shift_start_date)
  if (draft.rotation_cycle !== (employee.rotation_cycle || '')) payload.rotation_cycle = draft.rotation_cycle
  if (Boolean(draft.login_locked) !== Boolean(employee.login_locked)) payload.login_locked = Boolean(draft.login_locked)
  return payload
}

function Notice({ notice, onClose }) {
  if (!notice) return null
  return (
    <div className={`staff-notice ${notice.type}`} role="status">
      <strong>{notice.type === 'success' ? 'THÀNH CÔNG' : 'KHÔNG THÀNH CÔNG'}</strong>
      <span>{notice.message}</span>
      <button type="button" onClick={onClose} aria-label="Đóng thông báo">×</button>
    </div>
  )
}

export default function EmployeePage({ user }) {
  const [data, setData] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [selected, setSelected] = useState([])
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [shiftFilter, setShiftFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)
  const [addOpen, setAddOpen] = useState(false)
  const [createForm, setCreateForm] = useState(EMPTY_CREATE)
  const [profileUser, setProfileUser] = useState('')
  const [profileDraft, setProfileDraft] = useState({})
  const importRef = useRef(null)

  const load = async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const result = await veraApi.staff()
      setData(result)
      setDrafts(Object.fromEntries((result.employees || []).map((employee) => [employee.username, rowDraft(employee)])))
      setSelected([])
      setNotice(null)
    } catch (error) {
      setNotice({ type: 'error', message: error.message || 'Không tải được danh sách nhân viên.' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const visible = useMemo(() => {
    const employees = data?.employees || []
    const needle = searchKey(search)
    const exact = needle ? employees.filter((employee) => [employee.username, employee.full_name].some((value) => searchKey(value) === needle)) : []
    const namePool = exact.length ? new Set(exact.map((employee) => employee.username)) : null
    return employees.filter((employee) => {
      const matchesName = !needle || (namePool ? namePool.has(employee.username) : searchKey(`${employee.username} ${employee.full_name}`).includes(needle))
      return matchesName && (!roleFilter || employee.role === roleFilter)
        && (!statusFilter || employee.employment_status === statusFilter)
        && (!shiftFilter || employee.work_shift === shiftFilter)
    })
  }, [data, roleFilter, search, shiftFilter, statusFilter])

  const shiftOptions = useMemo(() => Array.from(new Set([
    ...(data?.employees || []).map((employee) => employee.work_shift),
    ...Object.values(data?.shifts_by_department || {}).flat(),
  ].filter(Boolean))).sort((left, right) => left.localeCompare(right, 'vi')), [data])

  const permissions = data?.permissions || {}
  const isAdmin = user?.role === 'admin'
  const manageableRoles = new Set(data?.role_options || [])
  const canManage = (employee) => isAdmin || manageableRoles.has(employee.role)
  const canSaveRows = permissions.employee_edit_save || permissions.employment_status_edit
    || permissions.shift_assignment_edit || permissions.account_lock_edit

  const setDraft = (username, field, value) => {
    setDrafts((current) => ({
      ...current,
      [username]: { ...(current[username] || {}), [field]: value },
    }))
  }

  const dirtyRows = (data?.employees || []).filter((employee) => {
    const draft = drafts[employee.username]
    return draft && Object.keys(changedPayload(employee, draft)).length > 0
  })

  const shiftsFor = (employee) => {
    const role = drafts[employee.username]?.role || employee.role
    const items = data?.shifts_by_department?.[departmentForRole(role)] || []
    return Array.from(new Set([employee.work_shift, ...items].filter(Boolean)))
  }

  const run = async (key, callback) => {
    setBusy(key)
    setNotice(null)
    try {
      await callback()
    } catch (error) {
      setNotice({ type: 'error', message: error.message || 'Thao tác không thành công.' })
    } finally {
      setBusy('')
    }
  }

  const saveRows = () => run('save', async () => {
    if (!dirtyRows.length) throw new Error('Chưa có thay đổi cần lưu.')
    for (const employee of dirtyRows) {
      await veraApi.updateStaff(employee.username, changedPayload(employee, drafts[employee.username]))
    }
    const count = dirtyRows.length
    await load(true)
    setNotice({ type: 'success', message: `Đã lưu thay đổi cho ${count} nhân viên.` })
  })

  const deleteSelected = () => run('delete', async () => {
    if (!selected.length) throw new Error('Chưa chọn nhân viên cần xóa.')
    if (!window.confirm(`Xóa ${selected.length} nhân viên đã chọn? Lịch sử nghỉ vẫn được giữ nguyên.`)) return
    const result = await veraApi.deleteStaff(selected)
    await load(true)
    setNotice({ type: 'success', message: result.message })
  })

  const deleteOne = (employee) => run(`delete-${employee.username}`, async () => {
    if (!window.confirm(`Xóa nhân viên ${employee.full_name || employee.username}? Lịch sử nghỉ vẫn được giữ nguyên.`)) return
    const result = await veraApi.deleteStaff([employee.username])
    await load(true)
    setNotice({ type: 'success', message: result.message })
  })

  const createStaff = (event) => {
    event.preventDefault()
    run('create', async () => {
      const payload = {
        ...createForm,
        birth_date: datePayload(createForm.birth_date),
        employment_start_date: datePayload(createForm.employment_start_date),
      }
      const result = await veraApi.createStaff(payload)
      setCreateForm(EMPTY_CREATE)
      setAddOpen(false)
      await load(true)
      setNotice({ type: 'success', message: result.message })
    })
  }

  const openProfile = (employee) => {
    setProfileUser(employee.username)
    setProfileDraft(Object.fromEntries(PROFILE_FIELDS.map(([field]) => [
      field,
      field.includes('date') ? toInputDate(employee[field]) : employee[field] ?? '',
    ])))
  }

  const saveProfile = () => run('profile', async () => {
    const payload = { ...profileDraft }
    payload.birth_date = datePayload(payload.birth_date)
    payload.employment_start_date = datePayload(payload.employment_start_date)
    for (const field of ['monthly_generated', 'monthly_leave', 'annual_leave']) payload[field] = Number(payload[field] || 0)
    const result = await veraApi.updateStaff(profileUser, payload)
    setProfileUser('')
    await load(true)
    setNotice({ type: 'success', message: result.message })
  })

  const importExcel = (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      setNotice({ type: 'error', message: 'Chỉ chấp nhận file Excel .xlsx.' })
      return
    }
    if (!window.confirm(`Import file ${file.name}? Hệ thống sẽ kiểm tra toàn bộ file trước khi ghi.`)) return
    run('import', async () => {
      const result = await veraApi.importStaffExcel(file)
      await load(true)
      setNotice({ type: 'success', message: result.message })
    })
  }

  const toggleSelected = (username) => {
    setSelected((current) => current.includes(username)
      ? current.filter((item) => item !== username)
      : [...current, username])
  }

  if (!isApiConfigured) return <div className="setup-note">Mục Nhân viên cần Python API V2 để ghi an toàn.</div>

  return (
    <div className="staff-page">
      <div className="page-heading-row staff-heading">
        <div>
          <div className="eyebrow"><UserRoundCog size={14} /> VẬN HÀNH NHÂN SỰ</div>
          <h1 className="page-title">Nhân viên</h1>
          <p className="page-subtitle">Danh sách, hồ sơ, trạng thái làm việc và phân ca trong một màn hình.</p>
        </div>
        <button className="secondary-button" onClick={() => load()} disabled={loading || Boolean(busy)}>
          <RefreshCw size={17} className={loading ? 'spin' : ''} /> Làm mới
        </button>
      </div>

      <Notice notice={notice} onClose={() => setNotice(null)} />

      <div className="metric-grid staff-metrics">
        {[
          ['Tổng nhân viên', data?.summary?.total || 0, UsersRound],
          ['Đang làm việc', data?.summary?.active || 0, UserCheck],
          ['Tạm thời nghỉ', data?.summary?.temporary || 0, BriefcaseBusiness],
          ['Đã nghỉ việc', data?.summary?.left || 0, LockKeyhole],
        ].map(([label, value, Icon]) => (
          <div className="metric-card" key={label}><div className="metric-icon"><Icon size={21} /></div><div><span>{label}</span><strong>{value}</strong></div></div>
        ))}
      </div>

      <section className="panel staff-control-panel">
        <div className="staff-toolbar">
          <div className="staff-search"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Tìm tên nhân viên hoặc họ tên" /></div>
          <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)} aria-label="Lọc phân quyền">
            <option value="">Tất cả phân quyền</option>
            {Object.entries(ROLE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="Lọc trạng thái">
            <option value="">Tất cả trạng thái</option>
            {(data?.status_options || []).map((status) => <option key={status}>{status}</option>)}
          </select>
          <select value={shiftFilter} onChange={(event) => setShiftFilter(event.target.value)} aria-label="Lọc ca làm việc">
            <option value="">Tất cả ca làm việc</option>
            {shiftOptions.map((shift) => <option key={shift}>{shift}</option>)}
          </select>
        </div>
        <div className="staff-actionbar">
          {permissions.employee_add && <button className="primary-button" onClick={() => setAddOpen((value) => !value)}><Plus size={17} /> Thêm nhân viên</button>}
          {permissions.staff_export && <button className="secondary-button" disabled={busy === 'export'} onClick={() => run('export', () => veraApi.exportStaffExcel(search, roleFilter, statusFilter, shiftFilter))}><Download size={17} /> Export Excel</button>}
          {permissions.staff_import && <>
            <input ref={importRef} className="staff-file-input" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={importExcel} />
            <button className="secondary-button" disabled={busy === 'import'} onClick={() => importRef.current?.click()}><Upload size={17} /> Import Excel</button>
          </>}
          {canSaveRows && <button className="secondary-button" disabled={busy === 'save' || !dirtyRows.length} onClick={saveRows}><Save size={17} /> Lưu thay đổi ({dirtyRows.length})</button>}
          {isAdmin && permissions.employee_delete && <button className="danger-button" disabled={busy === 'delete' || !selected.length} onClick={deleteSelected}><Trash2 size={17} /> Xóa đã chọn ({selected.length})</button>}
        </div>
      </section>

      {addOpen && <section className="panel staff-form-panel">
        <div className="panel-title-row"><div><h2>THÊM NHÂN VIÊN</h2><p>Mật khẩu chỉ được nhập khi tạo mới và không xuất ra Excel.</p></div></div>
        <form className="staff-form-grid" onSubmit={createStaff}>
          <label>Tên nhân viên<input required value={createForm.username} onChange={(event) => setCreateForm({ ...createForm, username: event.target.value })} /></label>
          <label>Mật khẩu ban đầu (tối thiểu 8 ký tự)<input required minLength={8} type="password" autoComplete="new-password" value={createForm.password} onChange={(event) => setCreateForm({ ...createForm, password: event.target.value })} /></label>
          <label>Phân quyền<select value={createForm.role} onChange={(event) => setCreateForm({ ...createForm, role: event.target.value })}>{(data?.role_options || []).map((role) => <option key={role} value={role}>{ROLE_LABELS[role] || role}</option>)}</select></label>
          <label>Họ và tên đầy đủ<input required value={createForm.full_name} onChange={(event) => setCreateForm({ ...createForm, full_name: event.target.value })} /></label>
          <label>Ngày bắt đầu làm<input type="date" value={createForm.employment_start_date} onChange={(event) => setCreateForm({ ...createForm, employment_start_date: event.target.value })} /></label>
          <label>Ngày sinh<input type="date" value={createForm.birth_date} onChange={(event) => setCreateForm({ ...createForm, birth_date: event.target.value })} /></label>
          <label>Điện thoại<input value={createForm.phone} onChange={(event) => setCreateForm({ ...createForm, phone: event.target.value })} /></label>
          <label>Email<input type="email" value={createForm.email} onChange={(event) => setCreateForm({ ...createForm, email: event.target.value })} /></label>
          <label className="span-2">Địa chỉ<input value={createForm.address} onChange={(event) => setCreateForm({ ...createForm, address: event.target.value })} /></label>
          <label>Số tài khoản ngân hàng<input value={createForm.bank_account} onChange={(event) => setCreateForm({ ...createForm, bank_account: event.target.value })} /></label>
          <label>Tên ngân hàng<input value={createForm.bank_name} onChange={(event) => setCreateForm({ ...createForm, bank_name: event.target.value })} /></label>
          <div className="staff-form-actions span-2"><button type="button" className="secondary-button" onClick={() => setAddOpen(false)}>Hủy</button><button className="primary-button" disabled={busy === 'create'}>{busy === 'create' ? <LoaderCircle size={17} className="spin" /> : <Plus size={17} />} Thêm nhân viên</button></div>
        </form>
      </section>}

      {profileUser && <section className="panel staff-form-panel">
        <div className="panel-title-row"><div><h2>SỬA HỒ SƠ · {profileUser}</h2><p>Cập nhật thông tin cá nhân và hạn mức phép.</p></div></div>
        <div className="staff-form-grid">
          {PROFILE_FIELDS.map(([field, label]) => {
            const isDate = field.includes('date')
            const isNumber = ['monthly_generated', 'monthly_leave', 'annual_leave'].includes(field)
            return <label key={field}>{label}<input type={isDate ? 'date' : isNumber ? 'number' : 'text'} min={isNumber ? '0' : undefined} step={isNumber ? '0.5' : undefined} value={profileDraft[field] ?? ''} onChange={(event) => setProfileDraft({ ...profileDraft, [field]: event.target.value })} /></label>
          })}
          <div className="staff-form-actions span-2"><button className="secondary-button" onClick={() => setProfileUser('')}>Hủy</button><button className="primary-button" disabled={busy === 'profile'} onClick={saveProfile}><Save size={17} /> Lưu hồ sơ</button></div>
        </div>
      </section>}

      <section className="panel staff-list-panel">
        <div className="panel-title-row"><div><h2>DANH SÁCH NHÂN VIÊN</h2><p>{visible.length} nhân viên phù hợp bộ lọc.</p></div></div>
        {loading ? <div className="empty-cell"><LoaderCircle className="spin" /> Đang tải danh sách…</div> : <>
          <div className="staff-desktop-table table-wrap">
            <table className="staff-table">
              <thead><tr><th>Chọn</th><th>Nhân viên</th><th>Phân quyền</th><th>Trạng thái</th><th>Ca làm việc</th><th>Ngày bắt đầu ca</th><th>Chu kỳ</th><th>Khóa</th><th>Hồ sơ</th><th>Admin</th></tr></thead>
              <tbody>{visible.map((employee) => {
                const draft = drafts[employee.username] || rowDraft(employee)
                const editable = canManage(employee)
                return <tr key={employee.username} className={employee.employment_status === 'Đã nghỉ việc' ? 'staff-left-row' : ''}>
                  <td className="center"><input type="checkbox" checked={selected.includes(employee.username)} disabled={!editable || !permissions.employee_delete} onChange={() => toggleSelected(employee.username)} aria-label={`Chọn ${employee.username}`} /></td>
                  <td><strong>{employee.username}</strong><small>{employee.full_name || '—'}</small></td>
                  <td><select value={draft.role} disabled={!editable || !permissions.employee_edit_save} onChange={(event) => setDraft(employee.username, 'role', event.target.value)}>{Array.from(new Set([employee.role, ...(data?.role_options || [])])).map((role) => <option key={role} value={role}>{ROLE_LABELS[role] || role}</option>)}</select></td>
                  <td><select value={draft.employment_status} disabled={!editable || !permissions.employment_status_edit} onChange={(event) => setDraft(employee.username, 'employment_status', event.target.value)}>{(data?.status_options || []).map((status) => <option key={status}>{status}</option>)}</select></td>
                  <td><select value={draft.work_shift} disabled={!editable || !permissions.shift_assignment_edit} onChange={(event) => setDraft(employee.username, 'work_shift', event.target.value)}><option value="">Chưa chia ca</option>{shiftsFor(employee).map((shift) => <option key={shift}>{shift}</option>)}</select></td>
                  <td><input type="date" value={draft.shift_start_date} disabled={!editable || !permissions.shift_assignment_edit} onChange={(event) => setDraft(employee.username, 'shift_start_date', event.target.value)} /></td>
                  <td><select value={draft.rotation_cycle} disabled={!editable || !permissions.shift_assignment_edit} onChange={(event) => setDraft(employee.username, 'rotation_cycle', event.target.value)}><option value="">Chưa chọn</option>{(data?.cycle_options || []).map((cycle) => <option key={cycle}>{cycle}</option>)}</select></td>
                  <td className="center"><input type="checkbox" checked={draft.login_locked} disabled={!editable || !permissions.account_lock_edit} onChange={(event) => setDraft(employee.username, 'login_locked', event.target.checked)} aria-label={`Khóa ${employee.username}`} /></td>
                  <td><button className="text-button staff-edit-button" disabled={!editable || !permissions.employee_edit_save} onClick={() => openProfile(employee)}><FilePenLine size={15} /> Sửa</button></td>
                  <td>{isAdmin && permissions.employee_delete && <button className="danger-button compact" disabled={Boolean(busy)} onClick={() => deleteOne(employee)}><Trash2 size={14} /> Xóa</button>}</td>
                </tr>
              })}</tbody>
            </table>
          </div>

          <div className="staff-mobile-list">{visible.map((employee) => {
            const draft = drafts[employee.username] || rowDraft(employee)
            const editable = canManage(employee)
            return <article className={`staff-mobile-card ${employee.employment_status === 'Đã nghỉ việc' ? 'left' : ''}`} key={employee.username}>
              <div className="staff-mobile-head"><label><input type="checkbox" checked={selected.includes(employee.username)} disabled={!isAdmin || !editable || !permissions.employee_delete} onChange={() => toggleSelected(employee.username)} /> <span><strong>{employee.username}</strong><small>{employee.full_name || '—'}</small></span></label><div className="list-actions"><button className="text-button" disabled={!editable || !permissions.employee_edit_save} onClick={() => openProfile(employee)}><FilePenLine size={15} /> Hồ sơ</button>{isAdmin && permissions.employee_delete && <button className="danger-button compact" disabled={Boolean(busy)} onClick={() => deleteOne(employee)}><Trash2 size={14} /> Xóa</button>}</div></div>
              <div className="staff-mobile-fields">
                <label>Phân quyền<select value={draft.role} disabled={!editable || !permissions.employee_edit_save} onChange={(event) => setDraft(employee.username, 'role', event.target.value)}>{Array.from(new Set([employee.role, ...(data?.role_options || [])])).map((role) => <option key={role} value={role}>{ROLE_LABELS[role] || role}</option>)}</select></label>
                <label>Trạng thái<select value={draft.employment_status} disabled={!editable || !permissions.employment_status_edit} onChange={(event) => setDraft(employee.username, 'employment_status', event.target.value)}>{(data?.status_options || []).map((status) => <option key={status}>{status}</option>)}</select></label>
                <label className="span-2">Ca làm việc<select value={draft.work_shift} disabled={!editable || !permissions.shift_assignment_edit} onChange={(event) => setDraft(employee.username, 'work_shift', event.target.value)}><option value="">Chưa chia ca</option>{shiftsFor(employee).map((shift) => <option key={shift}>{shift}</option>)}</select></label>
                <label>Ngày bắt đầu ca<input type="date" value={draft.shift_start_date} disabled={!editable || !permissions.shift_assignment_edit} onChange={(event) => setDraft(employee.username, 'shift_start_date', event.target.value)} /></label>
                <label>Chu kỳ<select value={draft.rotation_cycle} disabled={!editable || !permissions.shift_assignment_edit} onChange={(event) => setDraft(employee.username, 'rotation_cycle', event.target.value)}><option value="">Chưa chọn</option>{(data?.cycle_options || []).map((cycle) => <option key={cycle}>{cycle}</option>)}</select></label>
                <label className="staff-lock-field"><input type="checkbox" checked={draft.login_locked} disabled={!editable || !permissions.account_lock_edit} onChange={(event) => setDraft(employee.username, 'login_locked', event.target.checked)} /> Khóa đăng nhập</label>
              </div>
            </article>
          })}</div>
          {!visible.length && <div className="empty-cell">Không có nhân viên phù hợp bộ lọc.</div>}
        </>}
      </section>
    </div>
  )
}
