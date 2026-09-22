import { ChevronDown, ChevronRight, RefreshCw, Save, Settings2, Undo2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import PayrollPage from './PayrollPageEnhanced'
import PayrollDebtAdminPanel from './PayrollDebtAdminPanel'
import PayrollPersonalTracking from './PayrollPersonalTracking'
import VeraMoneyInput from '../components/VeraMoneyInput'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const money = (value) => Number(value || 0).toLocaleString('vi-VN') + 'đ'
const personalTrackingRoles = new Set(['leader', 'nhanvien'])

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

function PayrollAdminSectionOrder({ enabled, version }) {
  useEffect(() => {
    if (!enabled) return undefined
    let disposed = false
    let observer = null
    let timer = null

    const markDefaultConfig = () => {
      if (disposed) return
      const root = document.querySelector('.payroll-v38-stack.full .payroll-page-enhanced')
      if (!root) {
        timer = window.setTimeout(markDefaultConfig, 80)
        return
      }
      const sections = Array.from(root.querySelectorAll('section.panel'))
      sections.forEach((section) => {
        const heading = section.querySelector('h2')?.textContent || ''
        section.classList.toggle('payroll-default-config-section', heading.includes('CÀI ĐẶT KHẤU TRỪ MẶC ĐỊNH'))
      })
      observer = new MutationObserver(() => {
        Array.from(root.querySelectorAll('section.panel')).forEach((section) => {
          const heading = section.querySelector('h2')?.textContent || ''
          section.classList.toggle('payroll-default-config-section', heading.includes('CÀI ĐẶT KHẤU TRỪ MẶC ĐỊNH'))
        })
      })
      observer.observe(root, { childList: true, subtree: true })
    }

    markDefaultConfig()
    return () => {
      disposed = true
      if (timer) window.clearTimeout(timer)
      observer?.disconnect()
    }
  }, [enabled, version])
  return null
}

export default function PayrollPageV38({ user }) {
  const role = String(user?.role || '').toLowerCase()
  const isAdmin = role === 'admin'
  const canEditConfig = isAdmin || Boolean(user?.permissions?.payroll_config_edit)
  const canFullPayroll = isAdmin || Boolean(
    user?.permissions?.payroll_calculate
    || user?.permissions?.payroll_config_edit
    || user?.permissions?.payroll_penalty_obligation
    || user?.permissions?.payroll_save
    || user?.permissions?.payroll_export
    || user?.permissions?.payroll_email
    || user?.permissions?.payroll_history_edit
    || user?.permissions?.payroll_history_delete
  )
  const showPersonalTracking = isAdmin || personalTrackingRoles.has(role)
  const [data, setData] = useState({ employees: [], overrides: [], config: {} })
  const [selected, setSelected] = useState([])
  const [living, setLiving] = useState(150000)
  const [locker, setLocker] = useState(80000)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)
  const [payrollVersion, setPayrollVersion] = useState(0)
  const [overridesOpen, setOverridesOpen] = useState(false)
  const [payrollTab, setPayrollTab] = useState('calculate')

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

  useEffect(() => {
    if (canEditConfig && overridesOpen) void loadOverrides()
  }, [canEditConfig, overridesOpen]) // eslint-disable-line react-hooks/exhaustive-deps

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

  return <div className={`payroll-v38-stack${canFullPayroll ? ' full' : ''}`}>
    <style>{`
      .payroll-v38-stack.full{display:flex;flex-direction:column}
      .payroll-v38-stack.full>.payroll-page-enhanced{display:contents}
      .payroll-main-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 16px}
      .payroll-main-tabs button{min-height:42px;padding:9px 18px;border:1px solid #b8d0c3;border-radius:12px;background:#fff;color:#24473a;font:inherit;font-weight:900;cursor:pointer}
      .payroll-main-tabs button.active{background:#1f513f;color:#fff;border-color:#1f513f}
      .payroll-page-enhanced.payroll-tab-calculate>.payroll-history-panel{display:none}
      .payroll-page-enhanced.payroll-tab-history>section.panel:not(.payroll-history-panel){display:none}
      @media(max-width:700px){.payroll-main-tabs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}.payroll-main-tabs button{width:100%;padding:8px 6px;white-space:nowrap}}
      .payroll-v38-stack.full>.payroll-personal-tracking{order:900}
      .payroll-v38-stack.full .payroll-default-config-section{order:910}
      .payroll-v38-stack.full>.payroll-v38-config{order:920}
      .payroll-v38-config .v38-collapse-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
      .payroll-v38-config .v38-collapsed-note{margin-top:8px;color:#6b7771;font-size:12px}
    `}</style>
    <PayrollAdminSectionOrder enabled={canFullPayroll} version={payrollVersion} />
    {canFullPayroll && <PayrollPage key={payrollVersion} user={user} activeTab={payrollTab} onTabChange={setPayrollTab} />}
    {showPersonalTracking && payrollTab === 'calculate' && <PayrollPersonalTracking user={user} standalone={!canFullPayroll} />}
    {isAdmin && canFullPayroll && payrollTab === 'calculate' && <PayrollDebtAdminPanel user={user} portalVersion={payrollVersion} onChanged={() => setPayrollVersion((value) => value + 1)} />}
    {canFullPayroll && canEditConfig && payrollTab === 'calculate' && <div className="feature-page payroll-page payroll-v38-config">
      <section className="panel">
        <div className="panel-title-row">
          <div>
            <h2><Settings2 size={17} /> MỨC RIÊNG THEO NHÂN VIÊN / LEADER · 3.8</h2>
            <p>Mức riêng thay cho khấu trừ mặc định khi tính bảng lương mới. Tiền Lương = 0 vẫn tự đưa Phí sinh hoạt và Hỗ trợ Locker về 0 theo quy tắc 3.7.</p>
          </div>
          <div className="v38-collapse-actions">
            {overridesOpen && <button className="secondary-button" type="button" onClick={() => loadOverrides()} disabled={Boolean(busy)}><RefreshCw size={16} className={busy === 'load' ? 'spin' : ''} /> Làm mới</button>}
            <button className="secondary-button" type="button" onClick={() => setOverridesOpen((value) => !value)}>{overridesOpen ? <ChevronDown size={16}/> : <ChevronRight size={16}/>} {overridesOpen ? 'Ẩn' : 'Hiện'}</button>
          </div>
        </div>

        {!overridesOpen && <div className="v38-collapsed-note">Khu vực Mức riêng mặc định được ẩn.</div>}
        {overridesOpen && <>
          {notice && <div className={notice.type === 'error' ? 'error-box' : 'success-box'}>{notice.message}</div>}

          <div className="payroll-config-grid">
            <label>Chi phí sinh hoạt riêng<VeraMoneyInput disabled={Boolean(busy)} value={living} onChange={(event) => setLiving(Number(event.target.value))} /></label>
            <label>Hỗ trợ Locker riêng<VeraMoneyInput disabled={Boolean(busy)} value={locker} onChange={(event) => setLocker(Number(event.target.value))} /></label>
            <div><strong>Đã chọn: {selected.length}</strong><small style={{ display: 'block', marginTop: 6 }}>Mặc định hiện tại: {money(data.config?.default_living_expense)} / {money(data.config?.default_locker_support)}</small></div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 8, margin: '14px 0' }}>
            {(data.employees || []).map((item) => <label key={item.employee_name} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '8px 10px', border: '1px solid #e6e0dc', borderRadius: 8 }}>
              <input type="checkbox" checked={selectedSet.has(item.employee_name)} disabled={Boolean(busy)} onChange={() => toggleEmployee(item.employee_name)} />
              <span><strong>{item.employee_name}</strong><small style={{ display: 'block' }}>{item.role === 'leader' ? 'Leader' : item.role === 'nhanvien' ? 'Nhân viên' : item.role} · {item.has_override ? `${money(item.living_expense)} / ${money(item.locker_support)}` : 'Đang dùng mặc định'}</small></span>
            </label>)}
          </div>

          <div className="list-actions">
            <button className="primary-button" type="button" onClick={saveOverrides} disabled={Boolean(busy) || !selected.length}><Save size={16} /> {busy === 'save' ? 'Đang lưu…' : 'Áp dụng mức riêng'}</button>
            <button className="secondary-button" type="button" onClick={resetOverrides} disabled={Boolean(busy) || !selected.length}><Undo2 size={16} /> {busy === 'reset' ? 'Đang đặt lại…' : 'Dùng lại mặc định'}</button>
          </div>

          <div className="responsive-data-table" style={{ marginTop: 16 }}><table><thead><tr><th>Nhân viên</th><th>Phí sinh hoạt riêng</th><th>Hỗ trợ Locker riêng</th></tr></thead><tbody>{configured.map((item) => <tr key={item.employee_name}><td><strong>{item.employee_name}</strong></td><td>{money(item.living_expense)}</td><td>{money(item.locker_support)}</td></tr>)}</tbody></table></div>
          {!configured.length && <div className="setup-note">Chưa có mức riêng. Tất cả Nhân viên/Leader đang dùng mức mặc định.</div>}
        </>}
      </section>
    </div>}
  </div>
}
