let snapshot = { items: {} }
const listeners = new Set()
export const getCustomization = () => snapshot
export const subscribeCustomization = listener => { listeners.add(listener); return () => listeners.delete(listener) }
export function publishCustomization(items, editing = false) { snapshot = { items, editing }; listeners.forEach(listener => listener()) }
