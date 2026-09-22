// React owns both source elements and portal destinations. Ambiguous repeated
// groups are not destinations, so a saved layout never selects an arbitrary row.
let targets = {}
const registrations = new Map()
const listeners = new Set()
const publish = () => {
  targets = Object.fromEntries([...registrations].filter(([,entries]) => entries.size === 1).map(([key,entries]) => [key,[...entries][0]]))
  listeners.forEach(listener => listener())
}
export const getLayoutTargets = () => targets
export const subscribeLayoutTargets = listener => { listeners.add(listener); return () => listeners.delete(listener) }
export function registerLayoutTarget(key, element, slot) {
  if (!key || !element || !slot) return () => {}
  const entry = { element, slot }
  const entries = registrations.get(key) || new Set()
  entries.add(entry); registrations.set(key, entries); publish()
  return () => {
    entries.delete(entry)
    if (!entries.size) registrations.delete(key)
    publish()
  }
}
export function canRelocate(source, destination) {
  return Boolean(source && destination && source !== destination && !source.contains(destination)
    && source.closest('form') === destination.closest('form')
    && !destination.closest('button,a,label,table'))
}
