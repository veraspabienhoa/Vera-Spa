import { LoaderCircle } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

function readRegistrationForm() {
  const form = document.querySelector('.registration-panel .leave-form')
  const viewedDate = document.querySelector('.viewed-date-toolbar input[type="date"]')
  const selects = form ? Array.from(form.querySelectorAll('select')) : []
  const employee = selects[0]?.value || ''
  const reason = selects[1]?.value || ''
  const manual = form?.querySelector('input[type="number"]')?.value || ''
  return {
    form,
    reasonSelect: selects[1] || null,
    date: viewedDate?.value || '',
    employee,
    reason,
    manual,
  }
}

async function previewLeave(body, signal) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const response = await fetch(`${apiBase}/v2/leave/preview`, {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json',
      ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

export default function LeaveRegistrationEnhancements() {
  const [host, setHost] = useState(null)
  const [selection, setSelection] = useState({ date: '', employee: '', reason: '', manual: '' })
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let timer = null
    let observer = null
    const sync = () => {
      const current = readRegistrationForm()
      if (!current.form || !current.reasonSelect) {
        setHost(null)
        return
      }
      let nextHost = current.form.querySelector('[data-live-penalty-preview="true"]')
      if (!nextHost) {
        nextHost = document.createElement('div')
        nextHost.dataset.livePenaltyPreview = 'true'
        current.reasonSelect.insertAdjacentElement('afterend', nextHost)
      }
      setHost((old) => old === nextHost ? old : nextHost)
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
    }
  }, [])

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

  if (!host) return <style>{`
    .statistics-employee-search{display:none!important}
    .registration-panel .leave-form>.info-box{display:none!important}
  `}</style>

  return <>
    <style>{`
      .statistics-employee-search{display:none!important}
      .registration-panel .leave-form>.info-box{display:none!important}
      .live-penalty-preview{margin-top:2px;padding:10px 12px;border:1px solid #dbe5df;border-radius:10px;background:#f7faf8;color:#243d32;font-size:13px;line-height:1.45}
      .live-penalty-preview strong{color:#10251e}
      .live-penalty-preview .ordinal{display:inline-flex;margin-left:5px;padding:2px 7px;border-radius:999px;background:#fff1d7;color:#78551d;font-size:11px;font-weight:900}
      .live-penalty-preview.loading{display:flex;align-items:center;gap:7px;color:#66746d}
      .live-penalty-preview.error{border-color:#efd8a4;background:#fff8e8;color:#75561e}
      @media(max-width:820px){.live-penalty-preview{padding:8px 9px;font-size:11px}.live-penalty-preview .ordinal{font-size:9px}}
    `}</style>
    {createPortal(
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
      host,
    )}
  </>
}
