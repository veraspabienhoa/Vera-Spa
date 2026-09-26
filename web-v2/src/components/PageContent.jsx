import { memo } from 'react'
// Shell clocks, notification counts and drag feedback must not render business tables.
export default memo(function PageContent({ children, navigationToggle }) {
  return typeof children === 'function' ? children(navigationToggle) : children
})
