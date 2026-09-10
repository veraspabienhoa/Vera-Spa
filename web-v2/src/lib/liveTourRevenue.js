export function summarizeTourRevenue(rows) {
  const totals = rows.reduce((sum, row) => ({
    totalRevenue: sum.totalRevenue + Number(row.total || 0),
    tip: sum.tip + Number(row.tip || 0),
  }), { totalRevenue: 0, tip: 0 })
  // Invoice totals and allocated report totals already include TIP.
  return { ...totals, serviceRevenue: totals.totalRevenue - totals.tip }
}
