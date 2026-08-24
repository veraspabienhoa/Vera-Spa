import { Download, RefreshCw, Search, WalletCards } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { veraApi } from '../lib/api'

const money = (value) => Number(value || 0).toLocaleString('vi-VN') + 'đ'
export default function PayrollPage({ user }) {
  const [batch, setBatch] = useState('')
  const [search, setSearch] = useState('')
  const [data, setData] = useState({ records: [], batches: [] })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = async () => { setBusy(true); setError(''); try { setData(await veraApi.payrollHistory(batch, search)) } catch (e) { setError(e.message) } finally { setBusy(false) } }
  useEffect(() => { void load() }, [batch]) // eslint-disable-line react-hooks/exhaustive-deps
  const total = useMemo(() => data.records.reduce((sum, item) => sum + Number(item['Số tiền thực nhận'] || 0), 0), [data.records])
  return <div className="feature-page">
    <div className="page-heading"><div><span className="eyebrow"><WalletCards size={14} /> PostgreSQL</span><h1>BẢNG LƯƠNG</h1><p>Lịch sử bảng lương đã lưu; dữ liệu được giữ nguyên, không tự tính lại.</p></div><button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới</button></div>
    {error && <div className="error-box">{error}</div>}
    <section className="panel data-toolbar"><label>Kỳ lương<select value={batch} onChange={(e) => setBatch(e.target.value)}><option value="">Tất cả kỳ lương</option>{data.batches.map((item) => <option key={item}>{item}</option>)}</select></label><label className="search-field"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && load()} placeholder="Tên nhân viên" /></label>{user?.permissions?.payroll_export && <button className="secondary-button" onClick={() => veraApi.exportPayrollExcel(batch, search)}><Download size={16} /> Export Excel</button>}</section>
    <div className="metric-grid small"><div className="metric-card"><span>Số dòng lương</span><strong>{data.records.length}</strong></div><div className="metric-card"><span>Tổng thực nhận đang xem</span><strong>{money(total)}</strong></div></div>
    <section className="panel"><div className="responsive-data-table"><table><thead><tr><th>Nhân viên</th><th>Kỳ lương</th><th>Lương</th><th>Phạt</th><th>Ứng lương</th><th>Thực nhận</th></tr></thead><tbody>{data.records.map((item, index) => <tr key={`${item['Mã bản lưu']}-${item['Tên Hệ thống']}-${index}`}><td><strong>{item['Tên Hệ thống']}</strong><small>{item['Họ và tên']}</small></td><td>{item['Từ ngày']} – {item['Đến ngày']}</td><td>{money(item['Tiền Lương'])}</td><td>{money(item['Tiền phạt trong tháng'])}</td><td>{money(item['Tiền ứng lương'])}</td><td><strong>{money(item['Số tiền thực nhận'])}</strong></td></tr>)}</tbody></table></div>{!data.records.length && <div className="setup-note">Không có bảng lương phù hợp.</div>}</section>
  </div>
}
