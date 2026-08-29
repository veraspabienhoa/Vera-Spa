import { useEffect, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

// The visible Lễ tân editor for a record dated today always contains exactly
// these three choices. Compatibility aliases are only used to recognize old
// rows and are never rendered as a fourth choice.
const LETAN_REASON_GROUPS = [
  ['group-1', ['Nghỉ CÓ phép', 'Đi trễ CÓ phép', 'Về sớm CÓ phép']],
  ['group-2', ['Nghỉ KHÔNG phép', 'Đi trễ KHÔNG phép', 'Về sớm KHÔNG phép']],
  ['group-3', ['Nghỉ CUỐI TUẦN CÓ phép', 'Đi trễ CUỐI TUẦN CÓ phép', 'Về sớm CUỐI TUẦN CÓ phép']],
  ['group-4', ['Nghỉ CUỐI TUẦN KHÔNG phép', 'Đi trễ CUỐI TUẦN KHÔNG phép', 'Về sớm CUỐI TUẦN KHÔNG phép']],
  ['group-5', ['Leader nghỉ phép theo chính sách', 'Leader đi trễ sớm theo chính sách', 'Leader về sớm về sớm theo chính sách']],
]

const normalizeReason = (value) => String(value || '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd')
  .replace(/Đ/g, 'D')
  .toLocaleLowerCase('vi-VN')
  .replace(/\s+/g, ' ')
  .trim()

const LETAN_REASON_TO_GROUP = Object.fromEntries(
  LETAN_REASON_GROUPS.flatMap(([group, reasons]) => reasons.map((reason) => [normalizeReason(reason), group])),
)
// Existing Nội quy data may contain this corrected legacy wording. Recognize it
// as Group 5, but keep the requested three visible choices above.
LETAN_REASON_TO_GROUP[normalizeReason('Leader về sớm theo chính sách')] = 'group-5'

const LETAN_GROUP_CHOICES = Object.fromEntries(LETAN_REASON_GROUPS)

function letanGroupKey(reason) {
  return LETAN_REASON_TO_GROUP[normalizeReason(reason)] || ''
}

function localDateKey() {
  const value = new Date()
  const year = value.getFullYear()
  const month = `${value.getMonth() + 1}`.padStart(2, '0')
  const day = `${value.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

function rowDateKey(row) {
  const raw = String(row?.querySelector?.('.list-date-link')?.textContent || '').trim()
  const match = raw.match(/^(\d{2})\/(\d{2})\/(\d{4})$/)
  return match ? `${match[3]}-${match[2]}-${match[1]}` : ''
}

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

export default function LeaveListTypeColumn({ user }) {
  const [catalog, setCatalog] = useState({})
  const isLetan = String(user?.role || '').trim().toLowerCase() === 'letan'

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

    const restoreNativeOptions = (select) => {
      for (const option of select?.options || []) {
        option.hidden = false
        option.disabled = false
      }
      select?.removeAttribute('data-letan-group-filtered')
      select?.removeAttribute('data-leave-type-filtered')
    }

    const removeLetanProxy = (select) => {
      if (!select) return
      select.classList.remove('letan-native-reason-select')
      select.removeAttribute('aria-hidden')
      select.removeAttribute('data-letan-proxy-source')
      const proxy = select.parentElement?.querySelector('.letan-three-choice-select')
      proxy?.remove()
    }

    const restoreAllOptions = (select) => {
      restoreNativeOptions(select)
      removeLetanProxy(select)
    }

    const ensureNativeOption = (select, value) => {
      const wanted = normalizeReason(value)
      let option = Array.from(select.options).find((item) => normalizeReason(item.value) === wanted)
      if (!option) {
        option = document.createElement('option')
        option.value = value
        option.textContent = value
        option.dataset.letanInjected = 'true'
        select.appendChild(option)
      }
      return option
    }

    const ensureLetanThreeChoiceProxy = (select, row, groupKey, selectedReason) => {
      const choices = LETAN_GROUP_CHOICES[groupKey] || []
      if (choices.length !== 3) return false

      restoreNativeOptions(select)
      select.classList.add('letan-native-reason-select')
      select.setAttribute('aria-hidden', 'true')
      select.dataset.letanProxySource = 'true'

      let proxy = select.parentElement?.querySelector('.letan-three-choice-select')
      if (!proxy) {
        proxy = document.createElement('select')
        proxy.className = 'letan-three-choice-select'
        insertAfter(select, proxy)
        proxy.addEventListener('change', () => {
          const nextReason = String(proxy.value || '').trim()
          if (!nextReason) return
          const nativeOption = ensureNativeOption(select, nextReason)
          select.value = nativeOption.value
          // React owns reasonDrafts. Dispatching on the original select keeps
          // Save edits on the canonical React/API path instead of bypassing it.
          select.dispatchEvent(new Event('change', { bubbles: true }))
        })
      }

      proxy.replaceChildren(...choices.map((reason) => {
        const option = document.createElement('option')
        option.value = reason
        option.textContent = reason
        return option
      }))

      const selectedKey = normalizeReason(selectedReason)
      let visibleValue = choices.find((reason) => normalizeReason(reason) === selectedKey)
      // Compatibility: an old Group-5 alias is displayed as the requested
      // third Group-5 choice without silently changing the saved row.
      if (!visibleValue && letanGroupKey(selectedReason) === groupKey) visibleValue = choices[2]
      proxy.value = visibleValue || choices[0]
      proxy.disabled = Boolean(select.disabled)
      proxy.dataset.letanGroupKey = groupKey
      proxy.title = `${groupKey.replace('group-', 'Nhóm ')}: luôn có đúng 3 lựa chọn cho Lễ tân trong ngày hiện tại.`
      proxy.setAttribute('aria-label', `Lý do nghỉ, đúng 3 lựa chọn trong ${groupKey.replace('group-', 'Nhóm ')}`)
      row.dataset.letanGroupKey = groupKey
      select.dataset.letanGroupFiltered = 'true'
      return true
    }

    const lockSelectToPolicy = (select) => {
      if (!select || select.classList.contains('letan-three-choice-select')) return
      const row = select.closest('tr')
      if (!row) return

      const selectedReason = String(select.value || '').trim()
      const selectedInfo = reasonInfo(selectedReason)
      const selectedKey = normalizeReason(selectedReason)
      const recordDate = rowDateKey(row)
      const todayKey = localDateKey()

      if (isLetan && recordDate && recordDate < todayKey) {
        restoreAllOptions(select)
        select.disabled = true
        select.title = 'Lễ tân không được sửa đăng ký có ngày trước ngày hiện tại.'
        select.setAttribute('aria-label', 'Lý do nghỉ bị khóa vì đăng ký thuộc ngày trong quá khứ')
        return
      }

      if (isLetan && recordDate === todayKey) {
        const currentGroup = letanGroupKey(selectedReason)
        if (!row.dataset.letanGroupKey && currentGroup) row.dataset.letanGroupKey = currentGroup
        const lockedGroupKey = String(row.dataset.letanGroupKey || currentGroup || '').trim()
        if (!lockedGroupKey) {
          restoreAllOptions(select)
          select.disabled = true
          select.title = 'Lý do hiện tại không thuộc Nhóm 1–5 nên Lễ tân không được sửa trong ngày hiện tại.'
          return
        }

        ensureLetanThreeChoiceProxy(select, row, lockedGroupKey, selectedReason)
        select.removeAttribute('data-leave-type-filtered')
        select.title = `Lễ tân chỉ được đổi Lý do nghỉ trong cùng ${lockedGroupKey.replace('group-', 'Nhóm ')}; nhóm này luôn có đúng 3 lựa chọn.`
        return
      }

      removeLetanProxy(select)

      if (!row.dataset.leaveTypeKey && selectedInfo?.typeKey) {
        row.dataset.leaveTypeKey = selectedInfo.typeKey
        row.dataset.leaveTypeLabel = selectedInfo.leaveType
      }

      const lockedTypeKey = String(row.dataset.leaveTypeKey || '').trim()
      const lockedTypeLabel = String(row.dataset.leaveTypeLabel || selectedInfo?.leaveType || '').trim()
      if (!lockedTypeKey) {
        restoreNativeOptions(select)
        return
      }

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
      select.removeAttribute('data-letan-group-filtered')
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

        const reasonSelect = reasonCell.querySelector('select:not(.letan-three-choice-select)')
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

        const recordDate = rowDateKey(row)
        const checkbox = row.querySelector('.select-column input[type="checkbox"]')
        if (isLetan && checkbox && recordDate && recordDate <= localDateKey()) {
          checkbox.disabled = true
          checkbox.title = recordDate < localDateKey()
            ? 'Lễ tân không được xóa đăng ký của ngày trong quá khứ.'
            : 'Lễ tân không được xóa đăng ký của ngày hiện tại.'
        }

        if (reasonSelect) lockSelectToPolicy(reasonSelect)
      }
    }

    const scheduleSync = () => {
      if (scheduled) return
      scheduled = true
      window.requestAnimationFrame(syncTable)
    }

    const handleReasonOpen = (event) => {
      const select = event.target?.closest?.('.reason-edit-cell select:not(.letan-three-choice-select)')
      if (select) lockSelectToPolicy(select)
    }

    const handleReasonChange = (event) => {
      const select = event.target?.closest?.('.reason-edit-cell select:not(.letan-three-choice-select)')
      if (!select) return
      lockSelectToPolicy(select)
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
      for (const select of table?.querySelectorAll('.reason-edit-cell select:not(.letan-three-choice-select)') || []) restoreAllOptions(select)
    }
  }, [catalog, isLetan])

  return <style>{`
    .leave-records-table .leave-type-header,
    .leave-records-table .leave-type-cell{vertical-align:middle}
    .leave-records-table .leave-type-cell{min-width:110px;color:#31483d;font-weight:800;line-height:1.25}
    .leave-records-table .reason-edit-cell select[data-leave-type-filtered="true"]{border-color:#b8cbc0;background:#fbfdfc}
    .leave-records-table .reason-edit-cell .letan-native-reason-select{display:none!important}
    .leave-records-table .reason-edit-cell .letan-three-choice-select{width:100%;border-color:#96b7a5;background:#f4faf6;font-weight:800}
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
