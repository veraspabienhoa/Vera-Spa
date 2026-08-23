import { useEffect, useState } from 'react'
import AppShell from './components/AppShell'
import LoginPage from './pages/LoginPage'
import LeaveRegistrationPage from './pages/LeaveRegistrationPage'
import { veraApi } from './lib/api'
import { isSupabaseConfigured, supabase } from './lib/supabase'

export default function App() {
  const [session, setSession] = useState(null)
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(isSupabaseConfigured)
  const [authError, setAuthError] = useState('')
  const [demoUser, setDemoUser] = useState(null)
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
        if (mounted) setProfile(me)
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

  if (loading) return <div className="boot-screen">Đang mở VERA SPA Web V2…</div>

  const user = session?.user || demoUser
  if (!user) {
    return (
      <LoginPage
        externalError={authError}
        onDemoLogin={() => setDemoUser({ email: 'demo@veraspa.local', user_metadata: { full_name: 'Demo VERA' } })}
      />
    )
  }

  const signOut = async () => {
    setDemoUser(null)
    setProfile(null)
    if (supabase && session) await supabase.auth.signOut()
  }

  const shellUser = profile
    ? {
        ...user,
        employee_username: profile.employee_username,
        role: profile.role,
        user_metadata: {
          ...(user.user_metadata || {}),
          full_name: profile.full_name || profile.employee_username,
        },
      }
    : user

  return (
    <AppShell user={shellUser} currentPage={page} onPageChange={setPage} onSignOut={signOut}>
      {page === 'leave' && <LeaveRegistrationPage />}
    </AppShell>
  )
}
