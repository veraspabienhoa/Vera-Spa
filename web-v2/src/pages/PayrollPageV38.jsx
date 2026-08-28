import { RefreshCw, Save, Settings2, Undo2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import PayrollPage from './PayrollPage'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const money = (value) => Number(value || 0).toLocaleString('vi-VN') + 'đ'

async function payrollV38Request(path, options = {}) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers(options.headers || {})
  headers.set('Content-Type', 'application/json')
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const response = await fetch(`${apiBase}${path}`, { ...options, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

export default function PayrollPageV38({ user }) {
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const canEditConfig = isAdmin || Boolean(user?.permissions?.payroll_config_edit)
  const [data, setData] = useState({ employees: [], overrides: [], config: {} })
  const [selected, setSelected] = useState([])
  const [living, setLiving] = useState(150000)
  const [locker, setLocker] = useState(80000)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)

  const loadOverrides = async (silent = false) => {
    if (!canEditConfig) return
    if (!silent) setBusy('load')
    try {
      const result = await payrollV38Request('/v2/payroll-v38/employee-overrides')
      setData(result)
      const config = result.config || {}
      setLiving(Number(config.default_living_expense ?? 150000))
      setLocker(Number(config.default_locker_support ?? 80000))
      if (result.legacy_imported_count > 0) {
        setNotice({ type: 'success', message: `Bảng lương 3.8 đã kế thừa ${result.legacy_imported_count} mức riêng từ hệ thống cũ.` })
      }
    } catch (error) {
      setNotice({ type: 'error', message: error.message })
    } finally {
      if (!silent) setBusy('')
    }
  }

  useEffect(() => { void loadOverrides() }, [canEditConfig]) // eslint-disable-line react-hooks/exhaustive-deps

  const selectedSet = useMemo(() => new Set(selected), [selected])
  const toggleEmployee = (name) => {
    setSelected((current) => current.includes(name)
      ? current.filter((item) => item !== name)
      : [...current, name])
  }

  const saveOverrides = async () => {
    if (!selected.length) {
      setNotice({ type: 'error', message: 'Vui lòng chọn ít nhất 1 Nhân viên/Leader.' })
      return
    }
    setBusy('save'); setNotice(null)
    try {
      const result = await payrollV38Request('/v2/payroll-v38/employee-overrides', {
        method: 'PUT',
        body: JSON.stringify({
          employees: selected,
          living_expense: Number(living || 0),
          locker_support: Number(locker || 0),
        }),
      })
      setData(result)
      setNotice({ type: 'success', message: result.message })
    } catch (error) {
      setNotice({ type: 'error', message: error.message })
    } finally {
      setBusy('')
    }
  }

  const resetOverrides = async () => {
    if (!selected.length) {
      setNotice({ type: 'error', message: 'Vui lòng chọn ít nhất 1 Nhân viên/Leader.' })
      return
    }
    setBusy('reset'); setNotice(null)
    try {
      const result = await payrollV38Request('/v2/payroll-v38/employee-overrides/reset', {
        method: 'POST',
        body: JSON.stringify({ employees: selected }),
      })
      setData(result)
      setNotice({ type: 'success', message: result.message })
    } catch (error) {
      setNotice({ type: 'error', message: error.message })
    } finally {
      setBusy('')
    }
  }

  const configured = data.overrides || []

  return <>
    <PayrollPage user={user} />
    {canEditConfig && <div className="feature-page payroll-page payroll-v38-config">
      <section className="panel">
        <div className="panel-title-row">
          <div>
            <h2><Settings2 size={17} /> MỨC RIÊNG THEO NHÂN VIÊN / LEADER · 3.8</h2>
            <p>Mức riêng thay cho khấu trừ mặc định khi tính bảng lương mới. Tiền Lương = 0 vẫn tự đưa Phí sinh hoạt và Hỗ trợ Locker về 0 theo quy tắc 3.7.</p>
          </div>
          <button className="secondary-button" type="button" onClick={() => loadOverrides()} disabled={Boolean(busy)}><RefreshCw size={16} className={busy === 'load' ? 'spin' : ''} /> Làm mới</button>
        </div>
        {notice && <div className={notice.type === 'error' ? 'error-box' : 'success-box'}>{notice.message}</div>}

        <div className="payroll-config-grid">
          <label>Chi phí sinh hoạt riêng<input type="number" min="0" inputMode="numeric" disabled={Boolean(busy)} value={living} onChange={(event) => setLiving(Number(event.target.value))} /></label>
          <label>Hỗ trợ Locker riêng<input type="number" min="0" inputMode="numeric" disabled={Boolean(busy)} value={locker} onChange={(event) => setLocker(Number(event.target.value))} /></label>
          <div><strong>Đã chọn: {selected.length}</strong><small style={{ display: 'block', marginTop: 6 }}>Mặc định hiện tại: {money(data.config?.default_living_expense)} / {money(data.config?.default_locker_support)}</small></div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 8, margin: '14px 0' }}>
          {(data.employees || []).map((item) => <label key={item.employee_name} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '8px 10px', border: '1px solid #e6e0dc', borderRadius: 8 }}>
            <input type="checkbox" checked={selectedSet.has(item.employee_name)} disabled={Boolean(busy)} onChange={() => toggleEmployee(item.employee_name)} />
            <span><strong>{item.employee_name}</strong><small style={{ display: 'block' }}>{item.role === 'leader' ? 'Leader' : 'Nhân viên'} · {item.has_override ? `${money(item.living_expense)} / ${money(item.locker_support)}` : 'Đang dùng mặc định'}</small></span>
          </label>)}
        </div>

        <div className="list-actions">
          <button className="primary-button" type="button" onClick={saveOverrides} disabled={Boolean(busy) || !selected.length}><Save size={16} /> {busy === 'save' ? 'Đang lưu…' : 'Áp dụng mức riêng'}</button>
          <button className="secondary-button" type="button" onClick={resetOverrides} disabled={Boolean(busy) || !selected.length}><Undo2 size={16} /> {busy === 'reset' ? 'Đang đặt lại…' : 'Dùng lại mặc định'}</button>
        </div>

        <div className="responsive-data-table" style={{ marginTop: 16 }}><table><thead><tr><th>Nhân viên</th><th>Phí sinh hoạt riêng</th><th>Hỗ trợ Locker riêng</th></tr></thead><tbody>{configured.map((item) => <tr key={item.employee_name}><td><strong>{item.employee_name}</strong></td><td>{money(item.living_expense)}</td><td>{money(item.locker_support)}</td></tr>)}</tbody></table></div>
        {!configured.length && <div className="setup-note">Chưa có mức riêng. Tất cả Nhân viên/Leader đang dùng mức mặc định.</div>}
      </section>
    </div>}
  </>
}
