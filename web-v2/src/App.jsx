import { useEffect, useState } from 'react'
import AppShell from './components/AppShell'
import LoginPage from './pages/LoginPage'
import LeaveRegistrationPage from './pages/LeaveRegistrationPage'
import EmployeePage from './pages/EmployeePage'
import RulesPage from './pages/RulesPage'
import ProfilePage from './pages/ProfilePage'
import PermissionsPage from './pages/PermissionsPage'
import PayrollPage from './pages/PayrollPage'
import SnapshotPage from './pages/SnapshotPage'
import AdminChangesPage from './pages/AdminChangesPage'
import StorageAdminPage from './pages/StorageAdminPage'
import BirthdayPage from './pages/BirthdayPage'
import TourPage from './pages/TourPage'
import LongLeaveSection from './components/LongLeaveSection'
import { veraApi } from './lib/api'
import { isSupabaseConfigured, supabase } from './lib/supabase'

export default function App() {
  const [session, setSession] = useState(null)
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(isSupabaseConfigured)
  const [authError, setAuthError] = useState('')
  const [page, setPage] = useState('leave')

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
      {page === 'leave' && <LeaveRegistrationPage user={shellUser} />}
      {page === 'long-leave' && <LongLeaveSection user={shellUser} />}
      {page === 'employees' && <EmployeePage user={shellUser} />}
      {page === 'rules' && <RulesPage user={shellUser} />}
      {page === 'profile' && <ProfilePage user={shellUser} forcePasswordChange={shellUser.must_change_password} onPasswordChanged={signOut} />}
      {page === 'permissions' && <PermissionsPage user={shellUser} />}
      {page === 'payroll' && <PayrollPage user={shellUser} />}
      {page === 'snapshot' && <SnapshotPage user={shellUser} />}
      {page === 'birthday' && <BirthdayPage />}
      {page === 'tour' && <TourPage user={shellUser} />}
      {page === 'changes' && <AdminChangesPage user={shellUser} />}
      {page === 'storage' && <StorageAdminPage />}
    </AppShell>
  )
}
