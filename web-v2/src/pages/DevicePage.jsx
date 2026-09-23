import { Server } from 'lucide-react'

// Configuration supplied by the administrator. Reachability has not been verified
// from the production host; no browser request is made to a private LAN address.
const device = [
  ['Mã máy chấm công', '2023044'],
  ['Tên máy chấm công', 'máy nhận diện chấm công'],
  ['Loại thiết bị', 'FaceId'],
  ['Địa chỉ IP', '192.168.1.6'],
  ['Cổng', '4370'],
  ['Kiểu kết nối', 'TCP/IP'],
  ['ID máy', '2023044'],
  ['Face Server', '192.168.1.150'],
]

export default function DevicePage() {
  return <section className="device-page">
    <div className="page-heading"><div><span className="eyebrow"><Server size={16} /> THIẾT BỊ CHẤM CÔNG</span><h1>QUẢN LÝ THIẾT BỊ</h1><p>Thông tin thiết bị FaceID do quản trị viên cung cấp.</p></div></div>
    <div className="responsive-data-table"><table><thead><tr><th>Thông tin</th><th>Giá trị</th></tr></thead><tbody>
      {device.map(([label, value]) => <tr key={label}><td data-label="Thông tin">{label}</td><td data-label="Giá trị">{value}</td></tr>)}
    </tbody></table></div>
    <p>Trạng thái kết nối trực tiếp: chưa xác minh. Dữ liệu chấm công hiện được đồng bộ qua TimeSoft; cần đường mạng riêng từ máy chạy API tới Face Server hoặc máy chấm công để lấy log trực tiếp.</p>
  </section>
}
