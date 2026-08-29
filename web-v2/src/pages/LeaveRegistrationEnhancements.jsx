import { LoaderCircle } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const VIOLATION_ENTRY_ROLES = new Set(['admin', 'quanly', 'letan'])

function readRegistrationForm() {
  const form = document.querySelector('.registration-panel .leave-form')
  const viewedDate = document.querySelector('.viewed-date-toolbar input[type="date"]')
  const originalSelects = form
    ? Array.from(form.querySelectorAll('select')).filter((select) => select.dataset.customReasonSelect !== 'true')
    : []
  const employeeSelect = originalSelects[0] || null
  const reasonSelect = form?.querySelector('select[data-original-leave-reason="true"]') || originalSelects[1] || null
  const reasonLabel = form
    ? Array.from(form.querySelectorAll('label')).find((label) => String(label.textContent || '').trim() === 'Lý do nghỉ') || null
    : null
  const manual = form?.querySelector('input[type="number"]')?.value || ''
  return {
    form,
    employeeSelect,
    reasonSelect,
    reasonLabel,
    date: viewedDate?.value || '',
    employee: employeeSelect?.value || '',
    reason: reasonSelect?.value || '',
    manual,
  }
}

async function authenticatedJson(path, options = {}) {
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

async function previewLeave(body, signal) {
  return authenticatedJson('/v2/leave/preview', {
    method: 'POST',
    signal,
    body: JSON.stringify(body),
  })
}

async function loadReasonGroups(date, signal) {
  return authenticatedJson(`/v2/leave/reason-groups?date=${encodeURIComponent(date)}`, { signal })
}

function setNativeSelectValue(select, value) {
  if (!select) return
  const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set
  if (setter) setter.call(select, value)
  else select.value = value
  select.dispatchEvent(new Event('change', { bubbles: true }))
}

export default function LeaveRegistrationEnhancements({ user }) {
  const role = String(user?.role || '').trim().toLowerCase()
  const canEnterViolations = VIOLATION_ENTRY_ROLES.has(role)
  const [previewHost, setPreviewHost] = useState(null)
  const [reasonHost, setReasonHost] = useState(null)
  const [selection, setSelection] = useState({ date: '', employee: '', reason: '', manual: '' })
  const [reasonGroups, setReasonGroups] = useState({ date: '', leave_reasons: [], violations: [], ready: false })
  const [groupError, setGroupError] = useState('')
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let timer = null
    let observer = null

    const sync = () => {
      const current = readRegistrationForm()
      if (!current.form || !current.reasonSelect) {
        setPreviewHost(null)
        setReasonHost(null)
        return
      }

      current.reasonSelect.dataset.originalLeaveReason = 'true'
      const splitActive = canEnterViolations
        && reasonGroups.ready
        && reasonGroups.date === current.date
        && !groupError

      current.reasonSelect.classList.toggle('violation-original-hidden', splitActive)
      current.reasonSelect.required = !splitActive
      if (current.reasonLabel) current.reasonLabel.classList.toggle('violation-original-hidden', splitActive)

      let nextReasonHost = current.form.querySelector('[data-violation-reason-host="true"]')
      if (splitActive) {
        if (!nextReasonHost) {
          nextReasonHost = document.createElement('div')
          nextReasonHost.dataset.violationReasonHost = 'true'
          nextReasonHost.className = 'violation-reason-host'
          current.reasonSelect.insertAdjacentElement('afterend', nextReasonHost)
        }
        setReasonHost((old) => old === nextReasonHost ? old : nextReasonHost)
      } else {
        if (nextReasonHost) nextReasonHost.remove()
        nextReasonHost = null
        setReasonHost(null)
      }

      let nextPreviewHost = current.form.querySelector('[data-live-penalty-preview="true"]')
      if (!nextPreviewHost) {
        nextPreviewHost = document.createElement('div')
        nextPreviewHost.dataset.livePenaltyPreview = 'true'
      }
      const anchor = nextReasonHost || current.reasonSelect
      anchor.insertAdjacentElement('afterend', nextPreviewHost)
      setPreviewHost((old) => old === nextPreviewHost ? old : nextPreviewHost)

      setSelection((old) => {
        const next = { date: current.date, employee: current.employee, reason: current.reason, manual: current.manual }
        return JSON.stringify(old) === JSON.stringify(next) ? old : next
      })
    }

    const schedule = () => {
      if (timer) window.clearTimeout(timer)
      timer = window.setTimeout(sync, 30)
    }
    sync()
    observer = new MutationObserver(schedule)
    observer.observe(document.body, { childList: true, subtree: true })
    document.addEventListener('change', schedule, true)
    document.addEventListener('input', schedule, true)
    return () => {
      if (timer) window.clearTimeout(timer)
      observer?.disconnect()
      document.removeEventListener('change', schedule, true)
      document.removeEventListener('input', schedule, true)
      const current = readRegistrationForm()
      current.reasonSelect?.classList.remove('violation-original-hidden')
      if (current.reasonSelect) current.reasonSelect.required = true
      current.reasonLabel?.classList.remove('violation-original-hidden')
      current.form?.querySelector('[data-violation-reason-host="true"]')?.remove()
    }
  }, [canEnterViolations, groupError, reasonGroups.date, reasonGroups.ready])

  useEffect(() => {
    if (!canEnterViolations || !selection.date) {
      setReasonGroups({ date: selection.date, leave_reasons: [], violations: [], ready: false })
      setGroupError('')
      return undefined
    }
    const controller = new AbortController()
    setGroupError('')
    loadReasonGroups(selection.date, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        setReasonGroups({
          date: selection.date,
          leave_reasons: Array.isArray(result.leave_reasons) ? result.leave_reasons : [],
          violations: Array.isArray(result.violations) ? result.violations : [],
          ready: true,
        })
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return
        // Safe rollout: if the new backend endpoint is not deployed yet, keep
        // the original reason dropdown visible instead of blocking registration.
        setReasonGroups({ date: selection.date, leave_reasons: [], violations: [], ready: false })
        setGroupError(err.message || 'Không tải được nhóm Lỗi vi phạm từ Nội quy.')
      })
    return () => controller.abort()
  }, [canEnterViolations, selection.date])

  const violationNames = useMemo(
    () => new Set(reasonGroups.violations.map((item) => item.name)),
    [reasonGroups.violations],
  )
  const leaveNames = useMemo(
    () => new Set(reasonGroups.leave_reasons.map((item) => item.name)),
    [reasonGroups.leave_reasons],
  )
  const selectedViolation = violationNames.has(selection.reason) ? selection.reason : ''
  const selectedLeave = leaveNames.has(selection.reason) ? selection.reason : ''

  const chooseReason = (value) => {
    const current = readRegistrationForm()
    setNativeSelectValue(current.reasonSelect, value)
  }

  const requestBody = useMemo(() => {
    if (!selection.date || !selection.employee || !selection.reason) return null
    const body = {
      leave_date: selection.date,
      employee_name: selection.employee,
      leave_reason: selection.reason,
      detail: '',
    }
    if (selection.manual !== '') body.manual_penalty = Number(selection.manual)
    return body
  }, [selection])

  useEffect(() => {
    if (!requestBody) {
      setPreview(null)
      setError('')
      setBusy(false)
      return undefined
    }
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setBusy(true)
      setError('')
      try {
        const result = await previewLeave(requestBody, controller.signal)
        setPreview(result)
      } catch (err) {
        if (err?.name !== 'AbortError') {
          setPreview(null)
          setError(err.message || 'Không tính trước được mức phạt.')
        }
      } finally {
        if (!controller.signal.aborted) setBusy(false)
      }
    }, 180)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [requestBody])

  return <>
    <style>{`
      .statistics-employee-search{display:none!important}
      .registration-panel .leave-form>.info-box{display:none!important}
      .violation-original-hidden{display:none!important}
      .violation-reason-host,.violation-reason-controls{display:contents}
      .violation-reason-note{display:block;margin:-2px 0 2px;color:#68766f;font-size:11px;line-height:1.35}
      .violation-reason-select{border-color:#e6cda4!important;background:#fffaf0!important}
      .live-penalty-preview{margin-top:2px;padding:10px 12px;border:1px solid #dbe5df;border-radius:10px;background:#f7faf8;color:#243d32;font-size:13px;line-height:1.45}
      .live-penalty-preview strong{color:#10251e}
      .live-penalty-preview .ordinal{display:inline-flex;margin-left:5px;padding:2px 7px;border-radius:999px;background:#fff1d7;color:#78551d;font-size:11px;font-weight:900}
      .live-penalty-preview.loading{display:flex;align-items:center;gap:7px;color:#66746d}
      .live-penalty-preview.error{border-color:#efd8a4;background:#fff8e8;color:#75561e}
      @media(max-width:820px){.live-penalty-preview{padding:8px 9px;font-size:11px}.live-penalty-preview .ordinal{font-size:9px}.violation-reason-note{font-size:10px}}
    `}</style>

    {reasonHost && reasonGroups.ready && createPortal(
      <div className="violation-reason-controls">
        <label>Lý do nghỉ</label>
        <select
          data-custom-reason-select="true"
          value={selectedLeave}
          required={!selectedViolation}
          onChange={(event) => chooseReason(event.target.value)}
        >
          <option value="">-- Chọn lý do nghỉ --</option>
          {reasonGroups.leave_reasons.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
        </select>

        <label>Lỗi vi phạm</label>
        <select
          data-custom-reason-select="true"
          className="violation-reason-select"
          value={selectedViolation}
          required={!selectedLeave}
          onChange={(event) => chooseReason(event.target.value)}
        >
          <option value="">-- Chọn lỗi vi phạm --</option>
          {reasonGroups.violations.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
        </select>
        <small className="violation-reason-note">Danh sách Lỗi vi phạm tự động lấy từ BẢNG NỘI QUY · Loại nghỉ = Vi phạm.</small>
      </div>,
      reasonHost,
    )}

    {previewHost && createPortal(
      !selection.reason ? null : busy
        ? <div className="live-penalty-preview loading"><LoaderCircle className="spin" size={15} /> Đang tính đúng mức Người Thứ N…</div>
        : error
          ? <div className="live-penalty-preview error">{error}</div>
          : preview
            ? <div className="live-penalty-preview">
                Số ngày tính: <strong>{Number(preview.calculated_days || 0).toLocaleString('vi-VN')}</strong>
                {preview.progressive && preview.ordinal ? <span className="ordinal">Người Thứ {preview.ordinal}</span> : null}
                {preview.penalty !== null && preview.penalty !== undefined
                  ? <> · Phạt dự kiến: <strong>{Number(preview.penalty || 0).toLocaleString('vi-VN')}đ</strong></>
                  : null}
              </div>
            : null,
      previewHost,
    )}
  </>
}
