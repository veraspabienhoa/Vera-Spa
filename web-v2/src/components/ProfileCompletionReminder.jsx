import { AlertTriangle, UserRoundPen, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { veraApi } from '../lib/api'
import { staffSecurityApi } from '../lib/staffSecurityApi'

const EXEMPT_ROLES = new Set(['admin', 'quanly'])
const REQUIRED_FIELDS = [
  ['full_name', 'Họ và tên đầy đủ'],
  ['birth_date', 'Ngày sinh'],
  ['phone', 'Điện thoại'],
  ['email', 'Email'],
  ['province', 'Tỉnh/Thành phố'],
  ['ward', 'Xã/Phường'],
  ['address_detail', 'Địa chỉ'],
  ['bank_account', 'Số tài khoản ngân hàng'],
  ['bank_name', 'Tên ngân hàng'],
]

const hasValue = (value) => String(value ?? '').trim() !== ''

function missingProfileFields(profile, identity) {
  const missing = REQUIRED_FIELDS
    .filter(([key]) => {
      if (key === 'address_detail') return !hasValue(profile?.address_detail || profile?.address)
      return !hasValue(profile?.[key])
    })
    .map(([, label]) => label)
  if (!identity?.front) missing.push('CCCD mặt trước')
  if (!identity?.back) missing.push('CCCD mặt sau')
  return missing
}

async function showSystemNotification(username, missing) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  const dateKey = new Date().toISOString().slice(0, 10)
  const signature = missing.join('|')
  const storageKey = `vera-profile-reminder:${username}:${dateKey}`
  if (window.localStorage.getItem(storageKey) === signature) return
  const body = `Hồ sơ còn thiếu: ${missing.join(', ')}. Vui lòng cập nhật Hồ sơ & Mật khẩu.`
  try {
    const registration = await navigator.serviceWorker?.ready
    if (registration?.showNotification) {
      await registration.showNotification('VERA SPA · Hồ sơ chưa đầy đủ', {
        body,
        tag: `vera-profile-incomplete-${username}`,
        renotify: false,
        icon: './icons/icon-192.png',
        badge: './icons/icon-192.png',
        data: { url: window.location.href, kind: 'profile-incomplete' },
      })
    } else {
      new Notification('VERA SPA · Hồ sơ chưa đầy đủ', { body, tag: `vera-profile-incomplete-${username}` })
    }
    window.localStorage.setItem(storageKey, signature)
  } catch {
    // Banner below remains the reliable in-app reminder if OS notification fails.
  }
}

export default function ProfileCompletionReminder({ user, onOpenProfile }) {
  const role = String(user?.role || '').trim().toLowerCase()
  const username = String(user?.employee_username || '').trim()
  const [missing, setMissing] = useState([])
  const [dismissed, setDismissed] = useState(false)

  const load = useCallback(async () => {
    if (!username || EXEMPT_ROLES.has(role)) {
      setMissing([])
      return
    }
    try {
      const [profileResult, identityResult] = await Promise.all([
        veraApi.profile(),
        staffSecurityApi.identityMetadata(username).catch(() => ({ front: null, back: null })),
      ])
      const nextMissing = missingProfileFields(profileResult?.profile || {}, identityResult || {})
      setMissing(nextMissing)
      setDismissed(false)
      if (nextMissing.length) void showSystemNotification(username, nextMissing)
    } catch {
      // Do not block the rest of the app if the reminder check cannot load.
    }
  }, [role, username])

  useEffect(() => {
    void load()
    const refresh = () => void load()
    window.addEventListener('vera-profile-updated', refresh)
    return () => window.removeEventListener('vera-profile-updated', refresh)
  }, [load])

  const text = useMemo(() => missing.join(', '), [missing])
  if (!missing.length || dismissed || EXEMPT_ROLES.has(role)) return null

  return <div className="profile-completion-reminder" role="status">
    <style>{`
      .profile-completion-reminder{display:flex;align-items:flex-start;gap:10px;margin:0 0 14px;padding:12px 14px;border:1px solid #ead39c;border-radius:13px;background:#fff8e8;color:#614815}
      .profile-completion-reminder>svg{flex:0 0 auto;margin-top:1px}.profile-completion-reminder-content{flex:1;min-width:0}.profile-completion-reminder strong{display:block;font-size:13px}.profile-completion-reminder p{margin:3px 0 0;font-size:12px;line-height:1.45;overflow-wrap:anywhere}.profile-completion-reminder-actions{display:flex;gap:7px;flex-wrap:wrap}
      @media(max-width:700px){.profile-completion-reminder{display:grid;grid-template-columns:auto 1fr}.profile-completion-reminder-actions{grid-column:1/-1}.profile-completion-reminder-actions button{flex:1}}
    `}</style>
    <AlertTriangle size={18} />
    <div className="profile-completion-reminder-content"><strong>HỒ SƠ CHƯA ĐẦY ĐỦ</strong><p>Còn thiếu: {text}. Hệ thống không tính “Thay đổi mật khẩu / Mật khẩu mới” là hồ sơ bắt buộc.</p></div>
    <div className="profile-completion-reminder-actions">
      <button type="button" className="primary-button compact" onClick={onOpenProfile}><UserRoundPen size={14}/> Cập nhật hồ sơ</button>
      <button type="button" className="secondary-button compact" onClick={() => setDismissed(true)}><X size={14}/> Đóng</button>
    </div>
  </div>
}
