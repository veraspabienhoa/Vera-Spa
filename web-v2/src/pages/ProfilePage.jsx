import useAutoSave from '../hooks/useAutoSave'
import { BellRing, CheckCircle2, RefreshCw, Save, ShieldCheck, Smartphone } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import { refreshProfileReferenceData } from '../lib/profileReferenceRefresh'
import EmployeeIdentityPanel from './EmployeeIdentityPanel'
import { disablePushNotifications, enablePushNotifications, readPushState, syncExistingPushSubscription } from '../lib/pushNotifications'
import VeraDateInput from '../components/VeraDateInput'

const toInputDate = (value) => {
  const [day, month, year] = String(value || '').split('/')
  return day && month && year ? `${year}-${month}-${day}` : ''
}
const toVnDate = (value) => {
  const [year, month, day] = String(value || '').split('-')
  return year && month && day ? `${day}-${month}-${year}` : ''
}

export default function ProfilePage({ user, onPasswordChanged, forcePasswordChange = false }) {
  const [form, setForm] = useState({ current_password: '', new_password: '', full_name: '', birth_date: '', gender: '', ethnicity: '', phone: '', email: '', address: '', province: '', ward: '', address_detail: '', bank_account: '', bank_name: '', cccd_number: '', cccd_issue_date: '', cccd_issue_place: '' })
  const [references, setReferences] = useState({ provinces: [], wards: [], banks: [], bank_options: [] })
  const formRef = useRef(null)
  const savingRef = useRef(false)
  const [baseline, setBaseline] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordDone, setPasswordDone] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState(null)
  const [push, setPush] = useState({ loading: true, supported: false, subscribed: false })
  const [pushBusy, setPushBusy] = useState(false)
  const [referenceBusy, setReferenceBusy] = useState('')
  const [adminUsername, setAdminUsername] = useState(user?.employee_username || '')
  const [renamingUsername, setRenamingUsername] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [result, catalogs] = await Promise.all([veraApi.profile(), veraApi.profileReferenceData()])
      setForm((current) => {
        const next = { ...current, ...result.profile, birth_date: toInputDate(result.profile.birth_date), cccd_issue_date: toInputDate(result.profile.cccd_issue_date), current_password: '', new_password: '' }
        setBaseline(JSON.stringify(next))
        return next
      })
      setAdminUsername(result.profile.username || '')
      let wards = []
      const province = (catalogs.provinces || []).find((item) => item.name === result.profile.province)
      if (province) wards = (await veraApi.profileReferenceData(province.code)).wards || []
      setReferences({ provinces: catalogs.provinces || [], banks: catalogs.banks || [], bank_options: catalogs.bank_options || [], wards })
    } catch (error) { setNotice({ status: 'error', message: error.message }) }
    finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])
  useEffect(() => {
    syncExistingPushSubscription().then((state) => setPush({ ...state, loading: false }))
      .catch(() => readPushState().then((state) => setPush({ ...state, loading: false })).catch((error) => setPush({ loading: false, supported: false, subscribed: false, reason: error.message })))
  }, [])

  const submit = async (event) => {
    event?.preventDefault()
    if (savingRef.current || passwordDone || !formRef.current?.checkValidity()) return
    savingRef.current = true
    setSaving(true); setNotice(null)
    try {
      if ((forcePasswordChange || form.new_password) && !form.current_password) {
        throw new Error('Chỉ khi đổi mật khẩu mới cần nhập Mật khẩu hiện tại.')
      }
      if ((forcePasswordChange || form.new_password) && form.new_password !== confirmPassword) throw new Error('Xác nhận mật khẩu mới chưa khớp.')
      const payload = { ...form, birth_date: toVnDate(form.birth_date), cccd_issue_date: toVnDate(form.cccd_issue_date) }; delete payload.bank_code
      delete payload.district
      if (!forcePasswordChange && !form.new_password) {
        delete payload.current_password
        delete payload.new_password
      }
      const result = await veraApi.updateProfile(payload)
      setNotice({ status: 'success', message: result.message })
      window.dispatchEvent(new CustomEvent('vera-profile-updated'))
      setBaseline(JSON.stringify(form))
      if (result.password_changed) {
        setPasswordDone(true)
        setForm((current) => ({ ...current, current_password: '', new_password: '' }))
        setConfirmPassword('')
        window.setTimeout(onPasswordChanged, 1200)
      }
    } catch (error) { setNotice({ status: 'error', message: `KHÔNG THÀNH CÔNG (${error.message})` }) }
    finally { savingRef.current = false; setSaving(false) }
  }
  const passwordComplete = !(forcePasswordChange || form.new_password || form.current_password || confirmPassword)
    || Boolean(form.current_password && form.new_password.length >= 8 && form.new_password === confirmPassword)
  useAutoSave({ signature: JSON.stringify(form) !== baseline ? JSON.stringify([form, confirmPassword]) : '', enabled: !loading && !saving && !passwordDone && passwordComplete && JSON.stringify(form) !== baseline, save: submit, rootRef: formRef, lockRef: savingRef })

  const togglePush = async () => {
    setPushBusy(true); setNotice(null)
    try {
      const state = push.subscribed ? await disablePushNotifications() : await enablePushNotifications()
      setPush({ ...state, loading: false })
      setNotice({ status: 'success', message: state.subscribed ? 'Đã bật thông báo màn hình khóa trên thiết bị này.' : 'Đã tắt thông báo trên thiết bị này.' })
    } catch (error) { setNotice({ status: 'error', message: error.message }) }
    finally { setPushBusy(false) }
  }

  const renameAdminUsername = async () => {
    const currentUsername = String(user?.employee_username || '').trim()
    const nextUsername = String(adminUsername || '').trim().replace(/\s+/g, ' ')
    setNotice(null)
    if (!currentUsername || user?.role !== 'admin') return
    if (!nextUsername) {
      setNotice({ status: 'error', message: 'Tên đăng nhập Admin không được để trống.' })
      return
    }
    if (nextUsername === currentUsername) {
      setNotice({ status: 'error', message: 'Tên đăng nhập mới phải khác tên hiện tại.' })
      return
    }
    if (!window.confirm(`Đổi tên đăng nhập Admin:\n${currentUsername} → ${nextUsername}\n\nSau khi đổi, hệ thống sẽ đăng xuất. Hãy đăng nhập lại bằng tên mới.`)) return
    setRenamingUsername(true)
    try {
      const result = await veraApi.renameSystemName(currentUsername, nextUsername)
      setNotice({ status: 'success', message: `${result.message} Hệ thống đang đăng xuất để cập nhật tài khoản.` })
      window.dispatchEvent(new CustomEvent('vera-profile-updated'))
      window.setTimeout(onPasswordChanged, 1500)
    } catch (error) {
      setNotice({ status: 'error', message: `KHÔNG THÀNH CÔNG (${error.message})` })
    } finally {
      setRenamingUsername(false)
    }
  }

  const changeProvince = async (provinceName) => {
    setForm((current) => ({ ...current, province: provinceName, ward: '' }))
    const province = references.provinces.find((item) => item.name === provinceName)
    if (!province) { setReferences((current) => ({ ...current, wards: [] })); return }
    try {
      const result = await veraApi.profileReferenceData(province.code)
      setReferences((current) => ({ ...current, wards: result.wards || [] }))
    } catch (error) {
      setReferences((current) => ({ ...current, wards: [] }))
      setNotice({ status: 'error', message: `Không tải được danh sách Xã/Phường (${error.message}).` })
    }
  }

  const refreshReference = async (kind) => {
    setReferenceBusy(kind); setNotice(null)
    try {
      const province = references.provinces.find((item) => item.name === form.province)
      const result = await refreshProfileReferenceData(kind === 'wards' ? (province?.code ?? '') : '')
      setReferences((current) => ({
        provinces: result.provinces || current.provinces,
        banks: result.banks || current.banks,
        bank_options: result.bank_options || current.bank_options,
        wards: kind === 'wards' ? (result.wards || []) : current.wards,
      }))
      const label = kind === 'provinces' ? 'Tỉnh/Thành phố' : kind === 'wards' ? 'Phường/Xã' : 'Ngân hàng'
      setNotice({ status: 'success', message: `Đã cập nhật lại danh mục ${label}. ${result.administrative_standard || result.bank_standard || ''}`.trim() })
    } catch (error) {
      setNotice({ status: 'error', message: `Không cập nhật được danh mục (${error.message}).` })
    } finally {
      setReferenceBusy('')
    }
  }

  const passwordRequired = forcePasswordChange || Boolean(form.new_password)

  return <div className="feature-page">
    <div className="page-heading"><div><span className="eyebrow"><ShieldCheck size={14} /> Cá nhân</span><h1>HỒ SƠ & MẬT KHẨU</h1><p>{forcePasswordChange ? 'Vui lòng đặt mật khẩu mới để mở khóa các chức năng Web V2.' : 'Nhân viên tự cập nhật hồ sơ mà không bắt buộc thay đổi mật khẩu.'}</p></div><button className="secondary-button" onClick={load} disabled={loading}><RefreshCw size={16} className={loading ? 'spin' : ''} /> Làm mới</button></div>
    {notice && <div className={notice.status === 'success' ? 'success-box' : 'error-box'}>{notice.status === 'success' && <CheckCircle2 size={16} />} {notice.message}</div>}
    <section className="panel profile-panel">
      <form ref={formRef} className="profile-form" onSubmit={submit}>
        <p className="wide-field" role="status">{saving ? 'Đang tự lưu…' : 'Thông tin được tự lưu khi nhập xong và rời ô. Đổi mật khẩu cần nhập đủ mật khẩu hiện tại, mật khẩu mới và xác nhận.'}</p>
        <div className="profile-field-section wide-field">Thông tin cá nhân</div>
        <label>Họ và tên đầy đủ<input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
        <label>Ngày sinh<VeraDateInput aria-label="Ngày sinh" value={form.birth_date} onChange={(e) => setForm({ ...form, birth_date: e.target.value })} /></label>
        <label>Giới tính<select value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}><option value="">-- Chọn Nam/Nữ --</option><option>Nam</option><option>Nữ</option></select></label>
        <label>Dân tộc<input value={form.ethnicity} onChange={(e) => setForm({ ...form, ethnicity: e.target.value })} /></label>
        <div className="profile-field-section wide-field">Thông tin định danh</div>
        <label>Số Căn cước<input inputMode="numeric" maxLength="12" value={form.cccd_number} onChange={(e) => setForm({ ...form, cccd_number: e.target.value.replace(/\D/g, '').slice(0, 12) })} /></label>
        <label>Ngày cấp<VeraDateInput aria-label="Ngày cấp CCCD" value={form.cccd_issue_date} onChange={(e) => setForm({ ...form, cccd_issue_date: e.target.value })} /></label>
        <label className="wide-field">Nơi cấp<input value={form.cccd_issue_place} onChange={(e) => setForm({ ...form, cccd_issue_place: e.target.value })} /></label>
        <div className="profile-field-section wide-field">Thông tin liên hệ & Địa chỉ</div>
        <label>Điện thoại<input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
        <label>Email<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
        <label>Tỉnh/Thành phố<select value={form.province} onChange={(e) => void changeProvince(e.target.value)}><option value="">-- Chọn Tỉnh/Thành phố --</option>{form.province && !references.provinces.some((item) => item.name === form.province) && <option>{form.province}</option>}{references.provinces.map((item) => <option key={item.code} value={item.name}>{item.name}</option>)}</select><button type="button" className="secondary-button compact" onClick={() => void refreshReference('provinces')} disabled={Boolean(referenceBusy)}><RefreshCw size={14} className={referenceBusy === 'provinces' ? 'spin' : ''}/> Cập nhật danh mục</button></label>
        <label>Phường/Xã<select value={form.ward} onChange={(e) => setForm({ ...form, ward: e.target.value })} disabled={!form.province}><option value="">-- Chọn Phường/Xã --</option>{form.ward && !references.wards.includes(form.ward) && <option>{form.ward}</option>}{references.wards.map((ward) => <option key={ward}>{ward}</option>)}</select><button type="button" className="secondary-button compact" onClick={() => void refreshReference('wards')} disabled={Boolean(referenceBusy) || !form.province}><RefreshCw size={14} className={referenceBusy === 'wards' ? 'spin' : ''}/> Cập nhật danh mục</button></label>
        <label className="wide-field">Địa chỉ cụ thể (Số nhà, tên đường...)<input value={form.address_detail} onChange={(e) => setForm({ ...form, address_detail: e.target.value })} placeholder="Số nhà, tên đường, ấp/khu phố" /></label>
        <div className="profile-field-section wide-field">Thông tin thanh toán/Ngân hàng</div>
        <label>Tên ngân hàng<select value={form.bank_code || form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value, bank_code: e.target.value })}><option value="">-- Chọn ngân hàng --</option>{(references.bank_options || []).map((bank) => <option key={bank.code} value={bank.code}>{bank.short_name || bank.code}{bank.name && bank.name !== bank.short_name ? ` · ${bank.name}` : ''}</option>)}</select><button type="button" className="secondary-button compact" onClick={() => void refreshReference('banks')} disabled={Boolean(referenceBusy)}><RefreshCw size={14} className={referenceBusy === 'banks' ? 'spin' : ''}/> Cập nhật danh mục</button></label>
        <label>Mã ngân hàng tự động<input value={form.bank_code || ''} readOnly aria-label="Mã ngân hàng tự động" placeholder="Tự động: VCB / ACB / TCB…" /></label>
        <label>Số tài khoản ngân hàng<input value={form.bank_account} onChange={(e) => setForm({ ...form, bank_account: e.target.value.replace(/\D/g, '').slice(0, 19) })} inputMode="numeric" /></label>
        <div className="profile-password-box wide-field">
          <h3>{forcePasswordChange ? 'ĐỔI MẬT KHẨU LẦN ĐẦU' : 'THAY ĐỔI MẬT KHẨU (KHÔNG BẮT BUỘC)'}</h3><p>{forcePasswordChange ? 'Mật khẩu mới tối thiểu 8 ký tự và phải đáp ứng chính sách bảo mật.' : 'Để trống các ô mật khẩu nếu chỉ cập nhật hồ sơ. Hệ thống không yêu cầu đổi mật khẩu khi lưu thông tin cá nhân.'}</p>
          <div className="profile-password-grid">
            <label>Mật khẩu hiện tại<input type="password" value={form.current_password} onChange={(e) => setForm({ ...form, current_password: e.target.value })} required={passwordRequired} autoComplete="current-password" /></label>
            <label>Mật khẩu mới<input type="password" minLength="8" required={forcePasswordChange} value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} placeholder="Để trống nếu không đổi" autoComplete="new-password" /></label>
            <label>Xác nhận mật khẩu mới<input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required={passwordRequired} autoComplete="new-password" /></label>
          </div>
        </div>
        <EmployeeIdentityPanel username={user?.employee_username || ''} className="wide-field" onIdentityExtracted={(fields) => setForm((current) => ({
          ...current,
          full_name: current.full_name || fields.full_name || '',
          cccd_number: current.cccd_number || fields.cccd_number || '',
          cccd_issue_date: current.cccd_issue_date || toInputDate(fields.cccd_issue_date) || '',
          cccd_issue_place: current.cccd_issue_place || fields.cccd_issue_place || '',
        }))} />
        <button className="primary-button wide-field" disabled={saving}><Save size={16} /> {saving ? 'Đang lưu…' : 'Lưu hồ sơ'}</button>
      </form>
    </section>
    {user?.role === 'admin' && !forcePasswordChange && <section className="panel android-push-panel admin-username-panel">
      <div>
        <span className="eyebrow"><ShieldCheck size={14} /> Chỉ Admin</span>
        <h2>ĐỔI TÊN ĐĂNG NHẬP ADMIN</h2>
        <label>Tên đăng nhập mới<input value={adminUsername} onChange={(event) => setAdminUsername(event.target.value)} maxLength="120" autoComplete="username" /></label>
      </div>
      <button className="primary-button" type="button" onClick={renameAdminUsername} disabled={renamingUsername || loading}>
        <Save size={16} /> {renamingUsername ? 'Đang đổi…' : 'Đổi tên đăng nhập'}
      </button>
    </section>}
    <section className="panel android-push-panel">
      <div><span className="eyebrow"><Smartphone size={14} /> iPhone · Android</span><h2>THÔNG BÁO MÀN HÌNH KHÓA</h2><p>Mỗi điện thoại đăng nhập có thể bật Web Push riêng. Trên iPhone/iPad, hãy thêm VERA SPA vào Màn hình chính rồi mở từ biểu tượng; trên Android, dùng Chrome. Chế độ Không làm phiền vẫn có thể chặn âm thanh.</p></div>
      <button className={push.subscribed ? 'danger-button' : 'primary-button'} onClick={togglePush} disabled={push.loading || pushBusy || !push.supported}><BellRing size={16} /> {pushBusy ? 'Đang xử lý…' : (push.subscribed ? 'Tắt thông báo thiết bị này' : 'Bật thông báo thiết bị này')}</button>
      {!push.supported && !push.loading && <div className="warning-box">{push.reason || 'Trình duyệt hoặc thiết bị này chưa hỗ trợ Web Push.'}</div>}
    </section>
  </div>
}
