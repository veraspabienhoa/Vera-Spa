import {
  BriefcaseBusiness, Download, Eye, EyeOff, FileDown, FilePenLine, LoaderCircle, LockKeyhole,
  PencilLine, Plus, RefreshCw, Save, Search, Trash2, UserCheck, UserRoundCog, UsersRound,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { isApiConfigured, veraApi } from '../lib/api'
import { getCurrentSession } from '../lib/supabase'
import EmployeeIdentityPanel, { EmployeeMediaDraftPanel } from './EmployeeIdentityPanel'
import { staffSecurityApi } from '../lib/staffSecurityApi'

const API_BASE = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

const ROLE_LABELS = {
  admin: 'Admin', giamdoc: 'Giám đốc', quanly: 'Quản lý', letan: 'Lễ tân', leader: 'Leader',
  nhanvien: 'Nhân viên', locker: 'Locker', tapvu: 'Tạp vụ',
}

const EMPTY_CREATE = {
  username: '', password: '', role: 'nhanvien', full_name: '', birth_date: '',
  gender: '', ethnicity: '', phone: '', email: '', province: '', district: '', ward: '', address_detail: '',
  address: '', bank_account: '', bank_name: '', employment_start_date: '',
  cccd_number: '', cccd_issue_date: '', cccd_issue_place: '',
}

const PROFILE_SECTIONS = [
  { title: 'Thông tin cá nhân', fields: [
    ['full_name', 'Họ và tên đầy đủ'], ['birth_date', 'Ngày sinh'], ['gender', 'Giới tính'], ['ethnicity', 'Dân tộc'],
  ] },
  { title: 'Thông tin định danh', fields: [
    ['cccd_number', 'Số Căn cước'], ['cccd_issue_date', 'Ngày cấp'], ['cccd_issue_place', 'Nơi cấp'],
  ] },
  { title: 'Thông tin liên hệ & Địa chỉ', fields: [
    ['phone', 'Điện thoại'], ['email', 'Email'], ['province', 'Tỉnh/Thành phố'], ['district', 'Quận/Huyện'],
    ['ward', 'Phường/Xã'], ['address_detail', 'Địa chỉ cụ thể (Số nhà, tên đường...)'],
  ] },
  { title: 'Thông tin thanh toán/Ngân hàng', fields: [
    ['bank_name', 'Tên ngân hàng'], ['bank_account', 'Số tài khoản ngân hàng'],
  ] },
  { title: 'Thông tin việc làm', fields: [
    ['employment_start_date', 'Ngày bắt đầu làm'], ['employment_end_date', 'Ngày nghỉ việc'],
  ] },
]
const PROFILE_FIELDS = PROFILE_SECTIONS.flatMap((section) => section.fields)

const REQUIRED_PROFILE_FIELDS = [
  ['full_name', 'Họ và tên đầy đủ'], ['birth_date', 'Ngày sinh'], ['gender', 'Giới tính'], ['ethnicity', 'Dân tộc'],
  ['phone', 'Điện thoại'], ['email', 'Email'], ['province', 'Tỉnh/Thành phố'], ['district', 'Quận/Huyện'],
  ['ward', 'Phường/Xã'], ['address_detail', 'Địa chỉ cụ thể'],
  ['bank_account', 'Số tài khoản ngân hàng'], ['bank_name', 'Tên ngân hàng'],
  ['cccd_number', 'Số CCCD'], ['cccd_issue_date', 'Ngày cấp CCCD'], ['cccd_issue_place', 'Nơi cấp CCCD'],
]

function missingEmployeeProfileFields(employee) {
  return REQUIRED_PROFILE_FIELDS
    .filter(([field]) => !String(employee?.[field] ?? '').trim())
    .map(([, label]) => label)
}

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
  return { giamdoc: 'Giám đốc', letan: 'Lễ tân', quanly: 'Quản lý', locker: 'Locker', tapvu: 'Tạp vụ' }[role] || 'Khác'
}

async function renameSystemNameRequest(username, systemName) {
  if (!API_BASE) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const response = await fetch(`${API_BASE}/v2/staff/${encodeURIComponent(username)}/system-name`, {
    method: 'PATCH',
    headers,
    body: JSON.stringify({ system_name: systemName }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || payload?.message || 'Không đổi được Tên hệ thống.')
  return payload
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
  const [visibilityFilter, setVisibilityFilter] = useState('visible')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)
  const [addOpen, setAddOpen] = useState(false)
  const [createForm, setCreateForm] = useState(EMPTY_CREATE)
  const [createMedia, setCreateMedia] = useState({ portrait: null, front: null, back: null })
  const [profileUser, setProfileUser] = useState('')
  const [profileDraft, setProfileDraft] = useState({})
  const [profileScrollRequest, setProfileScrollRequest] = useState(0)
  const profileSectionRef = useRef(null)

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

  useEffect(() => {
    if (!profileScrollRequest) return undefined
    const frame = window.requestAnimationFrame(() => {
      profileSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [profileScrollRequest])

  useEffect(() => {
    const applyExtracted = (event) => {
      if (!profileUser || event.detail?.username !== profileUser) return
      const fields = event.detail?.fields || {}
      setProfileDraft((current) => ({
        ...current,
        ...fields,
        cccd_issue_date: fields.cccd_issue_date ? toInputDate(fields.cccd_issue_date) : current.cccd_issue_date,
      }))
    }
    window.addEventListener('vera-identity-extracted', applyExtracted)
    return () => window.removeEventListener('vera-identity-extracted', applyExtracted)
  }, [profileUser])

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
        && (visibilityFilter === 'all' || (visibilityFilter === 'hidden' ? employee.profile_hidden : !employee.profile_hidden))
    })
  }, [data, roleFilter, search, shiftFilter, statusFilter, visibilityFilter])
  const shiftOptions = useMemo(() => Array.from(new Set([
    ...(data?.employees || []).map((employee) => employee.work_shift),
    ...Object.values(data?.shifts_by_department || {}).flat(),
  ].filter(Boolean))).sort((left, right) => left.localeCompare(right, 'vi')), [data])

  const incompleteVisible = useMemo(
    () => visible.filter((employee) => missingEmployeeProfileFields(employee).length).length,
    [visible],
  )
  const hiddenEmployees = useMemo(
    () => (data?.employees || []).filter((employee) => employee.profile_hidden),
    [data],
  )

  const permissions = data?.permissions || {}
  const isAdmin = user?.role === 'admin'
  const manageableRoles = new Set(data?.role_options || [])
  const canManage = (employee) => isAdmin || manageableRoles.has(employee.role)
  const canSaveRows = permissions.employee_edit_save || permissions.employment_status_edit
    || permissions.shift_assignment_edit || permissions.account_lock_edit
  const canSelectRows = isAdmin && (permissions.staff_export || permissions.employee_delete || permissions.employees_visibility_manage)

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

  const renameSystemName = (employee) => run(`rename-${employee.username}`, async () => {
    if (!isAdmin) return
    const next = window.prompt(
      `Tên hệ thống mới cho ${employee.username}:\nTên đăng nhập cũng sẽ đổi theo tên này.`,
      employee.username,
    )
    if (next === null) return
    const clean = next.trim().replace(/\s+/g, ' ')
    if (!clean || clean === employee.username) return
    if (!window.confirm(`Đổi Tên hệ thống và Tên đăng nhập:\n${employee.username} → ${clean}\n\nDữ liệu lịch nghỉ, chấm công, lịch làm việc và thông báo sẽ được chuyển theo tài khoản mới.`)) return
    const result = await renameSystemNameRequest(employee.username, clean)
    if (profileUser === employee.username) setProfileUser('')
    await load(true)
    setNotice({ type: 'success', message: result.message || `Đã đổi Tên hệ thống/Tên đăng nhập thành ${clean}.` })
  })

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
      await staffSecurityApi.validateDraftIdentity(createMedia, createForm.full_name, createForm.cccd_number)
      const payload = {
        ...createForm,
        birth_date: datePayload(createForm.birth_date),
        employment_start_date: datePayload(createForm.employment_start_date),
        cccd_issue_date: datePayload(createForm.cccd_issue_date),
      }
      const result = await veraApi.createStaff(payload)
      const mediaWarnings = []
      for (const side of ['portrait', 'front', 'back']) {
        if (!createMedia[side]) continue
        try {
          await staffSecurityApi.uploadIdentity(payload.username, side, createMedia[side])
        } catch (mediaError) {
          mediaWarnings.push(`${side === 'portrait' ? 'ảnh nhân viên' : side === 'front' ? 'mặt trước CCCD' : 'mặt sau CCCD'}: ${mediaError.message}`)
        }
      }
      setCreateForm(EMPTY_CREATE)
      setCreateMedia({ portrait: null, front: null, back: null })
      setAddOpen(false)
      await load(true)
      setNotice({
        type: mediaWarnings.length ? 'error' : 'success',
        message: mediaWarnings.length
          ? `${result.message} Chưa tải được ${mediaWarnings.join('; ')}. Có thể bổ sung trong Hồ sơ nhân viên.`
          : result.message,
      })
    })
  }

  const openProfile = (employee) => {
    setProfileUser(employee.username)
    setProfileDraft(Object.fromEntries(PROFILE_FIELDS.map(([field]) => [
      field,
      field.includes('date') ? toInputDate(employee[field]) : employee[field] ?? '',
    ])))
    setProfileScrollRequest((request) => request + 1)
  }

  const changeEmployeeSearch = (value) => {
    setSearch(value)
    setProfileUser('')
    setProfileDraft({})
  }

  const saveProfile = () => run('profile', async () => {
    const payload = { ...profileDraft }
    payload.birth_date = datePayload(payload.birth_date)
    payload.employment_start_date = datePayload(payload.employment_start_date)
    payload.employment_end_date = datePayload(payload.employment_end_date)
    payload.cccd_issue_date = datePayload(payload.cccd_issue_date)
    const result = await veraApi.updateStaff(profileUser, payload)
    setProfileUser('')
    await load(true)
    setNotice({ type: 'success', message: result.message })
  })

  const toggleSelected = (username) => {
    setSelected((current) => current.includes(username)
      ? current.filter((item) => item !== username)
      : [...current, username])
  }

  const selectAllVisible = () => setSelected(visible.filter(canManage).map((employee) => employee.username))
  const clearSelected = () => setSelected([])

  const exportSelectedProfiles = () => run('profiles-pdf', async () => {
    if (!selected.length) throw new Error('Chưa chọn nhân viên cần xuất hồ sơ PDF.')
    await staffSecurityApi.exportProfilesPdf(selected)
    setNotice({ type: 'success', message: `Đã xuất ${selected.length} hồ sơ nhân viên trong một file PDF.` })
  })

  const setEmployeeHidden = (employee, hidden) => run(`visibility-${employee.username}`, async () => {
    const result = await veraApi.updateStaff(employee.username, { profile_hidden: hidden })
    await load(true)
    setNotice({ type: 'success', message: result.message || `Đã ${hidden ? 'ẩn' : 'hiện'} nhân viên ${employee.full_name || employee.username}.` })
  })

  const setSelectedHidden = (hidden) => run(hidden ? 'hide-selected' : 'show-selected', async () => {
    if (!selected.length) throw new Error('Chưa chọn nhân viên.')
    for (const username of selected) await veraApi.updateStaff(username, { profile_hidden: hidden })
    const count = selected.length
    await load(true)
    setNotice({ type: 'success', message: `Đã ${hidden ? 'tạm ẩn' : 'hiện lại'} ${count} nhân viên.` })
  })

  const showHiddenEmployees = () => run('show-hidden-employees', async () => {
    if (!hiddenEmployees.length) throw new Error('Không có nhân viên đang bị ẩn.')
    for (const employee of hiddenEmployees) await veraApi.updateStaff(employee.username, { profile_hidden: false })
    const count = hiddenEmployees.length
    setVisibilityFilter('visible')
    await load(true)
    setNotice({ type: 'success', message: `Đã hiện lại ${count} nhân viên đang bị ẩn.` })
  })

  if (!isApiConfigured) return <div className="setup-note">Mục Nhân viên cần Python API V2 để ghi an toàn.</div>

  return (
    <div className="staff-page">
      <div className="page-heading-row staff-heading">
        <div>
          <div className="eyebrow"><UserRoundCog size={14} /> VẬN HÀNH NHÂN SỰ</div>
          <h1 className="page-title">Nhân viên</h1>
          <p className="page-subtitle">Danh sách, hồ sơ, trạng thái làm việc và phân ca trong một màn hình.</p>
        </div>
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
          <div className="staff-search"><Search size={17} /><input value={search} onChange={(event) => changeEmployeeSearch(event.target.value)} placeholder="Tìm tên nhân viên hoặc họ tên" /></div>
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
          {isAdmin && <select value={visibilityFilter} onChange={(event) => setVisibilityFilter(event.target.value)} aria-label="Lọc hiển thị nhân viên"><option value="visible">Đang hiển thị</option><option value="hidden">Đã tạm ẩn</option><option value="all">Tất cả nhân viên</option></select>}
        </div>
        <div className="staff-actionbar">
          {permissions.employee_add && <button className="primary-button" onClick={() => setAddOpen((value) => !value)}><Plus size={17} /> Thêm nhân viên</button>}
          {permissions.staff_export && <button className="secondary-button" disabled={busy === 'export'} onClick={() => run('export', () => veraApi.exportStaffExcel(search, roleFilter, statusFilter, shiftFilter))}><Download size={17} /> Export Excel</button>}
          {canSaveRows && <button className="secondary-button" disabled={busy === 'save' || !dirtyRows.length} onClick={saveRows}><Save size={17} /> Lưu thay đổi ({dirtyRows.length})</button>}
          {isAdmin && permissions.staff_export && <button className="secondary-button" disabled={busy === 'profiles-pdf' || !selected.length} onClick={exportSelectedProfiles}>{busy === 'profiles-pdf' ? <LoaderCircle className="spin" size={17}/> : <FileDown size={17}/>} Xuất đồng loạt PDF ({selected.length})</button>}
          {isAdmin && permissions.employee_delete && <button className="danger-button" disabled={busy === 'delete' || !selected.length} onClick={deleteSelected}><Trash2 size={17} /> Xóa đã chọn ({selected.length})</button>}
        </div>
      </section>

      {addOpen && <section className="panel staff-form-panel">
        <div className="panel-title-row"><div><h2>THÊM NHÂN VIÊN</h2><p>Mật khẩu chỉ được nhập khi tạo mới và không xuất ra Excel.</p></div></div>
        <form className="staff-form-grid" onSubmit={createStaff}>
          <div className="profile-field-section span-2">Thông tin tài khoản</div>
          <label>Tên nhân viên<input required value={createForm.username} onChange={(event) => setCreateForm({ ...createForm, username: event.target.value })} /></label>
          <label>Mật khẩu ban đầu (tối thiểu 8 ký tự)<input required minLength={8} type="password" autoComplete="new-password" value={createForm.password} onChange={(event) => setCreateForm({ ...createForm, password: event.target.value })} /></label>
          <label>Phân quyền<select value={createForm.role} onChange={(event) => setCreateForm({ ...createForm, role: event.target.value })}>{(data?.role_options || []).map((role) => <option key={role} value={role}>{ROLE_LABELS[role] || role}</option>)}</select></label>
          <label>Ngày bắt đầu làm<input type="date" value={createForm.employment_start_date} onChange={(event) => setCreateForm({ ...createForm, employment_start_date: event.target.value })} /></label>
          <div className="profile-field-section span-2">Thông tin cá nhân</div>
          <label>Họ và tên đầy đủ<input required value={createForm.full_name} onChange={(event) => setCreateForm({ ...createForm, full_name: event.target.value })} /></label>
          <label>Ngày sinh<input type="date" value={createForm.birth_date} onChange={(event) => setCreateForm({ ...createForm, birth_date: event.target.value })} /></label>
          <label>Giới tính<select value={createForm.gender} onChange={(event) => setCreateForm({ ...createForm, gender: event.target.value })}><option value="">-- Chọn Nam/Nữ --</option><option>Nam</option><option>Nữ</option></select></label>
          <label>Dân tộc<input value={createForm.ethnicity} onChange={(event) => setCreateForm({ ...createForm, ethnicity: event.target.value })} /></label>
          <div className="profile-field-section span-2">Thông tin định danh</div>
          <label>Số Căn cước<input required inputMode="numeric" maxLength="12" value={createForm.cccd_number} onChange={(event) => setCreateForm({ ...createForm, cccd_number: event.target.value.replace(/\D/g, '').slice(0, 12) })} /></label>
          <label>Ngày cấp<input type="date" value={createForm.cccd_issue_date} onChange={(event) => setCreateForm({ ...createForm, cccd_issue_date: event.target.value })} /></label>
          <label className="span-2">Nơi cấp<input value={createForm.cccd_issue_place} onChange={(event) => setCreateForm({ ...createForm, cccd_issue_place: event.target.value })} /></label>
          <div className="profile-field-section span-2">Thông tin liên hệ & Địa chỉ</div>
          <label>Điện thoại<input value={createForm.phone} onChange={(event) => setCreateForm({ ...createForm, phone: event.target.value })} /></label>
          <label>Email<input type="email" value={createForm.email} onChange={(event) => setCreateForm({ ...createForm, email: event.target.value })} /></label>
          <label>Tỉnh/Thành phố<input value={createForm.province} onChange={(event) => setCreateForm({ ...createForm, province: event.target.value })} /></label>
          <label>Quận/Huyện<input value={createForm.district} onChange={(event) => setCreateForm({ ...createForm, district: event.target.value })} /></label>
          <label>Phường/Xã<input value={createForm.ward} onChange={(event) => setCreateForm({ ...createForm, ward: event.target.value })} /></label>
          <label>Địa chỉ cụ thể (Số nhà, tên đường...)<input value={createForm.address_detail} onChange={(event) => setCreateForm({ ...createForm, address_detail: event.target.value })} /></label>
          <div className="profile-field-section span-2">Thông tin thanh toán/Ngân hàng</div>
          <label>Tên ngân hàng<input value={createForm.bank_name} onChange={(event) => setCreateForm({ ...createForm, bank_name: event.target.value })} /></label>
          <label>Số tài khoản ngân hàng<input value={createForm.bank_account} onChange={(event) => setCreateForm({ ...createForm, bank_account: event.target.value })} /></label>
          <EmployeeMediaDraftPanel value={createMedia} onChange={setCreateMedia} onIdentityExtracted={(fields) => setCreateForm((current) => ({
            ...current,
            full_name: current.full_name || fields.full_name || '',
            cccd_number: current.cccd_number || fields.cccd_number || '',
            cccd_issue_date: current.cccd_issue_date || toInputDate(fields.cccd_issue_date) || '',
            cccd_issue_place: current.cccd_issue_place || fields.cccd_issue_place || '',
          }))}/>
          <div className="staff-form-actions span-2"><button type="button" className="secondary-button" onClick={() => setAddOpen(false)}>Hủy</button><button className="primary-button" disabled={busy === 'create'}>{busy === 'create' ? <LoaderCircle size={17} className="spin" /> : <Plus size={17} />} Thêm nhân viên</button></div>
        </form>
      </section>}

      {profileUser && <section ref={profileSectionRef} className="panel staff-form-panel" style={{ scrollMarginTop: 128 }}>
        <div className="panel-title-row"><div><h2>SỬA HỒ SƠ · {profileUser}</h2><p>Cập nhật thông tin cá nhân.</p></div></div>
        <div className="staff-form-grid">
          {PROFILE_SECTIONS.map((section) => <div className="profile-section-fields span-2" key={section.title}>
            <div className="profile-field-section">{section.title}</div>
            <div className="staff-form-grid">
              {section.fields.map(([field, label]) => {
                const isDate = field.includes('date')
                if (field === 'gender') return <label key={field}>{label}<select value={profileDraft[field] ?? ''} onChange={(event) => setProfileDraft({ ...profileDraft, [field]: event.target.value })}><option value="">-- Chọn Nam/Nữ --</option><option>Nam</option><option>Nữ</option></select></label>
                return <label key={field}>{label}<input type={isDate ? 'date' : 'text'} inputMode={field === 'cccd_number' ? 'numeric' : undefined} maxLength={field === 'cccd_number' ? 12 : undefined} value={profileDraft[field] ?? ''} onChange={(event) => setProfileDraft({ ...profileDraft, [field]: field === 'cccd_number' ? event.target.value.replace(/\D/g, '').slice(0, 12) : event.target.value })} /></label>
              })}
            </div>
          </div>)}
          {isAdmin && <EmployeeIdentityPanel username={profileUser} allowPasswordReset allowAdminEdit className="span-2" onIdentityExtracted={(fields) => setProfileDraft((current) => ({
            ...current,
            cccd_number: current.cccd_number || fields.cccd_number || '',
            cccd_issue_date: current.cccd_issue_date || toInputDate(fields.cccd_issue_date) || '',
            cccd_issue_place: current.cccd_issue_place || fields.cccd_issue_place || '',
          }))}/>}
          <div className="staff-form-actions span-2"><button className="secondary-button" onClick={() => setProfileUser('')}>Hủy</button><button className="primary-button" disabled={busy === 'profile'} onClick={saveProfile}><Save size={17} /> Lưu hồ sơ</button></div>
        </div>
      </section>}

      <section className="panel staff-list-panel">
        <div className="panel-title-row"><div><h2>DANH SÁCH NHÂN VIÊN</h2><p>{visible.length} nhân viên phù hợp bộ lọc.{incompleteVisible ? ` · ${incompleteVisible} hồ sơ chưa đầy đủ (dòng vàng).` : ''}</p></div><button className="secondary-button" onClick={() => load()} disabled={loading || Boolean(busy)}><RefreshCw size={17} className={loading ? 'spin' : ''} /> Làm mới</button></div>
        {canSelectRows && <div className="staff-list-selection-actions">
          <button className="secondary-button" disabled={!visible.length || Boolean(busy)} onClick={selectAllVisible}><UserCheck size={17}/> Chọn tất cả</button>
          <button className="secondary-button" disabled={!selected.length || Boolean(busy)} onClick={clearSelected}>Bỏ chọn</button>
          {permissions.employees_visibility_manage && <button className="secondary-button" disabled={!selected.length || Boolean(busy)} onClick={() => setSelectedHidden(true)}><EyeOff size={17}/> Ẩn đã chọn</button>}
          {permissions.employees_visibility_manage && <button className="secondary-button" disabled={!hiddenEmployees.length || Boolean(busy)} onClick={showHiddenEmployees}>{busy === 'show-hidden-employees' ? <LoaderCircle className="spin" size={17}/> : <Eye size={17}/>} Hiện nhân viên đã ẩn ({hiddenEmployees.length})</button>}
        </div>}
        {loading ? <div className="empty-cell"><LoaderCircle className="spin" /> Đang tải danh sách…</div> : <>
          <div className="staff-desktop-table table-wrap">
            <table className="staff-table">
              <colgroup><col className="staff-col-select"/><col className="staff-col-employee"/><col className="staff-col-role"/><col className="staff-col-status"/><col className="staff-col-shift"/><col className="staff-col-date"/><col className="staff-col-cycle"/><col className="staff-col-lock"/><col className="staff-col-profile"/><col className="staff-col-admin"/></colgroup>
              <thead><tr><th>Chọn</th><th>Nhân viên</th><th>Phân quyền</th><th>Trạng thái</th><th>Ca làm việc</th><th>Ngày bắt đầu ca</th><th>Chu kỳ</th><th>Khóa</th><th>Hồ sơ</th><th>Admin</th></tr></thead>
              <tbody>{visible.map((employee) => {
                const draft = drafts[employee.username] || rowDraft(employee)
                const editable = canManage(employee)
                const missingFields = missingEmployeeProfileFields(employee)
                const rowClassName = [employee.employment_status === 'Đã nghỉ việc' ? 'staff-left-row' : '', missingFields.length ? 'staff-incomplete-row' : '', employee.profile_hidden ? 'staff-hidden-row' : ''].filter(Boolean).join(' ')
                return <tr key={employee.username} className={rowClassName} title={missingFields.length ? `Hồ sơ còn thiếu: ${missingFields.join(', ')}` : undefined}>
                  <td className="center"><input type="checkbox" checked={selected.includes(employee.username)} disabled={!editable || !canSelectRows} onChange={() => toggleSelected(employee.username)} aria-label={`Chọn ${employee.username}`} /></td>
                  <td><div style={{ display: 'flex', alignItems: 'center', gap: 5 }}><strong>{employee.username}</strong>{isAdmin && <button type="button" className="text-button" title="Đổi Tên hệ thống và Tên đăng nhập" disabled={Boolean(busy)} onClick={() => renameSystemName(employee)}><PencilLine size={13} /></button>}</div><small>{employee.full_name || '—'}</small>{employee.profile_hidden && <span className="staff-hidden-badge">Đang ẩn</span>}{missingFields.length > 0 && <span className="staff-incomplete-badge">Thiếu {missingFields.length} mục</span>}</td>
                  <td><select value={draft.role} disabled={!editable || !permissions.employee_edit_save} onChange={(event) => setDraft(employee.username, 'role', event.target.value)}>{Array.from(new Set([employee.role, ...(data?.role_options || [])])).map((role) => <option key={role} value={role}>{ROLE_LABELS[role] || role}</option>)}</select></td>
                  <td><select value={draft.employment_status} disabled={!editable || !permissions.employment_status_edit} onChange={(event) => setDraft(employee.username, 'employment_status', event.target.value)}>{(data?.status_options || []).map((status) => <option key={status}>{status}</option>)}</select></td>
                  <td><select value={draft.work_shift} disabled={!editable || !permissions.shift_assignment_edit} onChange={(event) => setDraft(employee.username, 'work_shift', event.target.value)}><option value="">Chưa chia ca</option>{shiftsFor(employee).map((shift) => <option key={shift}>{shift}</option>)}</select></td>
                  <td><input type="date" value={draft.shift_start_date} disabled={!editable || !permissions.shift_assignment_edit} onChange={(event) => setDraft(employee.username, 'shift_start_date', event.target.value)} /></td>
                  <td><select value={draft.rotation_cycle} disabled={!editable || !permissions.shift_assignment_edit} onChange={(event) => setDraft(employee.username, 'rotation_cycle', event.target.value)}><option value="">Chưa chọn</option>{(data?.cycle_options || []).map((cycle) => <option key={cycle}>{cycle}</option>)}</select></td>
                  <td className="center"><input type="checkbox" checked={draft.login_locked} disabled={!editable || !permissions.account_lock_edit} onChange={(event) => setDraft(employee.username, 'login_locked', event.target.checked)} aria-label={`Khóa ${employee.username}`} /></td>
                  <td><button className="text-button staff-edit-button" disabled={!editable || !permissions.employee_edit_save} onClick={() => openProfile(employee)}><FilePenLine size={15} /> Sửa</button></td>
                  <td><div className="list-actions">{isAdmin && permissions.employees_visibility_manage && <button className="secondary-button compact" disabled={Boolean(busy)} onClick={() => setEmployeeHidden(employee, !employee.profile_hidden)}>{employee.profile_hidden ? <Eye size={14}/> : <EyeOff size={14}/>} {employee.profile_hidden ? 'Hiện' : 'Ẩn'}</button>}{isAdmin && permissions.employee_delete && <button className="danger-button compact" disabled={Boolean(busy)} onClick={() => deleteOne(employee)}><Trash2 size={14} /> Xóa</button>}</div></td>
                </tr>
              })}</tbody>
            </table>
          </div>

          <div className="staff-mobile-list">{visible.map((employee) => {
            const draft = drafts[employee.username] || rowDraft(employee)
            const editable = canManage(employee)
            const missingFields = missingEmployeeProfileFields(employee)
            return <article className={`staff-mobile-card ${employee.employment_status === 'Đã nghỉ việc' ? 'left' : ''} ${missingFields.length ? 'incomplete' : ''} ${employee.profile_hidden ? 'hidden' : ''}`} key={employee.username} title={missingFields.length ? `Hồ sơ còn thiếu: ${missingFields.join(', ')}` : undefined}>
              <div className="staff-mobile-head"><label><input type="checkbox" checked={selected.includes(employee.username)} disabled={!editable || !canSelectRows} onChange={() => toggleSelected(employee.username)} /> <span><strong>{employee.username}</strong><small>{employee.full_name || '—'}</small>{employee.profile_hidden && <span className="staff-hidden-badge">Đang ẩn</span>}{missingFields.length > 0 && <span className="staff-incomplete-badge">Thiếu {missingFields.length} mục</span>}</span></label><div className="list-actions">{isAdmin && <button className="text-button" disabled={Boolean(busy)} onClick={() => renameSystemName(employee)}><PencilLine size={15} /> Đổi tên</button>}<button className="text-button" disabled={!editable || !permissions.employee_edit_save} onClick={() => openProfile(employee)}><FilePenLine size={15} /> Hồ sơ</button>{isAdmin && permissions.employees_visibility_manage && <button className="secondary-button compact" disabled={Boolean(busy)} onClick={() => setEmployeeHidden(employee, !employee.profile_hidden)}>{employee.profile_hidden ? <Eye size={14}/> : <EyeOff size={14}/>} {employee.profile_hidden ? 'Hiện' : 'Ẩn'}</button>}{isAdmin && permissions.employee_delete && <button className="danger-button compact" disabled={Boolean(busy)} onClick={() => deleteOne(employee)}><Trash2 size={14} /> Xóa</button>}</div></div>
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
