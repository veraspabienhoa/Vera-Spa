import { Edit3, Save, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

async function savedPayrollRequest(path, options = {}) {
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

function setNativeValue(element, value) {
  if (!element) return
  const proto = element.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set
  if (setter) setter.call(element, String(value))
  else element.value = String(value)
  element.dispatchEvent(new Event('change', { bubbles: true }))
}

function clickExistingButton(text) {
  const button = Array.from(document.querySelectorAll('.payroll-page-enhanced button'))
    .find((item) => String(item.textContent || '').includes(text))
  if (!button) throw new Error(`Không tìm thấy nút “${text}”. Hãy bấm Làm mới và thử lại.`)
  button.click()
}

export default function PayrollSavedAdminPanel({ user }) {
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const canManage = isAdmin || Boolean(user?.permissions?.payroll_history_edit)
  const [draftActionsTarget, setDraftActionsTarget] = useState(null)
  const [historyPanel, setHistoryPanel] = useState(null)
  const [cardTargets, setCardTargets] = useState([])
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)

  useEffect(() => {
    if (!canManage) return undefined
    let cancelled = false
    const locate = () => {
      if (cancelled) return
      const draftActions = document.querySelector('.payroll-page-enhanced .payroll-draft-panel .panel-title-row .list-actions')
      setDraftActionsTarget((current) => current === draftActions ? current : (draftActions || null))

      const sections = Array.from(document.querySelectorAll('.payroll-page-enhanced section.panel'))
      const history = sections.find((section) => section.querySelector('h2')?.textContent?.includes('LỊCH SỬ BẢNG LƯƠNG')) || null
      setHistoryPanel((current) => current === history ? current : history)

      const cards = Array.from(document.querySelectorAll('.payroll-page-enhanced .saved-payroll-card'))
        .map((card) => ({
          batch: String(card.querySelector('h3')?.textContent || '').trim(),
          target: card.querySelector('header'),
        }))
        .filter((item) => item.batch && item.target)
      setCardTargets((current) => {
        const same = current.length === cards.length && current.every((item, index) => item.batch === cards[index].batch && item.target === cards[index].target)
        return same ? current : cards
      })
    }
    locate()
    const observer = new MutationObserver(locate)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => {
      cancelled = true
      observer.disconnect()
    }
  }, [canManage])

  const reopenForEdit = async (batch) => {
    setBusy(batch); setNotice(null)
    try {
      const result = await savedPayrollRequest(`/v2/payroll/saved-batches/${encodeURIComponent(batch)}/edit`, { method: 'POST' })
      const monthInput = document.querySelector('.payroll-page-enhanced .payroll-calculate-panel input[type="month"]')
      const periodSelect = document.querySelector('.payroll-page-enhanced .payroll-calculate-panel select')
      if (!monthInput || !periodSelect) throw new Error('Không tìm thấy bộ chọn kỳ lương trên màn hình.')

      const wantedMonth = String(result.month)
      const wantedPeriod = String(result.period_no)
      if (monthInput.value === wantedMonth && periodSelect.value === wantedPeriod) {
        setNativeValue(periodSelect, wantedPeriod === '1' ? '2' : '1')
        await new Promise((resolve) => window.setTimeout(resolve, 100))
      }
      if (monthInput.value !== wantedMonth) {
        setNativeValue(monthInput, wantedMonth)
        await new Promise((resolve) => window.setTimeout(resolve, 100))
      }
      setNativeValue(periodSelect, wantedPeriod)
      setNotice({ type: 'success', message: result.message })
      window.setTimeout(() => document.querySelector('.payroll-page-enhanced .payroll-draft-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 500)
    } catch (error) {
      setNotice({ type: 'error', message: error.message })
    } finally {
      setBusy('')
    }
  }

  if (!canManage) return null

  return <>
    {draftActionsTarget && createPortal(<>
      <button className="secondary-button" type="button" disabled={Boolean(busy)} onClick={() => clickExistingButton('Lưu bảng lương nháp')}><Save size={16} /> Lưu bảng lương</button>
      <button className="danger-button" type="button" disabled={Boolean(busy)} onClick={() => clickExistingButton('Xóa bảng lương nháp')}><Trash2 size={16} /> Xóa bảng lương đã lưu</button>
    </>, draftActionsTarget, 'payroll-current-save-actions')}

    {cardTargets.map(({ batch, target }) => createPortal(
      <button className="secondary-button compact" type="button" disabled={Boolean(busy)} onClick={() => reopenForEdit(batch)}><Edit3 size={14} /> {busy === batch ? 'Đang mở…' : 'Chỉnh sửa'}</button>,
      target,
      `edit-${batch}`,
    ))}

    {historyPanel && notice && createPortal(
      <div className={notice.type === 'error' ? 'error-box' : 'success-box'} style={{ marginTop: 12 }}>{notice.message}</div>,
      historyPanel,
      'payroll-edit-notice',
    )}
  </>
}
