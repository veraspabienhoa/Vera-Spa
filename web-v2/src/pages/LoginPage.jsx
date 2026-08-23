import { LockKeyhole, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { isSupabaseConfigured, supabase } from '../lib/supabase'

export default function LoginPage({ onDemoLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const demoAllowed = import.meta.env.VITE_VERA_DEMO_MODE === '1'

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    if (!isSupabaseConfigured || !supabase) {
      setError('Chưa cấu hình Supabase cho Web V2.')
      return
    }
    setBusy(true)
    try {
      const { data: bridge, error: bridgeError } = await supabase.functions.invoke('vera-v2-login', {
        body: { username: username.trim(), password },
      })
      if (bridgeError) {
        const detail = bridgeError?.context?.body?.message || bridgeError.message
        throw new Error(detail || 'Không xác thực được tài khoản VERA.')
      }
      if (!bridge?.email || !bridge?.password) throw new Error(bridge?.message || 'Không xác thực được tài khoản VERA.')

      const { error: signInError } = await supabase.auth.signInWithPassword({
        email: bridge.email,
        password: bridge.password,
      })
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
          <p>Web V2 dùng cùng tài khoản và mật khẩu VERA hiện tại. PostgreSQL/Supabase vẫn là dữ liệu trung tâm; nghiệp vụ ghi quan trọng tiếp tục được bảo vệ qua backend.</p>
        </div>
      </section>

      <section className="login-panel">
        <form className="login-card" onSubmit={submit}>
          <div className="login-icon"><LockKeyhole size={24} /></div>
          <h2>Đăng nhập VERA</h2>
          <p className="muted">Dùng đúng tên đăng nhập và mật khẩu đang sử dụng trên hệ thống hiện tại.</p>

          <label>Tên đăng nhập</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Tên nhân viên" autoComplete="username" required />

          <label>Mật khẩu</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" required />

          {error && <div className="error-box">{error}</div>}
          <button className="primary-button full" type="submit" disabled={busy}>{busy ? 'Đang xác thực…' : 'Đăng nhập'}</button>

          {!isSupabaseConfigured && <div className="setup-note">Supabase chưa được cấu hình cho bản deploy này.</div>}
          {demoAllowed && <button className="text-button" type="button" onClick={onDemoLogin}>Vào giao diện Demo</button>}
        </form>
      </section>
    </div>
  )
}
