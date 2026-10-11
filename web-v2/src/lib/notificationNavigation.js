// Route only the server's leave-request category. Notification text and URLs
// are presentation data, not permission grants or arbitrary navigation targets.
export function notificationPage(notification, user) {
  if (notification?.payload?.kind !== 'long_leave_requests' || user?.must_change_password) return ''
  const canOpen = String(user?.role || '').toLowerCase() === 'admin'
    || ['long_leave', 'long_leave_form', 'long_leave_stats', 'resignation_form']
      .some(permission => user?.permissions?.[permission] === true)
  return canOpen ? 'long-leave' : ''
}
