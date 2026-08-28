import { lazy, Suspense, useEffect, useState } from 'react'
import AppShell from './components/AppShell'
import LongLeaveAdminPanel from './components/LongLeaveAdminPanel'
import LoginPage from './pages/LoginPage'
import LeaveListPersonalStats from './pages/LeaveListPersonalStats'
import LeaveRegistrationEnhancements from './pages/LeaveRegistrationEnhancements'
import EmployeeManagementEnhancements from './pages/EmployeeManagementEnhancements'
import { veraApi } from './lib/api'
import {
  claimCurrentDevice,
  clearFreshLoginClaim,
  hasFreshLoginClaim,
  installDeviceSessionGuard,
} from './lib/deviceSession'
import { isSupabaseConfigured, supabase } from './lib/supabase'

installDeviceSessionGuard()

const lazyPage = (importer) => lazy(async () => {
  try {
    const module = await importer()
    window.sessionStorage.removeItem('vera-v2-chunk-reload')
    return module
  } catch (error) {
    if (!window.sessionStorage.getItem('vera-v2-chunk-reload')) {
      window.sessionStorage.setItem('vera-v2-chunk-reload', '1')
      window.location.reload()
      return new Promise(() => {})
    }
    window.sessionStorage.removeItem('vera-v2-chunk-reload')
    throw error
  }
})

const LeaveRegistrationPage = lazyPage(() => import('./pages/LeaveRegistrationPage'))
const EmployeePage = lazyPage(() => import('./pages/EmployeePage'))
const RulesPage = lazyPage(() => import('./pages/RulesPage'))
const ProfilePage = lazyPage(() => import('./pages/ProfilePage'))
const PermissionsPage = lazyPage(() => import('./pages/PermissionsPage'))
const PayrollPage = lazyPage(() => import('./pages/PayrollPageV38'))
const SnapshotPage = lazyPage(() => import('./pages/SnapshotPage'))
const AdminChangesPage = lazyPage(() => import('./pages/AdminChangesPage'))
const StorageAdminPage = lazyPage(() => import('./pages/StorageAdminPage'))
const BirthdayPage = lazyPage(() => import('./pages/BirthdayPage'))
const TourPage = lazyPage(() => import('./pages/TourPage'))
const LongLeaveSection = lazyPage(() => import('./components/LongLeaveSection'))

export default function App() {
  const [session, setSession] = useState(null)
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(isSupabaseConfigured)
  const [authError, setAuthError] = useState('')
  const [page, setPage] = useState('leave')
  const [longLeaveRevision, setLongLeaveRevision] = useState(0)

  useEffect(() => {
    if (!supabase) return undefined
    const handleDeviceConflict = async (event) => {
      const message = event?.detail?.detail || 'Tài khoản này đã đăng nhập trên thiết bị khác.'
      setAuthError(message)
      setProfile(null)
      setSession(null)
      clearFreshLoginClaim()
      await supabase.auth.signOut().catch(() => {})
    }
    window.addEventListener('vera-device-conflict', handleDeviceConflict)
    return () => window.removeEventListener('vera-device-conflict', handleDeviceConflict)
  }, [])

  useEffect(() => {
    if (!supabase) return undefined
    let mounted = true

    const applySession = async (nextSession) => {
      if (!mounted) return
      setSession(nextSession)
      setAuthError('')
      if (!nextSession) {
        setProfile(null)
        setLoading(false)
        return
      }
      try {
        if (hasFreshLoginClaim()) {
          try {
            await claimCurrentDevice(nextSession)
          } finally {
            clearFreshLoginClaim()
          }
        }
        const me = await veraApi.me()
        if (!me?.employee_username || me?.is_active === false) {
          throw new Error('Tài khoản chưa được liên kết với nhân viên VERA đang hoạt động.')
        }
        if (mounted) {
          setProfile(me)
          if (me.must_change_password) setPage('profile')
        }
      } catch (err) {
        if (mounted) {
          setProfile(null)
          setAuthError(err.message || 'Không xác minh được hồ sơ VERA.')
          await supabase.auth.signOut().catch(() => {})
          setSession(null)
        }
      } finally {
        if (mounted) setLoading(false)
      }
    }

    supabase.auth.getSession().then(({ data }) => applySession(data.session))
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      applySession(nextSession)
    })

    return () => {
      mounted = false
      listener.subscription.unsubscribe()
    }
  }, [])

  if (loading) return <div className="boot-screen">Đang mở VERA SPA…</div>

  const user = session?.user
  if (!user) {
    return <LoginPage externalError={authError} />
  }

  const signOut = async () => {
    clearFreshLoginClaim()
    setProfile(null)
    if (supabase && session) await supabase.auth.signOut()
  }

  const shellUser = profile
    ? {
        ...user,
        employee_username: profile.employee_username,
        role: profile.role,
        permissions: profile.permissions || {},
        registration_locked: Boolean(profile.registration_locked),
        must_change_password: Boolean(profile.must_change_password),
        user_metadata: {
          ...(user.user_metadata || {}),
          full_name: profile.full_name || profile.employee_username,
        },
      }
    : null

  if (!shellUser) return <div className="boot-screen">Đang xác minh hồ sơ VERA SPA…</div>

  return (
    <AppShell user={shellUser} currentPage={page} onPageChange={setPage} onSignOut={signOut}>
      <Suspense fallback={<div className="page-loading" role="status">Đang mở chức năng…</div>}>
        {page === 'leave' && <>
          <LeaveRegistrationPage user={shellUser} />
          <LeaveRegistrationEnhancements user={shellUser} />
          <LeaveListPersonalStats user={shellUser} />
        </>}
        {page === 'long-leave' && <>
          <LongLeaveAdminPanel user={shellUser} onChanged={() => setLongLeaveRevision((value) => value + 1)} />
          <LongLeaveSection key={longLeaveRevision} user={shellUser} />
        </>}
        {page === 'employees' && <>
          <EmployeePage user={shellUser} />
          <EmployeeManagementEnhancements user={shellUser} />
        </>}
        {page === 'rules' && <RulesPage user={shellUser} />}
        {page === 'profile' && <ProfilePage user={shellUser} forcePasswordChange={shellUser.must_change_password} onPasswordChanged={signOut} />}
        {page === 'permissions' && <PermissionsPage user={shellUser} />}
        {page === 'payroll' && <PayrollPage user={shellUser} />}
        {page === 'snapshot' && <SnapshotPage user={shellUser} />}
        {page === 'birthday' && <BirthdayPage />}
        {page === 'tour' && <TourPage user={shellUser} />}
        {page === 'changes' && <AdminChangesPage user={shellUser} />}
        {page === 'storage' && <StorageAdminPage />}
      </Suspense>
    </AppShell>
  )
}
