import { ArrowUp } from 'lucide-react'
import './BackToTop.css'
export default function BackToTop() {
  const go = () => {
    const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'
    window.scrollTo({ top: 0, behavior })
    document.querySelectorAll('main, .page-wrap, .live-tour-workspace, .live-tour-page').forEach(node => node.scrollTo?.({ top: 0, behavior }))
  }
  return <button type="button" className="back-to-top" onClick={go} aria-label="Về đầu trang" title="Về đầu trang"><ArrowUp size={18}/>Về đầu trang</button>
}
