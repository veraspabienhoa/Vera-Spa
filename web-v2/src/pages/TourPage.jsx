import { Compass, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { veraApi } from '../lib/api'

export default function TourPage({ user }) {
  const [data, setData] = useState({ columns: [], records: [] })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = async (refresh = false) => {
    setBusy(true); setError('')
    try { setData(await veraApi.tour(refresh)) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  useEffect(() => { void load(false) }, [])
  return <div className="feature-page">
    <div className="page-heading"><div><span className="eyebrow"><Compass size={14} /> Vận hành</span><h1>BẢNG TOUR</h1><p>Dữ liệu chỉ đọc từ file TourVera; làm mới tự động tối đa mỗi 5 phút.</p></div>{user?.permissions?.tour_refresh && <button className="secondary-button" onClick={() => load(true)} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới Bảng tour</button>}</div>
    {error && <div className="error-box">{error}</div>}
    <div className="metric-grid small"><div className="metric-card"><span>Số dòng tour</span><strong>{data.count || 0}</strong></div><div className="metric-card"><span>Có thể lên tour</span><strong>{data.available || 0}</strong></div></div>
    <section className="panel"><div className="responsive-data-table tour-table"><table><thead><tr>{data.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{data.records.map((item, index) => <tr key={index}>{data.columns.map((column) => <td key={column}>{String(item[column] ?? '')}</td>)}</tr>)}</tbody></table></div>{!busy && !data.records.length && <div className="setup-note">Bảng tour hiện chưa có dữ liệu.</div>}</section>
  </div>
}
