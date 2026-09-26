import './StableDataRegion.css'

// Keep the existing table and its own scroll container mounted during refresh.
// The overlay is outside document flow; busy controls cannot submit stale data.
export default function StableDataRegion({ loading, label = 'Đang cập nhật dữ liệu…', children }) {
  return <div className="stable-data-region" aria-busy={Boolean(loading)}>
    <div className="stable-data-content" inert={loading ? '' : undefined}>{children}</div>
    {loading && <div className="stable-data-loading" role="status">{label}</div>}
  </div>
}
