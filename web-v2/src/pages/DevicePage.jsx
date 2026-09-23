import { Server } from 'lucide-react'
import { useEffect, useState } from 'react'
import { veraApi } from '../lib/api'
import { formatVeraDateTime } from '../lib/veraDate'

// Configuration supplied by the administrator; no browser request is made to a private LAN address.
const device = [
  ['Mã máy chấm công', '2023044'],
  ['Tên máy chấm công', 'máy nhận diện chấm công'],
  ['Loại thiết bị', 'FaceId'],
  ['IP FaceGate hiện tại', '192.168.1.52'],
  ['Cổng web FaceGate', '80'],
  ['Cổng TimeSoft đang lưu', '4370 (chưa xác minh tại IP mới)'],
  ['Kiểu kết nối', 'TCP/IP'],
  ['ID máy', '2023044'],
  ['Face Server cũ', '192.168.1.150 (không phản hồi trên cổng 80)'],
]

export default function DevicePage() {
  const [source, setSource] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    veraApi.attendanceSource().then(value => { if (active) setSource(value) }).catch(cause => { if (active) setError(cause.message) })
    return () => { active = false }
  }, [])
  return <section className="device-page">
    <div className="page-heading"><div><span className="eyebrow"><Server size={16} /> THIẾT BỊ CHẤM CÔNG</span><h1>QUẢN LÝ THIẾT BỊ</h1><p>Thông tin thiết bị FaceID do quản trị viên cung cấp.</p></div></div>
    <div className="responsive-data-table"><table><thead><tr><th>Thông tin</th><th>Giá trị</th></tr></thead><tbody>
      {device.map(([label, value]) => <tr key={label}><td data-label="Thông tin">{label}</td><td data-label="Giá trị">{value}</td></tr>)}
    </tbody></table></div>
    <p>VPS đã đọc 56 bản ghi Capture ngày 23-09-2026 qua tunnel SSH tạm thời. Endpoint ảnh đã trả ảnh BMP; kết nối chỉ hoạt động khi Windows và phiên SSH còn chạy.</p>
    <p>Nguồn TimeSoft: {source ? `${source.row_count} bản ghi trong cache hôm nay; đồng bộ lúc ${formatVeraDateTime(source.last_sync_at)}; ${source.cache_fresh ? 'cache còn hạn' : 'cache hết hạn'}.` : error ? `Không đọc được trạng thái: ${error}` : 'Đang tải…'}</p>
    <p>TimeSoft không xác nhận các bản ghi này đến từ riêng máy 2023044. Cần thiết lập đường kết nối thường trực và xác minh mã nhân viên trước khi sử dụng log cho nghiệp vụ.</p>
  </section>
}
