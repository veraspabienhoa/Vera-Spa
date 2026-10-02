// Reports can contain several employee lines from the same invoice.
export function reportInvoiceMetrics(rows, invoiceById = new Map()) {
  const grouped = new Map()
  rows.forEach((row, index) => {
    const id = row.invoice_id || row.bill_no || row.id || `row-${index}`
    const invoice = invoiceById.get(row.invoice_id || row.id)
    const group = grouped.get(id) || { total: 0, discount: 0 }
    group.total += Number(row.total || 0)
    group.discount += Number(row.discount || 0)
    if (invoice || row.invoice_total != null) group.invoiceTotal = Number(invoice?.total ?? row.invoice_total)
    if (invoice || row.invoice_discount != null) group.invoiceDiscount = Number(invoice?.discount ?? row.invoice_discount ?? 0)
    grouped.set(id, group)
  })
  return [...grouped.values()].reduce((sum, row) => ({
    zeroInvoices: sum.zeroInvoices + ((row.invoiceTotal ?? row.total) === 0 ? 1 : 0),
    discount: sum.discount + (row.invoiceDiscount ?? row.discount),
  }), { zeroInvoices: 0, discount: 0 })
}
