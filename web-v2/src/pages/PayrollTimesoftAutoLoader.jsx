import { CloudDownload, LoaderCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

function payrollControls() {
  const panel = document.querySelector('.payroll-calculate-panel')
  if (!panel) return {}
  const month = panel.querySelector('input[type="month"]')
  const period = Array.from(panel.querySelectorAll('select')).find((select) => {
    const labels = Array.from(select.options || []).map((option) => String(option.textContent || ''))
    return labels.some((label) => label.includes('Kỳ 1')) && labels.some((label) => label.includes('Kỳ 2'))
  })
  const file = Array.from(panel.querySelectorAll('input[type="file"]')).find((input) => !input.classList.contains('payroll-draft-file-input')) || null
  const calculate = Array.from(panel.querySelectorAll('button')).find((button) => String(button.textContent || '').includes('Upload & tính lương')) || null
  const toolbar = panel.querySelector('.data-toolbar')
  return { panel, month, period, file, calculate, toolbar }
}

async function fetchAutomaticSource(month, periodNo) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers()
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const params = new URLSearchParams({ month, period_no: String(periodNo) })
  const response = await fetch(`${apiBase}/v2/payroll/timesoft-source.xlsx?${params}`, { headers })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  }
  return {
    blob: await response.blob(),
    tipRows: Number(response.headers.get('X-Vera-TimeSoft-Tip-Rows') || 0),
  }
}

export default function PayrollTimesoftAutoLoader({ enabled }) {
  const [host, setHost] = useState(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)

  useEffect(() => {
    if (!enabled) { setHost(null); return undefined }
    let disposed = false
    let timer = null
    let observer = null

    const sync = () => {
      if (disposed) return
      const { toolbar } = payrollControls()
      if (!toolbar) {
        setHost(null)
        return
      }
      let target = toolbar.querySelector('[data-payroll-timesoft-auto-host="true"]')
      if (!target) {
        target = document.createElement('div')
        target.dataset.payrollTimesoftAutoHost = 'true'
        target.className = 'payroll-timesoft-auto-host'
        toolbar.appendChild(target)
      }
      setHost((current) => current === target ? current : target)
    }

    const schedule = () => {
      if (timer) window.clearTimeout(timer)
      timer = window.setTimeout(sync, 40)
    }
    sync()
    observer = new MutationObserver(schedule)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => {
      disposed = true
      if (timer) window.clearTimeout(timer)
      observer?.disconnect()
      const target = document.querySelector('[data-payroll-timesoft-auto-host="true"]')
      if (target?.isConnected) target.remove()
    }
  }, [enabled])

  const run = async () => {
    if (busy) return
    const controls = payrollControls()
    const month = String(controls.month?.value || '').trim()
    const periodNo = Number(controls.period?.value || 0)
    if (!month || ![1, 2].includes(periodNo) || !controls.file || !controls.calculate) {
      setNotice({ type: 'error', message: 'Chưa nhận diện được Tháng/Kỳ hoặc ô File TimeSoft.' })
      return
    }

    setBusy(true); setNotice(null)
    try {
      const { blob, tipRows } = await fetchAutomaticSource(month, periodNo)
      const filename = `TimeSoft_Auto_${month}_Ky${periodNo}.xlsx`
      const sourceFile = new File([blob], filename, {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      const transfer = new DataTransfer()
      transfer.items.add(sourceFile)
      controls.file.files = transfer.files
      controls.file.dispatchEvent(new Event('change', { bubbles: true }))
      setNotice({ type: 'success', message: `Đã lấy ${tipRows.toLocaleString('vi-VN')} dòng TIP từ TimeSoft/PostgreSQL. Đang chuyển vào bộ tính lương chuẩn…` })
      await new Promise((resolve) => window.setTimeout(resolve, 450))
      const latest = payrollControls()
      if (!latest.calculate || latest.calculate.disabled) {
        throw new Error('Đã lấy dữ liệu TimeSoft nhưng nút tính lương đang bị khóa. Hãy chờ rồi bấm Upload & tính lương.')
      }
      latest.calculate.click()
    } catch (error) {
      setNotice({ type: 'error', message: error.message || 'Không lấy được dữ liệu TimeSoft tự động.' })
    } finally {
      setBusy(false)
    }
  }

  if (!host) return null
  return createPortal(<div className="payroll-timesoft-auto-control">
    <style>{`
      .payroll-timesoft-auto-host{display:grid;gap:5px;align-self:end;min-width:min(100%,250px)}
      .payroll-timesoft-auto-control{display:grid;gap:5px}.payroll-timesoft-auto-control button{white-space:nowrap}
      .payroll-timesoft-auto-notice{max-width:330px;font-size:10px;line-height:1.35;color:#5f6d66}.payroll-timesoft-auto-notice.error{color:#a12c23}.payroll-timesoft-auto-notice.success{color:#246243}
      @media(max-width:760px){.payroll-timesoft-auto-host{width:100%}.payroll-timesoft-auto-control button{width:100%}}
    `}</style>
    <button type="button" className="secondary-button" disabled={busy} onClick={run}>
      {busy ? <LoaderCircle className="spin" size={16}/> : <CloudDownload size={16}/>} {busy ? 'Đang lấy TimeSoft…' : 'Lấy TimeSoft & tính lương'}
    </button>
    <small>Tự lấy dữ liệu TimeSoft đã đồng bộ vào PostgreSQL. Upload Excel vẫn dùng bình thường.</small>
    {notice && <div className={`payroll-timesoft-auto-notice ${notice.type}`}>{notice.message}</div>}
  </div>, host)
}
