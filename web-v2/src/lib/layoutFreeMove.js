// Preserve document flow and React ownership; translation is separate from hover transforms.
const clamp = value => Math.max(-2400, Math.min(2400, Math.round(value)))
function snap(position, size, candidates, enabled) {
  let delta = 7, line = position
  if (enabled) for (const target of candidates) for (const edge of [0,size/2,size]) {
    const distance = target - position - edge
    if (Math.abs(distance) < Math.abs(delta)) {delta=distance;line=target}
  }
  return Math.abs(delta) <= 6 ? {position:position+delta,line} : {position,line:position}
}
export function freeMovePosition(start, dx, dy, viewportWidth, snapping=true, scrollX=0, scrollY=0) {
  const sx=scrollX-start.scrollX, sy=scrollY-start.scrollY
  const left=start.rect.left-sx, top=start.rect.top-sy
  const x=snap(left+dx+sx,start.rect.width,start.targets.flatMap(r=>[r.left-sx,(r.left+r.right)/2-sx,r.right-sx]),snapping)
  const y=snap(top+dy+sy,start.rect.height,start.targets.flatMap(r=>[r.top-sy,(r.top+r.bottom)/2-sy,r.bottom-sy]),snapping)
  // Keep the object's horizontal extent inside the visible page while dragging.
  const boundedLeft=Math.max(0,Math.min(x.position,Math.max(0,viewportWidth-start.rect.width)))
  return {x:clamp((start.original?.offset_x || 0)+boundedLeft-left),y:clamp((start.original?.offset_y || 0)+y.position-top),guides:{x:boundedLeft===x.position?x.line:boundedLeft,y:y.line}}
}
