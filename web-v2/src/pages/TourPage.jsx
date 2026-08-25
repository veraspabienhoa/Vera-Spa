import { Compass, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { veraApi } from '../lib/api'

export default function TourPage({ user }) {
  const [data, setData] = useState({ columns: [], records: [], stats: [] })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = useCallback(async (refresh = false, quiet = false) => {
    if (!quiet) setBusy(true)
    setError('')
    try { setData(await veraApi.tour(refresh)) } catch (err) { setError(err.message) } finally { if (!quiet) setBusy(false) }
  }, [])
  useEffect(() => {
    void load(false)
    const interval = window.setInterval(() => { void load(false, true) }, 30000)
    return () => window.clearInterval(interval)
  }, [load])
  return <div className="feature-page">
    <div className="page-heading"><div><span className="eyebrow"><Compass size={14} /> Vận hành</span><h1>BẢNG TUA</h1><p>Countdown cập nhật mỗi 30 giây; file TourVera được đọc lại tối đa mỗi 5 phút.</p></div>{user?.permissions?.tour_refresh && <button className="secondary-button" onClick={() => load(true)} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới Bảng tua</button>}</div>
    {error && <div className="error-box">{error}</div>}
    {data.countdown_error && <div className="warning-box">Countdown Bảng tua: {data.countdown_error}</div>}
    <div className="metric-grid small tour-metrics"><div className="metric-card"><span>Số dòng tua</span><strong>{data.count || 0}</strong></div><div className="metric-card tour-available-metric"><span>Có thể lên tour</span><strong>{data.available || 0}</strong></div><div className="metric-card"><span>Đi làm</span><strong>{data.working_count || 0}</strong></div><div className="metric-card tour-break-metric"><span>Break</span><strong>{data.break_count || 0}</strong></div></div>
    {data.viewer_can_see_stats && <section className="panel tour-stats-panel"><div className="panel-title-row"><div><h2>CHỈ SỐ</h2><p>Tính trực tiếp từ trạng thái, thời gian còn lại, Đi làm và Vào ca.</p></div></div><div className="responsive-data-table"><table><thead><tr><th>Chỉ số</th><th className="center">Số lượng</th><th>Cách tính</th></tr></thead><tbody>{(data.stats || []).map((item) => <tr className="tour-stat-available" key={item.label}><td><strong>{item.label}</strong></td><td className="center"><strong>{item.value}</strong></td><td>{item.detail}</td></tr>)}</tbody></table></div></section>}
    <section className="panel tour-table-panel"><div className="responsive-data-table tour-table"><table><thead><tr>{data.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{data.records.map((item, index) => <tr className={`tour-row-${item._row_style || 'default'}`} key={index}>{data.columns.map((column) => <td key={column}>{String(item[column] ?? '')}</td>)}</tr>)}</tbody></table></div>{!busy && !data.records.length && <div className="setup-note">Bảng tua hiện chưa có dữ liệu.</div>}</section>
    <section className="panel tour-legend"><div className="panel-title-row"><div><h2>MÀU DÒNG</h2><p>Màu áp dụng cho toàn bộ dòng và Break luôn được ưu tiên cao nhất.</p></div></div><div className="tour-legend-grid"><span className="green">≥15 phút · Xanh</span><span className="yellow">0–&lt;15 · Vàng</span><span className="red">-15–&lt;0 · Đỏ</span><span className="blank">≤-15 · Làm trống</span><span className="break">Break · Cam</span><span className="idle">Đi làm + Vào ca + đang rảnh</span><span className="leave">Nghỉ phép · Chữ mờ</span></div></section>
    <div className="setup-note tour-countdown-note">Thời gian còn lại do hệ thống tự đếm: Yêu cầu trống dùng “TG bắt đầu thực hiện”; Yêu cầu YC dùng “TG bắt đầu thực hiện YC”; cả hai cộng theo Thời lượng.</div>
  </div>
}
