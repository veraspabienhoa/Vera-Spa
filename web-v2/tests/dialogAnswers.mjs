// Existing business fixtures choose yes/no using a browser stub. Drive the real
// asynchronous modal with that same choice, instead of bypassing its UI.
export function answerDialogs(window) {
  const handled = new WeakSet()
  const observer = new window.MutationObserver(() => {
    if (!window.document) { observer.disconnect(); return }
    for (const dialog of window.document.querySelectorAll('dialog[data-system-dialog]')) {
      if (handled.has(dialog)) continue
      const kind = dialog.dataset.systemDialog
      if (!['confirm', 'prompt'].includes(kind)) continue
      handled.add(dialog)
      const message = dialog.querySelector('.system-dialog-message')?.textContent
      const answer = kind === 'confirm' ? window.confirm(message) : window.prompt(message, dialog.querySelector('input').value)
      if (kind === 'prompt' && answer !== null) dialog.querySelector('input').value = answer
      const accept = kind === 'confirm' ? answer : answer !== null
      dialog.querySelector(accept ? '.primary-button' : '.secondary-button').click()
    }
  })
  observer.observe(window.document.body, { childList: true, subtree: true })
  return () => observer.disconnect()
}
