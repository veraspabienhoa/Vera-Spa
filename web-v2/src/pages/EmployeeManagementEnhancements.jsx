import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import EmployeeIdentityPanel from './EmployeeIdentityPanel'

export default function EmployeeManagementEnhancements({ user }) {
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const [target, setTarget] = useState(null)
  const [profileUser, setProfileUser] = useState('')

  useEffect(() => {
    let cancelled = false
    let ownedHost = null
    let timer = null

    const synchronize = () => {
      if (cancelled) return

      // Desktop: keep Hồ sơ immediately before Khóa as requested. React may
      // repaint the row after edits, so this small DOM convergence runs again
      // whenever the staff table changes.
      const table = document.querySelector('.staff-desktop-table .staff-table')
      const headRow = table?.querySelector('thead tr')
      if (headRow) {
        const headers = Array.from(headRow.children)
        const profileIndex = headers.findIndex((cell) => String(cell.textContent || '').trim() === 'Hồ sơ')
        const lockIndex = headers.findIndex((cell) => String(cell.textContent || '').trim() === 'Khóa')
        if (profileIndex >= 0 && lockIndex >= 0 && profileIndex > lockIndex) {
          headRow.insertBefore(headers[profileIndex], headers[lockIndex])
          table.querySelectorAll('tbody tr').forEach((row) => {
            const cells = Array.from(row.children)
            if (cells[profileIndex] && cells[lockIndex]) row.insertBefore(cells[profileIndex], cells[lockIndex])
          })
        }
      }

      const profilePanels = Array.from(document.querySelectorAll('.staff-form-panel'))
      const profilePanel = profilePanels.find((panel) => String(panel.querySelector('h2')?.textContent || '').startsWith('SỬA HỒ SƠ ·')) || null
      const heading = String(profilePanel?.querySelector('h2')?.textContent || '')
      const username = heading.split('·').slice(1).join('·').trim()
      const grid = profilePanel?.querySelector('.staff-form-grid')
      const actions = grid?.querySelector('.staff-form-actions')

      if (!profilePanel || !grid || !actions || !username) {
        if (ownedHost?.isConnected) ownedHost.remove()
        ownedHost = null
        setTarget(null)
        setProfileUser('')
        return
      }

      let host = grid.querySelector('[data-staff-security-host="true"]')
      if (!host) {
        host = document.createElement('div')
        host.dataset.staffSecurityHost = 'true'
        host.className = 'span-2'
        grid.insertBefore(host, actions)
        ownedHost = host
      }
      setTarget((current) => current === host ? current : host)
      setProfileUser((current) => current === username ? current : username)
    }

    const schedule = () => {
      if (timer) window.clearTimeout(timer)
      timer = window.setTimeout(synchronize, 20)
    }
    synchronize()
    const observer = new MutationObserver(schedule)
    observer.observe(document.body, { childList: true, subtree: true })
    document.addEventListener('change', schedule, true)
    document.addEventListener('click', schedule, true)
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
      observer.disconnect()
      document.removeEventListener('change', schedule, true)
      document.removeEventListener('click', schedule, true)
      if (ownedHost?.isConnected) ownedHost.remove()
    }
  }, [])

  if (!target || !profileUser) return null
  return createPortal(
    <EmployeeIdentityPanel username={profileUser} allowPasswordReset={isAdmin} />,
    target,
  )
}
