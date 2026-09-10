export const normalizeSearchText = (value) => String(value ?? '').normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').toLowerCase().trim()
  .replace(/[^\p{L}\p{N}]+/gu, ' ').trim().replace(/\s+/g, ' ')

// Match a phrase at word boundaries, allowing the last word to be unfinished.
// Compare fields independently: label "An" + value "an" is not "An An".
export function searchTextMatches(fields, query) {
  const needle = normalizeSearchText(query)
  if (!needle) return true
  const terms = needle.split(' ')
  return (Array.isArray(fields) ? fields : [fields]).some((field) => {
    const words = normalizeSearchText(field).split(' ')
    return words.some((_, start) => terms.every((term, index) => {
      const word = words[start + index] || ''
      return index === terms.length - 1 ? word.startsWith(term) : word === term
    }))
  })
}

// Scroll only the result list. scrollIntoView also scrolls the page/viewport.
export function scrollSearchOption(list, option) {
  if (!list || !option) return
  const bounds = list.getBoundingClientRect()
  const row = option.getBoundingClientRect()
  if (row.top < bounds.top) list.scrollTop -= bounds.top - row.top
  else if (row.bottom > bounds.bottom) list.scrollTop += row.bottom - bounds.bottom
}
