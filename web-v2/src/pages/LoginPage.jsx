import { LockKeyhole, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { isSupabaseConfigured, supabase } from '../lib/supabase'

export default function LoginPage({ onDemoLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const demoAllowed = import.meta.env.VITE_VERA_DEMO_MODE === '1'

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    if (!isSupabaseConfigured) {
      setError('Chưa cấu hình Supabase cho Web V2.')
      return
    }
    setBusy(true)
    try {
      const { error: signInError } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
      if (signInError) throw signInError
    } catch (err) {
      setError(err.message || 'Đăng nhập thất bại.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-screen">
      <section className="login-visual">
        <div className="visual-glow one" />
        <div className="visual-glow two" />
        <div className="login-brand-row">
          <div className="brand-mark large">V</div>
          <div>
            <div className="brand-name large-text">VERA SPA</div>
            <div className="brand-subtitle">Web V2 · React + Supabase</div>
          </div>
        </div>
        <div className="login-pitch">
          <span className="eyebrow"><Sparkles size={15} /> Trải nghiệm mới</span>
          <h1>Nhanh hơn, mượt hơn, không làm gián đoạn hệ thống hiện tại.</h1>
          <p>Web V2 được xây song song với Streamlit. PostgreSQL/Supabase vẫn là dữ liệu trung tâm và nghiệp vụ quan trọng tiếp tục đi qua Python API.</p>
        </div>
      </section>

      <section className="login-panel">
        <form className="login-card" onSubmit={submit}>
          <div className="login-icon"><LockKeyhole size={24} /></div>
          <h2>Đăng nhập VERA</h2>
          <p className="muted">Tài khoản Supabase Auth dành cho Web V2.</p>

          <label>Email</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@veraspa.vn" autoComplete="username" />

          <label>Mật khẩu</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" />

          {error && <div className="error-box">{error}</div>}
          <button className="primary-button full" type="submit" disabled={busy}>{busy ? 'Đang đăng nhập…' : 'Đăng nhập'}</button>

          {!isSupabaseConfigured && <div className="setup-note">Cần đặt VITE_SUPABASE_URL và VITE_SUPABASE_ANON_KEY trong môi trường deploy.</div>}
          {demoAllowed && <button className="text-button" type="button" onClick={onDemoLogin}>Vào giao diện Demo</button>}
        </form>
      </section>
    </div>
  )
}
