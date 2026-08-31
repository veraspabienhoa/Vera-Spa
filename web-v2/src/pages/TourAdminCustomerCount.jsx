import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'

const normalize = (value) => String(value || '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd')
  .replace(/Đ/g, 'D')
  .trim()
  .toUpperCase()

function numberValue(value) {
  const raw = String(value || '').trim()
  if (!raw) return 0
  const cleaned = raw.replace(/[^0-9-]/g, '')
  const parsed = Number(cleaned)
  return Number.isFinite(parsed) ? parsed : 0
}

export default function TourAdminCustomerCount({ user }) {
  const [host, setHost] = useState(null)
  const [customerCount, setCustomerCount] = useState(0)
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'

  useEffect(() => {
    let scheduled = false
    let ownedHost = null

    const sync = () => {
      scheduled = false
      const filter = document.querySelector('.tour-shift-filter')
      const table = document.querySelector('.tour-table table')
      if (!filter) return

      const buttons = Array.from(filter.querySelectorAll(':scope > button'))
      const ca2 = buttons.find((button) => String(button.textContent || '').trim() === 'Ca 2') || buttons[2]
      let nextHost = filter.querySelector('[data-tour-customer-count="true"]')
      if (!nextHost) {
        nextHost = document.createElement('div')
        nextHost.dataset.tourCustomerCount = 'true'
        nextHost.className = 'tour-customer-count-host'
        if (ca2?.nextSibling) filter.insertBefore(nextHost, ca2.nextSibling)
        else filter.appendChild(nextHost)
        ownedHost = nextHost
      }
      setHost((current) => current === nextHost ? current : nextHost)

      if (!table) {
        setCustomerCount(0)
        return
      }
      const retainedValue = filter.dataset.tourCustomerCount
      if (retainedValue !== undefined && retainedValue !== '') {
        setCustomerCount(numberValue(retainedValue))
        return
      }
      const headers = Array.from(table.querySelectorAll('thead th'))
      const totalIndex = headers.findIndex((cell) => {
        const key = normalize(cell.textContent)
        return key === 'TONG SL' || key === 'TONG SO LUONG' || key.includes('TONG SL')
      })
      if (totalIndex < 0) {
        setCustomerCount(0)
        return
      }
      const total = Array.from(table.querySelectorAll('tbody tr')).reduce((sum, row) => {
        const cells = row.querySelectorAll('td')
        return sum + numberValue(cells[totalIndex]?.textContent)
      }, 0)
      setCustomerCount(total)
    }

    const schedule = () => {
      if (scheduled) return
      scheduled = true
      window.requestAnimationFrame(sync)
    }

    sync()
    const observer = new MutationObserver(schedule)
    observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true })
    document.addEventListener('click', schedule, true)
    return () => {
      observer.disconnect()
      document.removeEventListener('click', schedule, true)
      if (ownedHost?.isConnected) ownedHost.remove()
    }
  }, [])

  const style = <style>{`
    .tour-shift-filter>small{display:none!important}
    .tour-customer-count-host{display:flex;align-items:center}
    .tour-customer-count{display:flex;align-items:center;gap:6px;padding:9px 13px;border:1px solid #d9e1dc;border-radius:10px;background:#fff;color:#2d4539;font-weight:800;white-space:nowrap}
    .tour-customer-count strong{font-size:17px;color:#0f5137}
    @media(max-width:640px){.tour-customer-count-host{flex:1 0 100%}.tour-customer-count{width:100%;justify-content:center;padding:8px 10px}}
  `}</style>

  if (!host || !isAdmin) return style
  return <>{style}{createPortal(<div className="tour-customer-count"><span>Số khách:</span><strong>{customerCount.toLocaleString('vi-VN')}</strong></div>, host)}</>
}
