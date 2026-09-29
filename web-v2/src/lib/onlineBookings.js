export const canViewOnlineBookings = user => !user?.must_change_password && ['admin', 'quanly', 'letan'].includes(user?.role)
