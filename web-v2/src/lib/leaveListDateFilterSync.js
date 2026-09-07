function localDateValue(offsetDays = 0) {
  const date = new Date()
  date.setDate(date.getDate() + offsetDays)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function setReactDateValue(input, value) {
  if (!(input instanceof HTMLInputElement) || input.value === value) return
  const previous = input.value
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  if (setter) setter.call(input, value)
  else input.value = value

  // React tracks controlled input values internally. Reset the tracker to the
  // previous value so the synthetic change event is always observed.
  const tracker = input._valueTracker
  if (tracker?.setValue) tracker.setValue(previous)
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

export function startLeaveListDateFilterSync() {
  if (window.__veraLeaveListDateFilterSyncStarted) return
  window.__veraLeaveListDateFilterSyncStarted = true

  // Run in capture phase, before LeaveRegistrationPage's React onClick. This
  // makes `date` follow Hôm qua/Hôm nay first; the original React handler then
  // keeps the selected list filter and range. As a result edit permissions and
  // the reason catalog are correct immediately, without an F5 refresh.
  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target : null
    const button = target?.closest('.leave-list-panel .range-filter-buttons[aria-label="Lọc thời gian danh sách"] button')
    if (!button) return

    const label = String(button.textContent || '').replace(/\s+/g, ' ').trim()
    const offset = label === 'Hôm nay' ? 0 : label === 'Hôm qua' ? -1 : null
    if (offset === null) return

    const viewedDateInput = document.querySelector('.viewed-date-toolbar .date-picker-native')
    setReactDateValue(viewedDateInput, localDateValue(offset))
  }, true)
}
