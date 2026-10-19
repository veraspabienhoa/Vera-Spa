// Resolve insertion from visible rectangles, including gaps in wrapped rows.
export function flowDrop(peers, x, y, vertical = false) {
  if (!peers.length) return { before: null, line: null }
  const rows = []
  for (const node of peers) {
    const rect = node.getBoundingClientRect()
    if (!rect.width || !rect.height) continue
    let row = !vertical && rows.find(row => Math.min(row.bottom, rect.bottom) > Math.max(row.top, rect.top))
    if (!row) { row = { top: rect.top, bottom: rect.bottom, items: [] }; rows.push(row) }
    row.top = Math.min(row.top, rect.top); row.bottom = Math.max(row.bottom, rect.bottom)
    row.items.push({ node, rect })
  }
  if (!rows.length) return { before: null, line: null }
  rows.sort((a,b) => a.top-b.top)
  const row = rows.reduce((best, row) => {
    const distance = r => Math.max(r.top-y, y-r.bottom, 0)
    return distance(row) < distance(best) ? row : best
  })
  row.items.sort((a,b) => a.rect.left-b.rect.left)
  const target = vertical ? row.items[0] : row.items.find(item => x < (item.rect.left+item.rect.right)/2) || row.items.at(-1)
  const after = vertical ? y > (target.rect.top+target.rect.bottom)/2 : x >= (target.rect.left+target.rect.right)/2
  const index = peers.indexOf(target.node)
  const r = target.rect
  return { before: after ? peers[index+1] || null : target.node,
    line: vertical ? {x:r.left,y:after?r.bottom:r.top,width:r.width,height:2} : {x:after?r.right:r.left,y:r.top,width:2,height:r.height} }
}
