import { BellRing, CheckCircle2, RefreshCw, Save, ShieldCheck, Smartphone } from 'lucide-react'
import { useEffect, useState } from 'react'
import { veraApi } from '../lib/api'
import { disablePushNotifications, enablePushNotifications, readPushState, syncExistingPushSubscription } from '../lib/pushNotifications'

const toInputDate = (value) => {
  const [day, month, year] = String(value || '').split('/')
  return day && month && year ? `${year}-${month}-${day}` : ''
}
const toVnDate = (value) => {
  const [year, month, day] = String(value || '').split('-')
  return year && month && day ? `${day}/${month}/${year}` : ''
}

export default function ProfilePage({ onPasswordChanged }) {
  const [form, setForm] = useState({ current_password: '', new_password: '', full_name: '', birth_date: '', phone: '', email: '', address: '', bank_account: '', bank_name: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState(null)
  const [push, setPush] = useState({ loading: true, supported: false, subscribed: false })
  const [pushBusy, setPushBusy] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const result = await veraApi.profile()
      setForm((current) => ({ ...current, ...result.profile, birth_date: toInputDate(result.profile.birth_date), current_password: '', new_password: '' }))
    } catch (error) { setNotice({ status: 'error', message: error.message }) }
    finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])
  useEffect(() => {
    syncExistingPushSubscription().then((state) => setPush({ ...state, loading: false }))
      .catch(() => readPushState().then((state) => setPush({ ...state, loading: false })).catch((error) => setPush({ loading: false, supported: false, subscribed: false, reason: error.message })))
  }, [])

  const submit = async (event) => {
    event.preventDefault(); setSaving(true); setNotice(null)
    try {
      const result = await veraApi.updateProfile({ ...form, birth_date: toVnDate(form.birth_date) })
      setNotice({ status: 'success', message: result.message })
      if (result.password_changed) window.setTimeout(onPasswordChanged, 1200)
      else await load()
    } catch (error) { setNotice({ status: 'error', message: `KHÔNG THÀNH CÔNG (${error.message})` }) }
    finally { setSaving(false) }
  }
  const togglePush = async () => {
    setPushBusy(true); setNotice(null)
    try {
      const state = push.subscribed ? await disablePushNotifications() : await enablePushNotifications()
      setPush({ ...state, loading: false })
      setNotice({ status: 'success', message: state.subscribed ? 'Đã bật thông báo màn hình khóa trên thiết bị này.' : 'Đã tắt thông báo trên thiết bị này.' })
    } catch (error) { setNotice({ status: 'error', message: error.message }) }
    finally { setPushBusy(false) }
  }

  return <div className="feature-page">
    <div className="page-heading"><div><span className="eyebrow"><ShieldCheck size={14} /> Cá nhân</span><h1>HỒ SƠ & MẬT KHẨU</h1><p>Nhân viên tự cập nhật thông tin của chính tài khoản đang đăng nhập.</p></div><button className="secondary-button" onClick={load} disabled={loading}><RefreshCw size={16} className={loading ? 'spin' : ''} /> Làm mới</button></div>
    {notice && <div className={notice.status === 'success' ? 'success-box' : 'error-box'}>{notice.status === 'success' && <CheckCircle2 size={16} />} {notice.message}</div>}
    <section className="panel profile-panel">
      <form className="profile-form" onSubmit={submit}>
        <label>Họ và tên đầy đủ<input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
        <label>Ngày sinh<input type="date" value={form.birth_date} onChange={(e) => setForm({ ...form, birth_date: e.target.value })} /></label>
        <label>Điện thoại<input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
        <label>Email<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
        <label className="wide-field">Địa chỉ<input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></label>
        <label>Số tài khoản ngân hàng<input value={form.bank_account} onChange={(e) => setForm({ ...form, bank_account: e.target.value })} /></label>
        <label>Tên ngân hàng<input value={form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} /></label>
        <div className="profile-password-box wide-field">
          <h3>THAY ĐỔI MẬT KHẨU</h3><p>Luôn nhập mật khẩu hiện tại để xác nhận. Để trống mật khẩu mới nếu chỉ sửa hồ sơ.</p>
          <div className="profile-password-grid">
            <label>Mật khẩu hiện tại<input type="password" value={form.current_password} onChange={(e) => setForm({ ...form, current_password: e.target.value })} required /></label>
            <label>Mật khẩu mới<input type="password" minLength="8" value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} placeholder="Tối thiểu 8 ký tự" /></label>
          </div>
        </div>
        <button className="primary-button wide-field" disabled={saving}><Save size={16} /> {saving ? 'Đang lưu…' : 'Lưu hồ sơ'}</button>
      </form>
    </section>
    <section className="panel android-push-panel">
      <div><span className="eyebrow"><Smartphone size={14} /> Android · Chrome</span><h2>THÔNG BÁO MÀN HÌNH KHÓA</h2><p>Cho phép Chrome gửi thông báo để nhận tin ngay cả khi không mở website. Chế độ Không làm phiền của điện thoại vẫn có thể chặn âm thanh.</p></div>
      <button className={push.subscribed ? 'danger-button' : 'primary-button'} onClick={togglePush} disabled={push.loading || pushBusy || !push.supported}><BellRing size={16} /> {pushBusy ? 'Đang xử lý…' : (push.subscribed ? 'Tắt thông báo thiết bị này' : 'Bật thông báo Android')}</button>
      {!push.supported && !push.loading && <div className="warning-box">{push.reason || 'Trình duyệt này chưa hỗ trợ Web Push. Hãy mở bằng Chrome trên Android.'}</div>}
    </section>
  </div>
}
