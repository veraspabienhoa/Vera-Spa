import { useEffect, useState } from 'react'
import { RefreshCw, ShieldAlert } from 'lucide-react'
import { veraApi } from '../lib/api'
import usePageRefresh from '../lib/usePageRefresh'
import './HcRulesPage.css'

export default function HcRulesPage({ user }) {
  const [data, setData] = useState(null)
  const [draft, setDraft] = useState(null)
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
  usePageRefresh(load, () => Boolean(busy || draft))
  const toggle = async item => {
    setBusy(item.code); setError(''); setNotice('')
    try {
      setData(await veraApi.saveHcRules(item.code, { enabled: !item.enabled, expected_revision: data.revision }))
      setNotice(`${item.name}: đã ${item.enabled ? 'tắt' : 'kích hoạt'} phạt tự động.`)
    } catch (cause) { setError(cause.message || 'Không lưu được Nội quy HC.') }
    finally { setBusy('') }
  }
  const saveCatalog = async () => {
    setBusy('catalog'); setError(''); setNotice('')
    try {
      setData(await veraApi.saveHcCatalog({ rules: draft, expected_revision: data.revision }))
      setDraft(null); setNotice('Đã lưu nội quy và mức phạt. Khoản phạt đã ghi giữ nguyên.')
    } catch (cause) { setError(cause.message || 'Không lưu được nội quy.') }
    finally { setBusy('') }
  }
  const changeRule = (index, values) => setDraft(rows => rows.map((row, i) => i === index ? { ...row, ...values } : row))
  return <section className="hc-rules-page">
    <div className="page-heading"><div><h1>Nội quy HC</h1><p>Áp dụng các bộ phận ngoài Leader, Nhân viên, Admin và Giám đốc.</p></div><button type="button" className="secondary-button" onClick={load} disabled={Boolean(busy || draft)}><RefreshCw size={16} /> Làm mới</button></div>
    {error && <p className="error-box" role="alert">{error}</p>}
    {notice && <p className="success-box" role="status">{notice}</p>}
    <article className="panel hc-rule-description"><h2><ShieldAlert size={22} /> Hạng mục và mức phạt</h2>
      <p>Đi trễ tính theo lương của thời gian trễ; nghỉ không phép tính theo lương ca chính, không gồm tăng ca hay phụ cấp. Admin có thể chọn hệ số lương hoặc số tiền cố định cho mỗi vi phạm.</p>
      <p>Thay đổi chỉ áp dụng cho ca bắt đầu sau khi lưu; giữ nguyên khoản phạt đã ghi. Phạt tự động vẫn cần lịch VERA, cấu hình lương và bằng chứng Face ID đầy đủ.</p>
      <p>Nội quy thêm mới áp dụng mức tiền cố định và ghi nhận vi phạm thủ công; chưa tự động phát hiện.</p>
      {canEdit && data && !draft && <button className="primary-button" disabled={Boolean(busy)} onClick={() => setDraft(data.rules || [])}>Cài đặt nội quy / mức phạt</button>}
      {(draft || data?.rules || []).map((rule, index) => <div className="hc-rule-item" key={rule.id}>
        {draft ? <>
          <label>Tên nội quy<input maxLength={120} value={rule.name} disabled={Boolean(busy)} onChange={e => changeRule(index, { name: e.target.value })} /></label>
          <label>Mô tả<textarea maxLength={2000} value={rule.description || ''} disabled={Boolean(busy)} onChange={e => changeRule(index, { description: e.target.value })} /></label>
          <label>Cách tính<select value={rule.mode} disabled={Boolean(busy)} onChange={e => changeRule(index, { mode: e.target.value, value: e.target.value === 'multiplier' ? 2 : 100000 })}>
            {rule.kind !== 'manual' && <option value="multiplier">Hệ số lương</option>}<option value="fixed">Số tiền cố định / vi phạm</option>
          </select></label>
          <label>{rule.mode === 'fixed' ? 'Mức phạt (đ)' : 'Hệ số nhân'}<input type="number" min="0.01" max={rule.mode === 'fixed' ? 1000000000 : 100} step="any" value={rule.value} disabled={Boolean(busy)} onChange={e => changeRule(index, { value: e.target.value })} /></label>
          <label><input type="checkbox" checked={rule.enabled} disabled={Boolean(busy)} onChange={e => changeRule(index, { enabled: e.target.checked })} /> Áp dụng hạng mục</label>
          <button className="secondary-button" disabled={Boolean(busy)} onClick={() => { if (window.confirm(`Xóa nội quy “${rule.name}”? Các khoản phạt đã ghi giữ nguyên.`)) setDraft(rows => rows.filter((_, i) => i !== index)) }}>Xóa nội quy</button>
        </> : <><h3>{rule.name}</h3><p>{rule.description}</p><p>{rule.mode === 'fixed' ? `${Number(rule.value).toLocaleString('vi-VN')}đ / vi phạm` : `Lương tương ứng × ${rule.value}`} · {rule.enabled ? 'Áp dụng' : 'Đã tắt'} · {rule.kind === 'manual' ? 'Ghi nhận thủ công' : 'Tự động khi bộ phận kích hoạt'}</p></>}
      </div>)}
      {draft && <div className="hc-catalog-actions">
        <button className="secondary-button" disabled={Boolean(busy) || draft.length >= 100} onClick={() => setDraft(rows => [...rows, { id: `rule_${crypto.randomUUID()}`, name: '', description: '', kind: 'manual', mode: 'fixed', value: 100000, enabled: false }])}>Thêm nội quy</button>
        {['late', 'absence'].filter(kind => !draft.some(r => r.kind === kind)).map(kind => <button key={kind} className="secondary-button" disabled={Boolean(busy)} onClick={() => setDraft(rows => [...rows, { id: kind, name: kind === 'late' ? 'Đi trễ' : 'Nghỉ không phép', kind, mode: 'multiplier', value: 2, enabled: false }])}>Thêm {kind === 'late' ? 'Đi trễ' : 'Nghỉ không phép'}</button>)}
        <button className="primary-button" disabled={Boolean(busy) || draft.some(r => !r.name.trim() || !Number.isFinite(Number(r.value)) || Number(r.value) <= 0)} onClick={saveCatalog}>Lưu thay đổi</button>
        <button className="secondary-button" disabled={Boolean(busy)} onClick={() => setDraft(null)}>Hủy</button>
      </div>}
    </article>
    <div className="hc-department-grid">{data?.departments.map(item => <article className={`panel hc-department ${item.enabled ? 'enabled' : ''}`} key={item.code}>
      <h2>{item.name}</h2><p>{item.enabled ? 'Đang kích hoạt phạt tự động' : 'Đã tắt phạt tự động'}</p>
      {item.salary_mode === 'tip' && <p>Chưa có đơn giá lương giờ/tháng: chưa tự phạt.</p>}
      {canEdit && <button type="button" className="primary-button" aria-pressed={item.enabled} disabled={Boolean(busy || draft)} onClick={() => toggle(item)}>{busy === item.code ? 'Đang lưu…' : item.enabled ? 'Tắt kích hoạt' : 'Kích hoạt'}</button>}
    </article>)}</div>
  </section>
}
