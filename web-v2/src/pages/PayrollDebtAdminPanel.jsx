import { Plus, RefreshCw, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const money = (value) => Number(value || 0).toLocaleString('vi-VN') + 'đ'

async function debtAdminRequest(path, options = {}) {
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

function dateToIso(value, label) {
  const match = String(value || '').trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/)
  if (!match) throw new Error(`${label} phải theo định dạng dd/mm/yyyy.`)
  const [, dd, mm, yyyy] = match
  const day = Number(dd); const month = Number(mm); const year = Number(yyyy)
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1 || parsed.getUTCDate() !== day) {
    throw new Error(`${label} không phải ngày hợp lệ.`)
  }
  return `${yyyy}-${mm}-${dd}`
}

const emptyForm = () => ({
  employee_name: '',
  amount: '',
  period_start: '',
  period_end: '',
  due_from: '',
  debt_type: 'Âm thực nhận',
  content: 'Chưa hoàn thành nghĩa vụ Vi phạm',
})

export default function PayrollDebtAdminPanel({ user, portalVersion = 0, onChanged }) {
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const [target, setTarget] = useState(null)
  const [rows, setRows] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)

  useEffect(() => {
    if (!isAdmin) return undefined
    let cancelled = false
    let timer = null
    const locate = () => {
      if (cancelled) return
      const node = document.querySelector('.payroll-page-enhanced .payroll-obligation-groups')
      if (node) setTarget(node)
      else timer = window.setTimeout(locate, 60)
    }
    locate()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [isAdmin, portalVersion])

  const load = async (silent = false) => {
    if (!isAdmin) return
    if (!silent) setBusy('load')
    try {
      const result = await debtAdminRequest('/v2/payroll-debt-sync/admin-debts')
      setRows(result.rows || [])
      if (result.warning) setNotice({ type: 'warning', message: result.warning })
    } catch (error) {
      setNotice({ type: 'error', message: error.message })
    } finally {
      if (!silent) setBusy('')
    }
  }

  useEffect(() => { void load() }, [isAdmin, portalVersion]) // eslint-disable-line react-hooks/exhaustive-deps

  const employeeOptions = useMemo(
    () => Array.from(new Set(rows.map((item) => item.employee_name).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'vi')),
    [rows],
  )

  const addDebt = async (event) => {
    event.preventDefault()
    setBusy('add'); setNotice(null)
    try {
      const payload = {
        ...form,
        amount: Number(form.amount || 0),
        period_start: dateToIso(form.period_start, 'Kỳ phát sinh từ'),
        period_end: dateToIso(form.period_end, 'Kỳ phát sinh đến'),
        due_from: dateToIso(form.due_from, 'Bắt đầu trừ từ'),
      }
      const result = await debtAdminRequest('/v2/payroll-debt-sync/admin-debts', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setForm(emptyForm())
      await load(true)
      setNotice({ type: 'success', message: result.message })
      onChanged?.()
    } catch (error) {
      setNotice({ type: 'error', message: error.message })
    } finally {
      setBusy('')
    }
  }

  const deleteDebt = async (item) => {
    if (!window.confirm(`Xóa khoản ${money(item.amount)} của ${item.employee_name}? Khoản này sẽ không tự xuất hiện lại sau khi đồng bộ hệ thống cũ.`)) return
    setBusy(`delete-${item.debt_key}`); setNotice(null)
    try {
      const result = await debtAdminRequest(`/v2/payroll-debt-sync/admin-debts/${encodeURIComponent(item.debt_key)}`, { method: 'DELETE' })
      await load(true)
      setNotice({ type: 'success', message: result.message })
      onChanged?.()
    } catch (error) {
      setNotice({ type: 'error', message: error.message })
    } finally {
      setBusy('')
    }
  }

  if (!isAdmin || !target) return null

  return createPortal(<div className="payroll-obligation-group" style={{ borderStyle: 'dashed' }}>
    <div className="panel-title-row">
      <div>
        <h3>🛠️ ADMIN · THÊM / XÓA NỢ VI PHẠM</h3>
        <p>Admin có thể thêm mới hoặc xóa khoản nợ từ hệ thống cũ/Web V2. Ngày nhập thống nhất dd/mm/yyyy. Khoản đã xóa được ghi nhớ để không xuất hiện lại sau lần đồng bộ kế tiếp.</p>
      </div>
      <button className="secondary-button compact" type="button" onClick={() => load()} disabled={Boolean(busy)}><RefreshCw size={14} className={busy === 'load' ? 'spin' : ''} /> Làm mới</button>
    </div>

    {notice && <div className={notice.type === 'error' ? 'error-box' : notice.type === 'warning' ? 'warning-box' : 'success-box'}>{notice.message}</div>}

    <form className="payroll-obligation-form" onSubmit={addDebt}>
      <label>Loại nợ<select value={form.debt_type} disabled={Boolean(busy)} onChange={(event) => setForm({ ...form, debt_type: event.target.value })}><option>Âm thực nhận</option><option>Tạm hoãn vi phạm</option></select></label>
      <label>Nhân viên<input required list="payroll-admin-debt-employees" value={form.employee_name} disabled={Boolean(busy)} onChange={(event) => setForm({ ...form, employee_name: event.target.value })} /></label>
      <label>Số tiền<input required type="number" min="1" inputMode="numeric" value={form.amount} disabled={Boolean(busy)} onChange={(event) => setForm({ ...form, amount: event.target.value })} /></label>
      <label>Kỳ phát sinh từ<input required type="text" inputMode="numeric" placeholder="dd/mm/yyyy" pattern="\d{2}/\d{2}/\d{4}" value={form.period_start} disabled={Boolean(busy)} onChange={(event) => setForm({ ...form, period_start: event.target.value })} /></label>
      <label>Kỳ phát sinh đến<input required type="text" inputMode="numeric" placeholder="dd/mm/yyyy" pattern="\d{2}/\d{2}/\d{4}" value={form.period_end} disabled={Boolean(busy)} onChange={(event) => setForm({ ...form, period_end: event.target.value })} /></label>
      <label>Bắt đầu trừ từ<input required type="text" inputMode="numeric" placeholder="dd/mm/yyyy" pattern="\d{2}/\d{2}/\d{4}" value={form.due_from} disabled={Boolean(busy)} onChange={(event) => setForm({ ...form, due_from: event.target.value })} /></label>
      <label>Nội dung<input required value={form.content} disabled={Boolean(busy)} onChange={(event) => setForm({ ...form, content: event.target.value })} /></label>
      <button className="primary-button" type="submit" disabled={Boolean(busy)}><Plus size={16} /> {busy === 'add' ? 'Đang thêm…' : 'Thêm mới'}</button>
    </form>
    <datalist id="payroll-admin-debt-employees">{employeeOptions.map((name) => <option key={name}>{name}</option>)}</datalist>

    <div className="responsive-data-table" style={{ marginTop: 12 }}><table><thead><tr><th>Tên nhân viên</th><th>Số tiền</th><th>Loại</th><th>Kỳ phát sinh</th><th>Bắt đầu trừ</th><th>Nguồn</th><th></th></tr></thead><tbody>{rows.map((item) => <tr key={item.debt_key}><td><strong>{item.employee_name}</strong></td><td>{money(item.amount)}</td><td>{item.type}</td><td>{item.period_start} – {item.period_end}</td><td>{item.due_from}</td><td>{item.source}</td><td><button className="danger-button compact" type="button" disabled={Boolean(busy)} onClick={() => deleteDebt(item)}><Trash2 size={14} /> Xóa</button></td></tr>)}</tbody></table></div>
    {!rows.length && <div className="setup-note">Không có Nợ vi phạm đang mở.</div>}
  </div>, target)
}
