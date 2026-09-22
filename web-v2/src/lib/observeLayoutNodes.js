// Initial identity application and subsequent inserts are separate from editing.
// Text/timer updates never scan the entire application tree.
export function observeLayoutNodes(root, identify, windowObject = window) {
  const selector='[data-vera-node],[data-ui-key]'
  const excluded='.layout-designer,.layout-resize-overlay,.break-alert-stack'
  const pending=new Set()
  let frame=null
  const collect=node=>{
    if(node.nodeType!==1 || node.closest(excluded))return
    if(node.matches(selector))pending.add(node)
    node.querySelectorAll(selector).forEach(child=>{if(!child.closest(excluded))pending.add(child)})
  }
  const flush=()=>{frame=null;const nodes=[...pending].filter(node=>root.contains(node));pending.clear();if(nodes.length)identify(nodes)}
  collect(root);flush()
  const observer=new windowObject.MutationObserver(changes=>{
    for(const change of changes) {
      if(change.type==='attributes')collect(change.target)
      else for(const node of change.addedNodes)collect(node)
    }
    if(pending.size && frame===null)frame=windowObject.requestAnimationFrame(flush)
  })
  observer.observe(root,{childList:true,subtree:true,attributes:true,attributeFilter:['data-ui-key','data-vera-node','data-vera-item']})
  return ()=>{observer.disconnect();if(frame!==null)windowObject.cancelAnimationFrame(frame)}
}
