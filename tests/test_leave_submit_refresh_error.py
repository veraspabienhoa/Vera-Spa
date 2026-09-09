from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_successful_leave_create_is_not_reclassified_when_refresh_fails():
    # Execute the actual handlers, with only React setters and API I/O stubbed.
    # Check outcomes instead of freezing internal option names or UI copy.
    script = r"""
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const source = fs.readFileSync('web-v2/src/pages/LeaveRegistrationPage.jsx', 'utf8')
const loadSource = source.slice(source.indexOf('  const load = useCallback('), source.indexOf('  useEffect(() => { load()'))
const submitStart = source.indexOf('  const submit = async (event) => {')
const submitSource = source.slice(submitStart, source.indexOf('\n  return (', submitStart))
function harness(failedRead = '', failedCreate = false) {
  const state = { message: '', warnings: [], error: '', busy: false, saving: false }
  const calls = []
  let reading = false
  const context = {
    isApiConfigured: true, canCreate: true, canChooseEmployee: true,
    dateIsPast: false, date: '2026-09-09', rangeStart: '', rangeEnd: '',
    listRangeStart: '', listRangeEnd: '', statsEmployeeFilter: '',
    form: { employee_name: 'Test', leave_reason: 'Nghỉ CÓ phép', detail: '' },
    emptyForm: {}, selectedReason: {}, user: {}, useCallback: fn => fn,
    refreshWatchDates: async () => { calls.push('watch') },
  }
  for (const match of (loadSource + submitSource).matchAll(/\b(set\w+)\(/g)) {
    const name = match[1], key = name[3].toLowerCase() + name.slice(4)
    context[name] = value => { state[key] = typeof value === 'function' ? value(state[key]) : value }
  }
  context.veraApi = {
    createLeave: async () => {
      calls.push('create')
      if (failedCreate) throw new Error('create unavailable')
      return { warnings: ['Cảnh báo từ máy chủ'] }
    },
  }
  for (const name of ['leaveDailyStats', 'leaveRecords', 'leaveReasons', 'employees']) {
    context.veraApi[name] = async () => {
      assert.equal(reading, false, 'Refresh requests must remain sequential')
      reading = true
      calls.push(name)
      await Promise.resolve()
      reading = false
      if (name === failedRead) throw new Error('refresh unavailable')
      return {}
    }
  }
  vm.createContext(context)
  vm.runInContext(loadSource + submitSource + '\nthis.handlers = { load, submit }', context)
  return { state, calls, ...context.handlers }
}
(async () => {
  for (const endpoint of ['leaveDailyStats', 'leaveRecords', 'leaveReasons', 'employees']) {
    const run = harness(endpoint)
    await run.submit({ preventDefault() {} })
    assert.match(run.state.message, /THÀNH CÔNG/)
    assert.equal(run.state.error, '', 'A committed leave must not be reported as a failed save')
    assert.equal(run.state.warnings.length, 2)
    assert.equal(run.state.warnings[0], 'Cảnh báo từ máy chủ')
    assert.match(run.state.warnings[1], /đã được lưu.*chưa thể làm mới/)
    assert.equal(run.calls.filter(x => x === 'create').length, 1)
    assert.equal(run.state.busy, false)
    assert.equal(run.state.saving, false)
    assert.equal(run.calls.at(-1), 'watch')
  }
  const success = harness()
  await success.submit({ preventDefault() {} })
  assert.equal(success.state.error, '')
  assert.equal(success.state.warnings.length, 1)
  assert.deepEqual(success.calls, ['create', 'leaveDailyStats', 'leaveRecords', 'leaveReasons', 'employees', 'watch'])
  const initial = harness('leaveDailyStats')
  assert.equal(await initial.load(), false)
  assert.match(initial.state.error, /Không tải được/)
  assert.equal(initial.state.message, '')
  const rejected = harness('', true)
  await rejected.submit({ preventDefault() {} })
  assert.equal(rejected.state.message, '')
  assert.match(rejected.state.error, /KHÔNG THÀNH CÔNG/)
  assert.deepEqual(rejected.calls, ['create'])
  assert.equal(rejected.state.saving, false)
})().catch(error => { console.error(error); process.exitCode = 1 })
"""
    result = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
