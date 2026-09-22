import { useLayoutEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import useDialogFocus from '../lib/useDialogFocus'
import { fitTransaction, transactionViewport } from '../lib/transactionViewport'
import './LiveTourTransactionDialog.css'

export default function LiveTourTransactionDialog({ title, children, onClose, busy = false, className = '' }) {
  const dialogRef = useDialogFocus(() => { if (!busy) onClose() })
  const frameRef = useRef(null)
  const [view, setView] = useState(() => transactionViewport())
  const paymentDialog = className.split(/\s+/).includes('tour-payment-dialog')
  const mobileFullscreen = paymentDialog && (view.width <= 700 || (view.width <= 900 && view.height <= 500))
  const width = mobileFullscreen ? Math.max(1, view.width) : Math.min(1040, Math.max(1, view.width - 16))

  useLayoutEffect(() => {
    const update = () => setView(transactionViewport())
    window.addEventListener('resize', update)
    window.visualViewport?.addEventListener('resize', update)
    window.visualViewport?.addEventListener('scroll', update)
    const root = document.documentElement
    const oldOverflow = root.style.overflow
    const oldBodyOverflow = document.body.style.overflow
    root.style.overflow = 'hidden'
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('resize', update)
      window.visualViewport?.removeEventListener('resize', update)
      window.visualViewport?.removeEventListener('scroll', update)
      root.style.overflow = oldOverflow
      document.body.style.overflow = oldBodyOverflow
    }
  }, [])

  useLayoutEffect(() => {
    const dialog = dialogRef.current, frame = frameRef.current
    const fit = () => {
      if (!dialog || !frame) return
      if (mobileFullscreen) {
        dialog.style.transform = 'none'
        frame.style.width = `${view.width}px`
        frame.style.height = `${view.height}px`
        frame.dataset.scale = '1'
        return
      }
      // Measure the complete unscaled form. Never conceal fields with a fixed
      // max-height; rotation, keyboard and validation messages refit the frame.
      const size = fitTransaction(view, Math.max(width, dialog.scrollWidth), dialog.offsetHeight)
      dialog.style.transform = `scale(${size.scale})`
      frame.style.width = `${size.width}px`
      frame.style.height = `${size.height}px`
      frame.dataset.scale = String(size.scale)
    }
    fit()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(fit)
    observer?.observe(dialog)
    return () => observer?.disconnect()
  }, [view, width, children, dialogRef, mobileFullscreen])

  return <div className={`live-tour-modal-backdrop tour-transaction-backdrop${mobileFullscreen ? ' tour-payment-backdrop-fullscreen' : ''}`}
    style={{ left: view.left, top: view.top, width: view.width, height: view.height }}
    onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose() }}>
    <div ref={frameRef} className="tour-transaction-frame">
      <section data-ui-key="u-28ee347d7e54" ref={dialogRef} tabIndex="-1" role="dialog" aria-modal="true" aria-label={title}
        className={`live-tour-modal tour-transaction-dialog ${className}`} style={{ width }}>
        <div className="live-tour-modal-head"><strong>{title}</strong><button data-ui-key="u-b59b73812d19" type="button" className="icon-button" aria-label="Đóng" disabled={busy} onClick={onClose}><X size={18}/></button></div>
        {children}
      </section>
    </div>
  </div>
}
