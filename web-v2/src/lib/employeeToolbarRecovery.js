function setReactInputValue(input, value) {
  if (!(input instanceof HTMLInputElement)) return
  const previous = input.value
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  if (setter) setter.call(input, value)
  else input.value = value
  const tracker = input._valueTracker
  if (tracker?.setValue) tracker.setValue(previous)
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

function restoreToolbarSelect(select) {
  if (!(select instanceof HTMLSelectElement)) return

  // The generic employee typing enhancer hides the React-owned <select> and
  // places an imperative proxy beside it. That proxy can get out of sync after
  // React rerenders the toolbar, leaving a visible default label while the
  // hidden filter state is different. The toolbar is more important than the
  // cosmetic proxy, so keep the real controlled select visible and interactive.
  const wrapper = select.__veraTypingWrapper
    || (select.nextElementSibling?.classList?.contains('vera-typing-select') ? select.nextElementSibling : null)
  if (wrapper) {
    wrapper.__veraTypingMenu?.remove?.()
    wrapper.remove()
  }
  select.__veraTypingWrapper = null
  select.classList.remove('vera-typing-select-source')

  // Leave the marker in place so employeeDirectoryUx will not hide the toolbar
  // select again on its periodic reconciliation. Native selects retain browser
  // type-ahead and are the most reliable controlled input on desktop/mobile.
  select.dataset.veraTypingSearch = '1'
}

function restoreToolbar() {
  const toolbar = document.querySelector('.staff-control-panel .staff-toolbar')
  if (!toolbar) return
  toolbar.querySelectorAll('select').forEach(restoreToolbarSelect)
}

function syncListSearchProxy(proxy) {
  if (!(proxy instanceof HTMLInputElement)) return
  const original = document.querySelector('.staff-control-panel .staff-search input')
  if (!(original instanceof HTMLInputElement)) return
  if (document.activeElement !== proxy && proxy.value !== original.value) proxy.value = original.value
}

export function startEmployeeToolbarRecovery() {
  if (window.__veraEmployeeToolbarRecoveryStarted) return
  window.__veraEmployeeToolbarRecoveryStarted = true

  const reconcile = () => {
    restoreToolbar()
    const proxy = document.querySelector('.staff-list-panel .vera-list-name-search input')
    syncListSearchProxy(proxy)
  }

  // Rewire the duplicate list search field to the current React-owned search
  // input on every keystroke. This avoids stale element closures after a list
  // refresh and keeps both search boxes on exactly the same filter state.
  document.addEventListener('input', (event) => {
    const target = event.target instanceof Element ? event.target : null
    const proxy = target?.closest('.staff-list-panel .vera-list-name-search input')
    if (!(proxy instanceof HTMLInputElement)) return
    const original = document.querySelector('.staff-control-panel .staff-search input')
    if (original instanceof HTMLInputElement) setReactInputValue(original, proxy.value)
  }, true)

  document.addEventListener('search', (event) => {
    const target = event.target instanceof Element ? event.target : null
    const proxy = target?.closest('.staff-list-panel .vera-list-name-search input')
    if (!(proxy instanceof HTMLInputElement)) return
    const original = document.querySelector('.staff-control-panel .staff-search input')
    if (original instanceof HTMLInputElement) setReactInputValue(original, proxy.value)
  }, true)

  const observer = new MutationObserver(() => window.requestAnimationFrame(reconcile))
  observer.observe(document.body, { childList: true, subtree: true })
  window.setInterval(reconcile, 800)
  window.requestAnimationFrame(reconcile)
}
