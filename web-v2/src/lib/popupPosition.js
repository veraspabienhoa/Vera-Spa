export function clampPopupPosition(position, size, viewport) {
  return {
    left: Math.max(8, Math.min(position.left, Math.max(8, viewport.width - size.width - 8))),
    top: Math.max(8, Math.min(position.top, Math.max(8, viewport.height - size.height - 8))),
  }
}
