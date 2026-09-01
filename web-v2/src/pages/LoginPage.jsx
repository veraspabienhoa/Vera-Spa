import { Eye, EyeOff, LockKeyhole } from 'lucide-react'
import { useEffect, useState } from 'react'
import { isSupabaseConfigured, supabase } from '../lib/supabase'
import { unlockWatchBellAudio } from '../lib/watchBell'

export default function LoginPage({ externalError = '' }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(externalError)
  useEffect(() => { if (externalError) setError(externalError) }, [externalError])

  const submit = async (event) => {
    event.preventDefault()
    void unlockWatchBellAudio()
    setError('')
    if (!isSupabaseConfigured || !supabase) {
      setError('Chưa cấu hình Supabase cho hệ thống.')
      return
    }
    setBusy(true)
    try {
      const { data: bridge, error: bridgeError } = await supabase.functions.invoke('vera-v2-login', {
        body: { username: username.trim(), password },
      })
      if (bridgeError) {
        let detail = bridgeError.message
        try {
          const responseBody = await bridgeError.context?.json?.()
          detail = responseBody?.message || detail
        } catch {
          // Keep the SDK error message when the Edge Function response has no JSON body.
        }
        throw new Error(detail || 'Không xác thực được tài khoản VERA.')
      }
      if (!bridge?.email || !bridge?.password) throw new Error(bridge?.message || 'Không xác thực được tài khoản VERA.')

      const { error: signInError } = await supabase.auth.signInWithPassword({
        email: bridge.email,
        password: bridge.password,
      })
      if (signInError) throw signInError
      setPassword('')
      setShowPassword(false)
    } catch (err) {
      setError(err.message || 'Đăng nhập thất bại.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-screen">
      <style>{`
        .login-password-control{position:relative;width:100%}
        .login-password-control input{width:100%;padding-right:46px}
        .login-password-eye{position:absolute;right:8px;top:50%;transform:translateY(-50%);width:34px;height:34px;display:grid;place-items:center;border:0;border-radius:9px;background:transparent;color:#52645b}
        .login-password-eye:hover{background:#edf3ef;color:#173329}
      `}</style>
      <section className="login-visual">
        <div className="visual-glow one" />
        <div className="visual-glow two" />
        <div className="login-brand-row">
          <div className="brand-mark large">VERA</div>
          <div>
            <div className="brand-name large-text">SPA</div>
          </div>
        </div>
        <div className="login-pitch">
          <h1>
            <span>Suối nguồn thư giãn</span>
            <span>Trọn vẹn an yên</span>
          </h1>
          <div className="login-contact">
            <p><span aria-hidden="true">🏠</span> 193 Trương Định, Tam Hiệp, Đồng Nai</p>
            <p><span aria-hidden="true">☎️</span> Hotline: 0833.22.99.39</p>
            <a
              href="https://maps.app.goo.gl/kkQjkTT7vm9oDWjbA?g_st=ic"
              target="_blank"
              rel="noopener noreferrer"
              className="map-button"
            >
              <span aria-hidden="true">📍</span>
              Xem vị trí trên Google Maps
            </a>
          </div>
        </div>
      </section>

      <section className="login-panel">
        <form className="login-card" onSubmit={submit}>
          <div className="login-icon"><LockKeyhole size={24} /></div>
          <h2>Đăng nhập VERA SPA</h2>
          <p className="muted">Dùng đúng tên đăng nhập và mật khẩu đang sử dụng trên hệ thống hiện tại.</p>

          <label>Tên đăng nhập</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Tên nhân viên" autoComplete="username" required />

          <label>Mật khẩu</label>
          <div className="login-password-control">
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
            />
            <button
              type="button"
              className="login-password-eye"
              onClick={() => setShowPassword((value) => !value)}
              aria-label={showPassword ? 'Ẩn mật khẩu' : 'Xem mật khẩu'}
              title={showPassword ? 'Ẩn mật khẩu' : 'Xem mật khẩu'}
            >
              {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>

          {error && <div className="error-box">{error}</div>}
          <button className="primary-button full" type="submit" disabled={busy}>{busy ? 'Đang xác thực…' : 'Đăng nhập'}</button>

          {!isSupabaseConfigured && <div className="setup-note">Supabase chưa được cấu hình cho bản deploy này.</div>}
        </form>
      </section>
    </div>
  )
}
