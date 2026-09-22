// Source identities do not depend on visible text, permissions or live data.
export default function layoutIdentity({ types: t }) {
  return { visitor: { JSXOpeningElement(path, state) {
    const name = path.node.name
    if (!t.isJSXIdentifier(name) || !/^[a-z]/.test(name.name)) return
    const file = (state.filename || '').replaceAll('\\', '/').split('/src/')[1]
    if (!file || file.includes('LayoutDesigner')) return
    const owner = path.findParent(parent => parent.isFunction())
    const ownerName = owner?.node.id?.name || owner?.parentPath?.node.id?.name || 'module'
    const staticAttributes = path.node.attributes.filter(attr => t.isJSXAttribute(attr)
      && ['id', 'className', 'role', 'aria-label', 'name', 'data-label'].includes(attr.name.name)
      && t.isStringLiteral(attr.value)).map(attr => `${attr.name.name}=${attr.value.value}`).join('|')
    const signature = `${file}:${ownerName}:${name.name}:${staticAttributes}`
    state.layoutOccurrences ||= new Map()
    const occurrence = state.layoutOccurrences.get(signature) || 0
    state.layoutOccurrences.set(signature, occurrence + 1)
    const identity = `${signature}:${occurrence}`
    let hash = 2166136261
    for (const char of identity) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619)
    path.node.attributes.push(t.jsxAttribute(t.jsxIdentifier('data-vera-node'), t.stringLiteral((hash >>> 0).toString(36))))
    const key = path.node.attributes.find(attr => t.isJSXAttribute(attr) && attr.name.name === 'key')
    if (key?.value) path.node.attributes.push(t.jsxAttribute(t.jsxIdentifier('data-vera-item'), t.cloneNode(key.value, true)))
  } } }
}
