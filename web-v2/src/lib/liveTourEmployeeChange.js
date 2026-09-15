export function canChangeEmployee(record) {
  return record?._tour_groups?.includes('doing') === true && record?._employee_change_allowed === true
}
