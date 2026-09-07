// EmployeePage already owns the canonical React-controlled employee search input.
// Keep this compatibility component mounted by App.jsx, but do not hide or proxy
// the real input: DOM-level proxying can leave React state stuck on a sentinel
// value and make both name search and the other filters appear unresponsive.
export default function EmployeeExactSearch() {
  return null
}
