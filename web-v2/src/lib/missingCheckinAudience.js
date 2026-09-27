export const canSeeMissingCheckins = role => ['admin', 'letan', 'quanly'].includes(String(role || '').trim().toLowerCase())
