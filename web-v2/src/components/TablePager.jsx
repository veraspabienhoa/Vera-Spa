import './TablePager.css'
export default function TablePager({ pagination, label = 'Danh sách' }) {
  const { page, pages, total, pageSize, setPage } = pagination
  if (total <= pageSize) return null
  return <nav className="table-pager" aria-label={`Phân trang ${label}`}>
    <span>{(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} / {total.toLocaleString('vi-VN')} dòng</span>
    <button type="button" className="secondary-button compact" disabled={page === 1} onClick={() => setPage(page - 1)}>Trang trước</button>
    <span aria-live="polite">Trang {page} / {pages}</span>
    <button type="button" className="secondary-button compact" disabled={page === pages} onClick={() => setPage(page + 1)}>Trang sau</button>
  </nav>
}
