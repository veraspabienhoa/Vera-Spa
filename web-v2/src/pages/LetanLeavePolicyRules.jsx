import { ShieldCheck } from 'lucide-react'

const GROUPS = [
  ['Nhóm 1', ['Nghỉ CÓ phép', 'Đi trễ CÓ phép', 'Về sớm CÓ phép']],
  ['Nhóm 2', ['Nghỉ KHÔNG phép', 'Đi trễ KHÔNG phép', 'Về sớm KHÔNG phép']],
  ['Nhóm 3', ['Nghỉ CUỐI TUẦN CÓ phép', 'Đi trễ CUỐI TUẦN CÓ phép', 'Về sớm CUỐI TUẦN CÓ phép']],
  ['Nhóm 4', ['Nghỉ CUỐI TUẦN KHÔNG phép', 'Đi trễ CUỐI TUẦN KHÔNG phép', 'Về sớm CUỐI TUẦN KHÔNG phép']],
  ['Nhóm 5', ['Leader nghỉ phép theo chính sách', 'Leader đi trễ sớm theo chính sách', 'Leader về sớm về sớm theo chính sách']],
]

export default function LetanLeavePolicyRules() {
  return (
    <section className="panel letan-leave-policy-panel">
      <style>{`
        .letan-leave-policy-panel{margin-top:16px}
        .letan-policy-note{display:grid;gap:5px;margin:10px 0 14px;padding:11px 13px;border:1px solid #d7e2dc;border-radius:12px;background:#f7faf8;color:#31483d;font-size:13px;line-height:1.45}
        .letan-policy-note strong{color:#173329}
        .letan-policy-table-wrap{width:100%;overflow-x:auto}
        .letan-policy-table{width:100%;border-collapse:collapse;table-layout:fixed}
        .letan-policy-table th,.letan-policy-table td{border-bottom:1px solid #e5ebe7;padding:10px 12px;text-align:left;vertical-align:top}
        .letan-policy-table th{font-size:12px;color:#52675e;background:#f7faf8}
        .letan-policy-table th:first-child,.letan-policy-table td:first-child{width:110px;text-align:center;font-weight:900;color:#173329}
        .letan-policy-reasons{display:grid;gap:5px;margin:0;padding-left:18px}
        .letan-policy-reasons li{line-height:1.35}
        @media(max-width:640px){
          .letan-policy-table th:first-child,.letan-policy-table td:first-child{width:72px;padding-left:6px;padding-right:6px}
          .letan-policy-table th,.letan-policy-table td{font-size:11px;padding:8px}
        }
      `}</style>
      <div className="panel-title-row">
        <div>
          <h2>QUYỀN SỬA / XÓA ĐĂNG KÝ – TÀI KHOẢN LỄ TÂN</h2>
          <p>Quy tắc hệ thống áp dụng bắt buộc cho tài khoản có vai trò Lễ tân.</p>
        </div>
        <ShieldCheck size={20} aria-hidden="true" />
      </div>

      <div className="letan-policy-note">
        <span><strong>Trước ngày hiện tại:</strong> Lễ tân không được xóa hoặc sửa bất cứ đăng ký nào.</span>
        <span><strong>Ngày hiện tại – Nhóm 1 đến Nhóm 5:</strong> Lễ tân không được xóa; chỉ được đổi <strong>Lý do nghỉ</strong> sang một trong 3 lý do thuộc đúng cùng nhóm.</span>
        <span><strong>Ngày hiện tại – Lý do/Loại nghỉ khác:</strong> nếu Lễ tân được phép nhập theo Phân quyền + Nội quy thì vẫn được <strong>xóa, sửa và thay đổi</strong> theo quyền hiện hành.</span>
        <span><strong>Ngày tương lai:</strong> tiếp tục áp dụng Phân quyền và Bảng nội quy hiện hành.</span>
      </div>

      <div className="letan-policy-table-wrap">
        <table className="letan-policy-table">
          <thead>
            <tr><th>Nhóm</th><th>Các Lý do nghỉ đặc biệt được phép đổi qua lại trong cùng nhóm</th></tr>
          </thead>
          <tbody>
            {GROUPS.map(([group, reasons]) => (
              <tr key={group}>
                <td>{group}</td>
                <td><ul className="letan-policy-reasons">{reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
