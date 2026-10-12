export const canViewOnlineBookings = user => !user?.must_change_password && ['admin', 'quanly', 'letan', 'locker'].includes(user?.role)
export const canEditOnlineBookings = user => !user?.must_change_password && ['admin', 'quanly', 'letan'].includes(user?.role)
