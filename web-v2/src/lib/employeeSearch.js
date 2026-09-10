// Canonical name rules extracted from Đăng ký nghỉ / Danh sách.
export const shortEmployeeName = (value) => String(value || '')
  .split(/\s*[-–—]\s*/, 1)[0]
  .trim()
  .toLocaleLowerCase('vi-VN')
  .replace(/(^|\s)\S/g, (letter) => letter.toLocaleUpperCase('vi-VN'))

export const normalizeEmployeeSearch = (value) => String(value || '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd')
  .replace(/Đ/g, 'D')
  .toLocaleLowerCase('vi-VN')
  .replace(/\s+/g, ' ')
  .trim()

export const matchesEmployeeName = (employeeName, searchValue) => {
  const needle = normalizeEmployeeSearch(searchValue)
  return !needle || [employeeName, shortEmployeeName(employeeName)]
    .some((name) => normalizeEmployeeSearch(name) === needle)
}

export const employeeValue = (employee) => String(typeof employee === 'string' ? employee
  : employee?.value ?? employee?.username ?? employee?.employee_username
    ?? employee?.employee_name ?? employee?.['Tên Hệ thống'] ?? '')

export const employeeOptions = (employees = []) => [...new Set(employees.map(employeeValue).filter(Boolean))]

// Never assign an ambiguous short name to the first matching employee.
export const resolveEmployeeName = (employees, query) => {
  const needle = normalizeEmployeeSearch(query)
  if (!needle) return ''
  const options = employeeOptions(employees)
  const exact = options.filter((name) => normalizeEmployeeSearch(name) === needle)
  if (exact.length === 1) return exact[0]
  if (exact.length > 1) return ''
  const matches = options.filter((name) => matchesEmployeeName(name, query))
  return matches.length === 1 ? matches[0] : ''
}
