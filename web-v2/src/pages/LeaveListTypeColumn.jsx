import { useEffect, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

const normalizeReason = (value) => String(value || '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd')
  .replace(/Đ/g, 'D')
  .toLocaleLowerCase('vi-VN')
  .replace(/\s+/g, ' ')
  .trim()

async function loadReasonTypes(signal) {
  if (!apiBase) return []
  const session = await getCurrentSession()
  const response = await fetch(`${apiBase}/v2/leave/reason-types`, {
    signal,
    headers: session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {},
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return Array.isArray(payload.items) ? payload.items : []
}

function insertAfter(referenceNode, nextNode) {
  if (!referenceNode?.parentNode) return
  referenceNode.parentNode.insertBefore(nextNode, referenceNode.nextSibling)
}

export default function LeaveListTypeColumn() {
  const [catalog, setCatalog] = useState({})

  useEffect(() => {
    const controller = new AbortController()
    loadReasonTypes(controller.signal)
      .then((items) => {
        if (controller.signal.aborted) return
        const next = {}
        for (const item of items) {
          const key = normalizeReason(item?.name)
          if (!key) continue
          const leaveType = String(item?.leave_type || '').trim()
          next[key] = {
            leaveType,
            typeKey: normalizeReason(leaveType),
          }
        }
        setCatalog(next)
      })
      .catch((error) => {
        if (error?.name !== 'AbortError') console.warn('Không tải được Loại nghỉ từ BẢNG NỘI QUY:', error)
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    let scheduled = false

    const reasonInfo = (reason) => catalog[normalizeReason(reason)] || null

    const restoreAllOptions = (select) => {
      for (const option of select?.options || []) {
        option.hidden = false
        option.disabled = false
      }
    }

    const lockSelectToRowType = (select) => {
      if (!select) return
      const row = select.closest('tr')
      if (!row) return

      const selectedReason = String(select.value || '').trim()
      const selectedInfo = reasonInfo(selectedReason)

      if (!row.dataset.leaveTypeKey && selectedInfo?.typeKey) {
        row.dataset.leaveTypeKey = selectedInfo.typeKey
        row.dataset.leaveTypeLabel = selectedInfo.leaveType
      }

      const lockedTypeKey = String(row.dataset.leaveTypeKey || '').trim()
      const lockedTypeLabel = String(row.dataset.leaveTypeLabel || selectedInfo?.leaveType || '').trim()
      if (!lockedTypeKey) {
        restoreAllOptions(select)
        select.removeAttribute('data-leave-type-filtered')
        return
      }

      const selectedKey = normalizeReason(selectedReason)
      for (const option of select.options) {
        const optionKey = normalizeReason(option.value)
        const optionInfo = catalog[optionKey]
        const sameType = optionInfo?.typeKey === lockedTypeKey
        const isCurrentValue = optionKey === selectedKey
        const allowed = sameType || isCurrentValue
        option.hidden = !allowed
        option.disabled = !allowed
      }

      select.dataset.leaveTypeFiltered = 'true'
      select.dataset.leaveTypeKey = lockedTypeKey
      select.dataset.leaveTypeLabel = lockedTypeLabel
      select.title = lockedTypeLabel
        ? `Chỉ hiển thị Lý do nghỉ thuộc Loại nghỉ: ${lockedTypeLabel}`
        : 'Lý do nghỉ được giới hạn theo Loại nghỉ của dòng.'
      select.setAttribute(
        'aria-label',
        lockedTypeLabel
          ? `Lý do nghỉ, chỉ hiển thị nhóm ${lockedTypeLabel}`
          : 'Lý do nghỉ, giới hạn theo Loại nghỉ của dòng',
      )
    }

    const syncTable = () => {
      scheduled = false
      const table = document.querySelector('.leave-list-panel .leave-records-table')
      if (!table) return

      table.classList.add('with-leave-type-column')

      const colgroup = table.querySelector('colgroup')
      const reasonCol = colgroup?.querySelector('.leave-col-reason')
      if (colgroup && reasonCol && !colgroup.querySelector('.leave-col-type')) {
        const typeCol = document.createElement('col')
        typeCol.className = 'leave-col-type'
        insertAfter(reasonCol, typeCol)
      }

      const headerRow = table.querySelector('thead tr')
      const reasonHeader = headerRow
        ? Array.from(headerRow.children).find((cell) => normalizeReason(cell.textContent) === 'ly do')
        : null
      if (reasonHeader && !headerRow.querySelector('.leave-type-header')) {
        const typeHeader = document.createElement('th')
        typeHeader.className = 'leave-type-header'
        typeHeader.textContent = 'Loại nghỉ'
        insertAfter(reasonHeader, typeHeader)
      }

      const headerCount = headerRow?.children.length || 0
      for (const row of table.querySelectorAll('tbody tr')) {
        const emptyCell = row.querySelector('.empty-cell')
        if (emptyCell) {
          if (headerCount) emptyCell.colSpan = headerCount
          continue
        }

        const reasonCell = row.querySelector('.reason-edit-cell')
        if (!reasonCell) continue
        let typeCell = row.querySelector('.leave-type-cell')
        if (!typeCell) {
          typeCell = document.createElement('td')
          typeCell.className = 'leave-type-cell'
          insertAfter(reasonCell, typeCell)
        } else if (typeCell.previousElementSibling !== reasonCell) {
          insertAfter(reasonCell, typeCell)
        }

        const reasonSelect = reasonCell.querySelector('select')
        const reason = String(reasonSelect?.value || reasonCell.textContent || '').trim()
        const info = reasonInfo(reason)

        if (reasonSelect && !row.dataset.leaveTypeKey && info?.typeKey) {
          row.dataset.leaveTypeKey = info.typeKey
          row.dataset.leaveTypeLabel = info.leaveType
        }

        const leaveType = info?.leaveType || row.dataset.leaveTypeLabel || '—'
        if (typeCell.textContent !== leaveType) typeCell.textContent = leaveType
        typeCell.title = leaveType === '—'
          ? 'Chưa tìm thấy Loại nghỉ tương ứng trong BẢNG NỘI QUY.'
          : `Theo BẢNG NỘI QUY: ${leaveType}`

        if (reasonSelect) lockSelectToRowType(reasonSelect)
      }
    }

    const scheduleSync = () => {
      if (scheduled) return
      scheduled = true
      window.requestAnimationFrame(syncTable)
    }

    const handleReasonOpen = (event) => {
      const select = event.target?.closest?.('.reason-edit-cell select')
      if (select) lockSelectToRowType(select)
    }

    const handleReasonChange = (event) => {
      const select = event.target?.closest?.('.reason-edit-cell select')
      if (!select) return
      lockSelectToRowType(select)
      scheduleSync()
    }

    syncTable()
    const observer = new MutationObserver(scheduleSync)
    observer.observe(document.body, { childList: true, subtree: true, characterData: true })
    document.addEventListener('pointerdown', handleReasonOpen, true)
    document.addEventListener('focusin', handleReasonOpen, true)
    document.addEventListener('keydown', handleReasonOpen, true)
    document.addEventListener('change', handleReasonChange, true)
    document.addEventListener('input', handleReasonChange, true)

    return () => {
      observer.disconnect()
      document.removeEventListener('pointerdown', handleReasonOpen, true)
      document.removeEventListener('focusin', handleReasonOpen, true)
      document.removeEventListener('keydown', handleReasonOpen, true)
      document.removeEventListener('change', handleReasonChange, true)
      document.removeEventListener('input', handleReasonChange, true)
      const table = document.querySelector('.leave-list-panel .leave-records-table')
      for (const select of table?.querySelectorAll('.reason-edit-cell select') || []) restoreAllOptions(select)
    }
  }, [catalog])

  return <style>{`
    .leave-records-table .leave-type-header,
    .leave-records-table .leave-type-cell{vertical-align:middle}
    .leave-records-table .leave-type-cell{min-width:110px;color:#31483d;font-weight:800;line-height:1.25}
    .leave-records-table .reason-edit-cell select[data-leave-type-filtered="true"]{border-color:#b8cbc0;background:#fbfdfc}
    @media(max-width:820px){
      .leave-records-table.with-leave-type-column.without-penalty .leave-col-select{width:7%}
      .leave-records-table.with-leave-type-column.without-penalty .leave-col-date{width:11%}
      .leave-records-table.with-leave-type-column.without-penalty .leave-col-weekday{width:8%}
      .leave-records-table.with-leave-type-column.without-penalty .leave-col-employee{width:13%}
      .leave-records-table.with-leave-type-column.without-penalty .leave-col-reason{width:24%}
      .leave-records-table.with-leave-type-column.without-penalty .leave-col-type{width:14%}
      .leave-records-table.with-leave-type-column.without-penalty .leave-col-detail{width:23%}
      .leave-records-table.with-leave-type-column.with-penalty .leave-col-select{width:6%}
      .leave-records-table.with-leave-type-column.with-penalty .leave-col-date{width:9%}
      .leave-records-table.with-leave-type-column.with-penalty .leave-col-weekday{width:7%}
      .leave-records-table.with-leave-type-column.with-penalty .leave-col-employee{width:11%}
      .leave-records-table.with-leave-type-column.with-penalty .leave-col-reason{width:20%}
      .leave-records-table.with-leave-type-column.with-penalty .leave-col-type{width:12%}
      .leave-records-table.with-leave-type-column.with-penalty .leave-col-detail{width:20%}
      .leave-records-table.with-leave-type-column.with-penalty .leave-col-penalty{width:15%}
      .leave-records-table .leave-type-cell{min-width:0;padding:7px 2px;font-size:8px;overflow-wrap:anywhere}
      .leave-records-table .leave-type-header{font-size:7px;letter-spacing:.02em;overflow-wrap:anywhere}
    }
  `}</style>
}
