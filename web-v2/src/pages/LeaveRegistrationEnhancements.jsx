import { LoaderCircle } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { apiErrorMessage } from '../lib/apiError'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const VIOLATION_ENTRY_ROLES = new Set(['admin', 'quanly', 'letan'])
const PAST_VIOLATION_ROLES = new Set(['quanly', 'letan'])

function todayInput() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function isPastDate(value) {
  return Boolean(value && value < todayInput())
}

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
  const manualInput = form?.querySelector('input[type="number"]') || null
  const detailInput = form?.querySelector('textarea') || null
  const submitButton = form?.querySelector('button[type="submit"]') || null
  return {
    form,
    employeeSelect,
    reasonSelect,
    reasonLabel,
    manualInput,
    detailInput,
    submitButton,
    date: viewedDate?.value || '',
    employee: employeeSelect?.value || '',
    reason: reasonSelect?.value || '',
    manual: manualInput?.value || '',
    detail: detailInput?.value || '',
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
  if (!response.ok) {
    const error = new Error(apiErrorMessage(payload, response.status))
    error.status = response.status
    throw error
  }
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

function isPreviewRolloutError(error) {
  const status = Number(error?.status || 0)
  const message = String(error?.message || '').toLowerCase()
  return status === 404 || status === 405 || message === 'not found' || message.includes('http 404') || message.includes('http 405')
}

function setNativeSelectValue(select, value) {
  if (!select) return
  const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set
  if (setter) setter.call(select, value)
  else select.value = value
  select.dispatchEvent(new Event('input', { bubbles: true }))
  select.dispatchEvent(new Event('change', { bubbles: true }))
}

function setNativeControlValue(control, value) {
  if (!control) return
  const prototype = control instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set
  if (setter) setter.call(control, value)
  else control.value = value
  control.dispatchEvent(new Event('input', { bubbles: true }))
  control.dispatchEvent(new Event('change', { bubbles: true }))
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
  const [pastSubmitBusy, setPastSubmitBusy] = useState(false)
  const [pastSubmitNotice, setPastSubmitNotice] = useState(null)

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
      current.form.classList.toggle('live-penalty-preview-ready', Boolean(preview) && !error)

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
      if (anchor.nextElementSibling !== nextPreviewHost) anchor.insertAdjacentElement('afterend', nextPreviewHost)
      setPreviewHost((old) => old === nextPreviewHost ? old : nextPreviewHost)

      const isPastViolation = PAST_VIOLATION_ROLES.has(role)
        && isPastDate(current.date)
        && reasonGroups.violations.some((item) => item.name === current.reason)
      current.form.classList.toggle('past-violation-entry-enabled', isPastViolation)
      if (current.submitButton) {
        if (isPastViolation) {
          current.submitButton.dataset.pastViolationEntry = 'true'
          current.submitButton.disabled = pastSubmitBusy
        } else if (current.submitButton.dataset.pastViolationEntry === 'true') {
          delete current.submitButton.dataset.pastViolationEntry
          current.submitButton.disabled = !apiBase
            || user?.permissions?.leave_create === false
            || Boolean(user?.registration_locked)
            || (role !== 'admin' && isPastDate(current.date))
        }
      }

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
      current.form?.classList.remove('past-violation-entry-enabled')
      current.form?.classList.remove('live-penalty-preview-ready')
      current.form?.querySelector('[data-violation-reason-host="true"]')?.remove()
    }
  }, [canEnterViolations, error, groupError, pastSubmitBusy, preview, reasonGroups.date, reasonGroups.ready, reasonGroups.violations, role, user?.permissions?.leave_create, user?.registration_locked])

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
  const canBackfillPastViolation = PAST_VIOLATION_ROLES.has(role) && isPastDate(selection.date) && Boolean(selectedViolation)

  const chooseReason = (value) => {
    setPastSubmitNotice(null)
    // Update the visible controlled select immediately. Waiting for the DOM
    // observer made the selection look blank until refresh on slower devices.
    setSelection((current) => ({ ...current, reason: value }))
    const current = readRegistrationForm()
    setNativeSelectValue(current.reasonSelect, value)
    // React may replace the hidden original select during the same render.
    // Verify once on the next frame so every role/device keeps the selection.
    window.requestAnimationFrame(() => {
      const latest = readRegistrationForm()
      if (latest.reasonSelect && latest.reasonSelect.value !== value) {
        setNativeSelectValue(latest.reasonSelect, value)
      }
    })
  }

  useEffect(() => {
    const current = readRegistrationForm()
    const form = current.form
    if (!form) return undefined

    const handlePastViolationSubmit = async (event) => {
      const latest = readRegistrationForm()
      const isPastViolation = PAST_VIOLATION_ROLES.has(role)
        && isPastDate(latest.date)
        && violationNames.has(latest.reason)
      if (!isPastViolation) return

      event.preventDefault()
      event.stopPropagation()
      if (typeof event.stopImmediatePropagation === 'function') event.stopImmediatePropagation()
      if (pastSubmitBusy) return

      setPastSubmitNotice(null)
      if (!apiBase || user?.permissions?.leave_create === false || user?.registration_locked) {
        setPastSubmitNotice({ type: 'error', message: 'Tài khoản hiện tại chưa được phép ghi lịch nghỉ.' })
        return
      }
      if (!latest.employee || !latest.reason || !latest.date) {
        setPastSubmitNotice({ type: 'error', message: 'Vui lòng chọn đầy đủ nhân viên, lỗi vi phạm và ngày.' })
        return
      }

      const violationItem = reasonGroups.violations.find((item) => item.name === latest.reason)
      if (violationItem?.requires_manual_penalty && latest.manual === '') {
        setPastSubmitNotice({ type: 'error', message: 'Lỗi vi phạm này bắt buộc nhập Mức phạt vi phạm.' })
        return
      }

      const body = {
        leave_date: latest.date,
        employee_name: latest.employee,
        leave_reason: latest.reason,
        detail: latest.detail || '',
      }
      if (latest.manual !== '') body.manual_penalty = Number(latest.manual)

      setPastSubmitBusy(true)
      try {
        const result = await authenticatedJson('/v2/leave/records', {
          method: 'POST',
          body: JSON.stringify(body),
        })
        setPastSubmitNotice({
          type: 'success',
          message: `Đã ghi lỗi vi phạm ngày ${latest.date.split('-').reverse().join('/')} THÀNH CÔNG.`,
        })
        setNativeSelectValue(latest.reasonSelect, '')
        setNativeControlValue(latest.detailInput, '')
        setNativeControlValue(latest.manualInput, '')
        window.setTimeout(() => {
          document.querySelector('.page-heading-row .secondary-button')?.click()
        }, 80)
        if (Array.isArray(result?.warnings) && result.warnings.length) {
          setPastSubmitNotice({ type: 'success', message: `Đã ghi THÀNH CÔNG · ${result.warnings.join(' · ')}` })
        }
      } catch (err) {
        setPastSubmitNotice({ type: 'error', message: `KHÔNG THÀNH CÔNG (${err.message || 'Không ghi được lỗi vi phạm.'})` })
      } finally {
        setPastSubmitBusy(false)
      }
    }

    form.addEventListener('submit', handlePastViolationSubmit, true)
    return () => form.removeEventListener('submit', handlePastViolationSubmit, true)
  }, [pastSubmitBusy, reasonGroups.violations, role, user?.permissions?.leave_create, user?.registration_locked, violationNames])

  const requestBody = useMemo(() => {
    if (!selection.date || !selection.employee || !selection.reason) return null
    const current = readRegistrationForm()
    const body = {
      leave_date: selection.date,
      employee_name: selection.employee,
      leave_reason: selection.reason,
      detail: current.detail || '',
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
          if (isPreviewRolloutError(err)) setError('')
          else setError(err.message || 'Không tính trước được mức phạt.')
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
      .registration-panel .leave-form>.info-box{display:block!important}
      .registration-panel .leave-form.live-penalty-preview-ready>.info-box{display:none!important}
      .violation-original-hidden{display:none!important}
      .violation-reason-host,.violation-reason-controls{display:contents}
      .violation-reason-note{display:block;margin:-2px 0 2px;color:#68766f;font-size:11px;line-height:1.35}
      .violation-reason-select{border-color:#e6cda4!important;background:#fffaf0!important}
      .live-penalty-preview{margin-top:2px;padding:10px 12px;border:1px solid #dbe5df;border-radius:10px;background:#f7faf8;color:#243d32;font-size:13px;line-height:1.45}
      .live-penalty-preview strong{color:#10251e}
      .live-penalty-preview .ordinal{display:inline-flex;margin-left:5px;padding:2px 7px;border-radius:999px;background:#fff1d7;color:#78551d;font-size:11px;font-weight:900}
      .live-penalty-preview.loading{display:flex;align-items:center;gap:7px;color:#66746d}
      .live-penalty-preview.error,.past-violation-submit-notice.error{border-color:#efd8a4;background:#fff8e8;color:#75561e}
      .past-violation-entry-note{margin-top:6px;padding:8px 10px;border:1px solid #d7e5dc;border-radius:9px;background:#f1f8f4;color:#2d5945;font-size:11px;font-weight:700}
      .past-violation-submit-notice{margin-top:6px;padding:8px 10px;border:1px solid #cfe5d7;border-radius:9px;background:#eff9f2;color:#23643f;font-size:11px;font-weight:800}
      .leave-form.past-violation-entry-enabled button[type="submit"]{opacity:1!important;cursor:pointer!important}
      @media(max-width:820px){.live-penalty-preview{padding:8px 9px;font-size:11px}.live-penalty-preview .ordinal{font-size:9px}.violation-reason-note,.past-violation-entry-note,.past-violation-submit-notice{font-size:10px}}
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
      <>
        {canBackfillPastViolation && (
          <div className="past-violation-entry-note">Quản lý/Lễ tân được nhập lỗi vi phạm cho ngày quá khứ. Các lý do nghỉ khác vẫn bị khóa.</div>
        )}
        {pastSubmitNotice && <div className={`past-violation-submit-notice ${pastSubmitNotice.type}`}>{pastSubmitNotice.message}</div>}
        {!selection.reason ? null : busy
          ? <div className="live-penalty-preview loading"><LoaderCircle className="spin" size={15} /> Đang tính đúng mức Người Thứ N…</div>
          : error
            ? <div className="live-penalty-preview error">{error}</div>
            : preview
              ? <div className="live-penalty-preview">
                  Số ngày tính: <strong>{Number(preview.calculated_days || 0).toLocaleString('vi-VN')}</strong>
                  {preview.progressive && preview.ordinal ? <span className="ordinal">Người Thứ {preview.ordinal}</span> : null}
                  {preview.penalty !== null && preview.penalty !== undefined
                    ? <> · Phạt vi phạm dự kiến: <strong>{Number(preview.penalty || 0).toLocaleString('vi-VN')}đ</strong></>
                    : null}
                </div>
              : null}
      </>,
      previewHost,
    )}
  </>
}
