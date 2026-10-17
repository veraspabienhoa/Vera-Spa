export default function WeeklyShiftTable({ rows = [] }) {
  const first = rows.filter(row => row.current === 'Ca 1')
  const second = rows.filter(row => row.current === 'Ca 2')
  return <table className="weekly-shift-summary-table" aria-label="Danh sách ca tuần này">
    <colgroup><col className="weekly-shift-number"/><col/><col className="weekly-shift-number"/><col/></colgroup>
    <thead><tr><th scope="col">STT</th><th scope="col">Ca 1 tuần này</th><th scope="col">STT</th><th scope="col">Ca 2 tuần này</th></tr></thead>
    <tbody>{Array.from({ length: Math.max(first.length, second.length) }, (_, index) => <tr key={index}>
      <td>{first[index] ? index + 1 : ''}</td><td>{first[index]?.name || ''}</td>
      <td>{second[index] ? index + 1 : ''}</td><td>{second[index]?.name || ''}</td>
    </tr>)}{!first.length && !second.length && <tr><td colSpan={4}>Chưa có nhân viên được xếp ca tuần này.</td></tr>}</tbody>
    <tfoot><tr><th scope="row">Tổng</th><td>{first.length} nhân viên</td><th scope="row">Tổng</th><td>{second.length} nhân viên</td></tr></tfoot>
  </table>
}
