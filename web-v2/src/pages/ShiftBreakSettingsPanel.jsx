import { Clock3, RefreshCw, Save } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

async function apiRequest(path, options = {}) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers(options.headers || {})
  headers.set('Content-Type', 'application/json')
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const response = await fetch(`${apiBase}${path}`, { ...options, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

function numberValue(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

export default function ShiftBreakSettingsPanel() {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [shifts, setShifts] = useState([])
  const [departments, setDepartments] = useState([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const result = await apiRequest('/v2/staff/shift-break-settings')
      setShifts(Array.isArray(result.shifts) ? result.shifts : [])
      setDepartments(Array.isArray(result.departments) ? result.departments : [])
    } catch (err) {
      setError(err.message || 'Không tải được cài đặt nghỉ giữa ca.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open && !shifts.length && !loading) void load()
  }, [load, loading, open, shifts.length])

  const updateShift = (id, field, value) => {
    setShifts((current) => current.map((row) => row.id === id ? { ...row, [field]: value } : row))
  }

  const updateDepartment = (name, field, value) => {
    setDepartments((current) => current.map((row) => row.department === name ? { ...row, [field]: value } : row))
  }

  const save = async () => {
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const body = {
        shifts: shifts.map((row) => ({
          id: row.id,
          enabled: Boolean(row.enabled),
          duration_minutes: Math.max(0, Math.min(360, Math.round(numberValue(row.duration_minutes, 0)))),
          faceid_cluster_minutes: Math.max(1, Math.min(60, Math.round(numberValue(row.faceid_cluster_minutes, 10)))),
        })),
        departments: departments.map((row) => ({
          department: row.department,
          enabled: Boolean(row.enabled),
          duration_minutes: Math.max(0, Math.min(360, Math.round(numberValue(row.duration_minutes, 0)))),
        })),
      }
      const result = await apiRequest('/v2/staff/shift-break-settings', {
        method: 'PUT',
        body: JSON.stringify(body),
      })
      setMessage(result.message || 'Đã lưu cài đặt nghỉ giữa ca.')
      await load()
    } catch (err) {
      setError(err.message || 'Không lưu được cài đặt nghỉ giữa ca.')
    } finally {
      setSaving(false)
    }
  }

  const activeCount = useMemo(() => shifts.filter((row) => row.enabled).length, [shifts])

  return <section className="panel shift-break-settings-panel">
    <style>{`
      .shift-break-settings-panel{margin:14px 0}
      .shift-break-settings-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
      .shift-break-settings-title{display:flex;align-items:center;gap:9px}
      .shift-break-settings-title h2{margin:0;font-size:1rem}
      .shift-break-settings-title p{margin:3px 0 0;color:#6c746f;font-size:.82rem}
      .shift-break-actions{display:flex;gap:8px;flex-wrap:wrap}
      .shift-break-body{margin-top:14px;display:grid;gap:14px}
      .shift-break-subtitle{font-weight:900;font-size:.86rem;margin-bottom:8px}
      .shift-break-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
      .shift-break-card{border:1px solid #dde5df;border-radius:12px;padding:10px;background:#fbfdfb;display:grid;gap:8px}
      .shift-break-card strong{font-size:.9rem}
      .shift-break-card small{color:#6c746f;min-height:1.2em}
      .shift-break-field{display:grid;gap:4px;font-size:.76rem;font-weight:800;color:#526059}
      .shift-break-field input[type="number"]{width:100%;min-width:0;border:1px solid #d7e0da;border-radius:8px;padding:7px 8px;background:white}
      .shift-break-toggle{display:flex;align-items:center;gap:7px;font-size:.78rem;font-weight:900}
      .shift-break-message{padding:8px 10px;border-radius:9px;font-size:.82rem;background:#eaf7ee;color:#1f6845}
      .shift-break-error{padding:8px 10px;border-radius:9px;font-size:.82rem;background:#fff0f0;color:#a52828}
      @media(max-width:900px){.shift-break-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
      @media(max-width:560px){.shift-break-grid{grid-template-columns:1fr}.shift-break-settings-head{align-items:flex-start}.shift-break-actions{width:100%}.shift-break-actions button{flex:1}}
    `}</style>
    <div className="shift-break-settings-head">
      <div className="shift-break-settings-title">
        <Clock3 size={19} />
        <div>
          <h2>CÀI ĐẶT NGHỈ GIỮA CA</h2>
          <p>Admin cài theo từng ca. Chấm công dùng thời lượng này để so sánh với FaceID nghỉ thực tế.</p>
        </div>
      </div>
      <div className="shift-break-actions">
        <button type="button" className="secondary-button" onClick={() => setOpen((value) => !value)}>{open ? 'Thu gọn' : `Cài đặt (${activeCount || '...'})`}</button>
        {open && <button type="button" className="secondary-button" onClick={load} disabled={loading || saving}><RefreshCw size={15} className={loading ? 'spin' : ''} /> Làm mới</button>}
        {open && <button type="button" className="primary-button" onClick={save} disabled={loading || saving}><Save size={15} /> {saving ? 'Đang lưu...' : 'Lưu nghỉ giữa ca'}</button>}
      </div>
    </div>

    {open && <div className="shift-break-body">
      {error && <div className="shift-break-error">{error}</div>}
      {message && <div className="shift-break-message">{message}</div>}

      <div>
        <div className="shift-break-subtitle">THEO TỪNG CA</div>
        {loading && !shifts.length ? <div className="setup-note">Đang tải cấu hình ca...</div> : <div className="shift-break-grid">
          {shifts.map((row) => <div className="shift-break-card" key={row.id}>
            <div><strong>{row.name || row.id}</strong><br /><small>{row.department}{row.start || row.end ? ` · ${row.start || '--:--'}–${row.end || '--:--'}` : ''}</small></div>
            <label className="shift-break-toggle"><input type="checkbox" checked={Boolean(row.enabled)} onChange={(event) => updateShift(row.id, 'enabled', event.target.checked)} /> Áp dụng nghỉ giữa ca</label>
            <label className="shift-break-field">Thời lượng nghỉ (phút)<input type="number" min="0" max="360" step="5" value={row.duration_minutes ?? 0} onChange={(event) => updateShift(row.id, 'duration_minutes', event.target.value)} /></label>
            <label className="shift-break-field">Khoảng gom FaceID (phút)<input type="number" min="1" max="60" step="1" value={row.faceid_cluster_minutes ?? 10} onChange={(event) => updateShift(row.id, 'faceid_cluster_minutes', event.target.value)} /></label>
          </div>)}
          {!shifts.length && !loading && <div className="setup-note">Chưa có ca đang dùng để cài nghỉ giữa ca.</div>}
        </div>}
      </div>

      <details>
        <summary className="shift-break-subtitle">MẶC ĐỊNH THEO BỘ PHẬN (dùng khi TimeSoft không khớp tên ca)</summary>
        <div className="shift-break-grid" style={{ marginTop: 8 }}>
          {departments.map((row) => <div className="shift-break-card" key={row.department}>
            <strong>{row.department}</strong>
            <label className="shift-break-toggle"><input type="checkbox" checked={Boolean(row.enabled)} onChange={(event) => updateDepartment(row.department, 'enabled', event.target.checked)} /> Áp dụng mặc định</label>
            <label className="shift-break-field">Thời lượng nghỉ (phút)<input type="number" min="0" max="360" step="5" value={row.duration_minutes ?? 0} onChange={(event) => updateDepartment(row.department, 'duration_minutes', event.target.value)} /></label>
          </div>)}
        </div>
      </details>
    </div>}
  </section>
}
