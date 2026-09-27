export const canSeeMissingCheckins = role => ['admin', 'letan', 'quanly', 'leader', 'nhanvien', 'locker', 'tapvu', 'support'].includes(String(role || '').trim().toLowerCase())
