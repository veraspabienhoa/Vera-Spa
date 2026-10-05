import { useEffect, useState } from 'react'
import { RefreshCw, ShieldAlert } from 'lucide-react'
import { veraApi } from '../lib/api'
import usePageRefresh from '../lib/usePageRefresh'
import './HcRulesPage.css'

export default function HcRulesPage({ user }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const canEdit = user?.role === 'admin'
  const load = async () => {
    setBusy('load'); setError('')
    try { setData(await veraApi.hcRules()) }
    catch (cause) { setError(cause.message || 'Không tải được Nội quy HC.') }
    finally { setBusy('') }
  }
  useEffect(() => { void load() }, [])
  usePageRefresh(load, () => Boolean(busy))
  const toggle = async item => {
    setBusy(item.code); setError(''); setNotice('')
    try {
      setData(await veraApi.saveHcRules(item.code, { enabled: !item.enabled, expected_revision: data.revision }))
      setNotice(`${item.name}: đã ${item.enabled ? 'tắt' : 'kích hoạt'} phạt tự động.`)
    } catch (cause) { setError(cause.message || 'Không lưu được Nội quy HC.') }
    finally { setBusy('') }
  }
  return <section className="hc-rules-page">
    <div className="page-heading"><div><h1>Nội quy HC</h1><p>Áp dụng các bộ phận ngoài Leader, Nhân viên, Admin và Giám đốc.</p></div><button type="button" className="secondary-button" onClick={load} disabled={Boolean(busy)}><RefreshCw size={16} /> Làm mới</button></div>
    {error && <p className="error-box" role="alert">{error}</p>}
    {notice && <p className="success-box" role="status">{notice}</p>}
    <article className="panel hc-rule-description"><h2><ShieldAlert size={22} /> Đi trễ / Nghỉ không phép</h2>
      <p><strong>Đi trễ:</strong> thời gian trễ thực tế so với giờ làm đã xếp × đơn giá lương giờ × 2.</p>
      <p><strong>Nghỉ không phép:</strong> tiền lương toàn bộ ca chính × 2, không cộng tăng ca hay phụ cấp.</p>
      <p>Lương giờ lấy cấu hình từng nhân viên hoặc bộ phận, theo ca và mốc 22 giờ. Lương tháng quy đổi từ lương cơ bản ÷ ngày công chuẩn ÷ giờ làm chuẩn.</p>
      <p>Quy tắc mới mặc định tắt. Khi kích hoạt chỉ xét ca bắt đầu sau thời điểm bật; không phạt lại lịch sử. Tắt không xóa khoản phạt đã ghi.</p>
      <p>Chỉ ghi phạt khi lịch VERA, đơn giá và bằng chứng Face ID đầy đủ. Nghỉ không phép chỉ xác định sau khi kết thúc ca chính và dữ liệu máy đã đồng bộ qua mốc đó. Trường hợp có phép, đã có phạt hoặc thiếu dữ liệu giữ lại để đối chiếu.</p>
    </article>
    <div className="hc-department-grid">{data?.departments.map(item => <article className={`panel hc-department ${item.enabled ? 'enabled' : ''}`} key={item.code}>
      <h2>{item.name}</h2><p>{item.enabled ? 'Đang kích hoạt phạt tự động' : 'Đã tắt phạt tự động'}</p>
      {item.salary_mode === 'tip' && <p>Chưa có đơn giá lương giờ/tháng: chưa tự phạt.</p>}
      {canEdit && <button type="button" className="primary-button" aria-pressed={item.enabled} disabled={Boolean(busy)} onClick={() => toggle(item)}>{busy === item.code ? 'Đang lưu…' : item.enabled ? 'Tắt kích hoạt' : 'Kích hoạt'}</button>}
    </article>)}</div>
  </section>
}
