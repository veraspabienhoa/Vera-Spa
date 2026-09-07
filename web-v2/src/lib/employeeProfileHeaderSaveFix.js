const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim()

function realProfileSaveButton(topButton) {
  const panel = topButton?.closest?.('.staff-form-panel')
  if (!panel) return null
  return Array.from(panel.querySelectorAll('button')).find((button) => (
    button !== topButton
    && !button.classList.contains('vera-profile-save-top')
    && /^Lưu hồ sơ$/i.test(clean(button.textContent))
  )) || null
}

export function startEmployeeProfileHeaderSaveFix() {
  if (window.__veraEmployeeProfileHeaderSaveFixStarted) return
  window.__veraEmployeeProfileHeaderSaveFixStarted = true

  document.addEventListener('click', (event) => {
    const topButton = event.target?.closest?.('.vera-profile-save-top')
    if (!topButton) return

    // The header button is injected outside React. Intercept it before its old
    // proxy handler runs, then delegate to the real React-owned Save button.
    // This keeps the current profile draft/state intact and guarantees that the
    // same saveProfile handler used by the footer button is executed.
    event.preventDefault()
    event.stopImmediatePropagation()

    const saveButton = realProfileSaveButton(topButton)
    if (!saveButton || saveButton.disabled) return
    saveButton.click()
  }, true)
}
