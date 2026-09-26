import { Children } from 'react'
import './StableFeedback.css'

// Keep the slot even when there is no message. Long errors stay readable inside
// it rather than moving every control below the message after a save or retry.
export default function StableFeedback({ children, className = '' }) {
  const populated = Children.toArray(children).some(child => child !== '')
  return <div className={`stable-feedback ${className}`.trim()} role="region"
    aria-label="Thông báo thao tác" tabIndex={populated ? 0 : undefined}>
    {children}
  </div>
}
