export function transactionViewport(win = window) {
  const view = win.visualViewport
  return { width: view?.width || win.innerWidth, height: view?.height || win.innerHeight,
    left: view?.offsetLeft || 0, top: view?.offsetTop || 0 }
}

export function fitTransaction(view, contentWidth, contentHeight) {
  const width = Math.max(1, view.width - 16)
  const height = Math.max(1, view.height - 16)
  const scale = Math.min(1, width / Math.max(1, contentWidth), height / Math.max(1, contentHeight))
  return { scale, width: contentWidth * scale, height: contentHeight * scale }
}
