import { Children } from 'react'
import './StableFeedback.css'

// Empty feedback must not reserve a row in the shell or page layout. Keep the
// same wrapper so a message update does not remount neighbouring forms/tables.
export default function StableFeedback({ children, className = '' }) {
  const populated = Children.toArray(children).some(child => child !== '')
  return <div className={`stable-feedback ${className}`.trim()} hidden={!populated} role="region"
    aria-label="Thông báo thao tác" tabIndex={populated ? 0 : undefined}>
    {children}
  </div>
}
