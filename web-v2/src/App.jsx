import { useEffect, useState } from 'react'
import AppShell from './components/AppShell'
import LoginPage from './pages/LoginPage'
import LeaveRegistrationPage from './pages/LeaveRegistrationPage'
import { isSupabaseConfigured, supabase } from './lib/supabase'

export default function App() {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(isSupabaseConfigured)
  const [demoUser, setDemoUser] = useState(null)
  const [page, setPage] = useState('leave')

  useEffect(() => {
    if (!supabase) return undefined
    let mounted = true
    supabase.auth.getSession().then(({ data }) => {
      if (mounted) {
        setSession(data.session)
        setLoading(false)
      }
    })
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession)
      setLoading(false)
    })
    return () => {
      mounted = false
      listener.subscription.unsubscribe()
    }
  }, [])

  if (loading) return <div className="boot-screen">Đang mở VERA SPA Web V2…</div>

  const user = session?.user || demoUser
  if (!user) return <LoginPage onDemoLogin={() => setDemoUser({ email: 'demo@veraspa.local', user_metadata: { full_name: 'Demo VERA' } })} />

  const signOut = async () => {
    setDemoUser(null)
    if (supabase && session) await supabase.auth.signOut()
  }

  return (
    <AppShell user={user} currentPage={page} onPageChange={setPage} onSignOut={signOut}>
      {page === 'leave' && <LeaveRegistrationPage />}
    </AppShell>
  )
}
