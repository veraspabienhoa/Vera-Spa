import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { employeeOptions, matchesEmployeeName, resolveEmployeeName } from '../src/lib/employeeSearch.js'

const cases = JSON.parse(readFileSync(new URL('../../tests/fixtures/employee_search_cases.json', import.meta.url), 'utf8'))
test('employee filters follow the Leave List rules for Vietnamese names and near matches', () => {
  for (const item of cases) assert.equal(matchesEmployeeName(item.name, item.query), item.matches, JSON.stringify(item))
})
test('assignment accepts only unique eligible employees and returns the stored username', () => {
  const employees = [{ username: 'Cẩm Vân' }, { username: 'Ngọc Châu - KTV' }]
  assert.equal(resolveEmployeeName(employees, '  CAM   VAN '), 'Cẩm Vân')
  assert.equal(resolveEmployeeName(employees, 'ngoc chau'), 'Ngọc Châu - KTV')
  assert.equal(resolveEmployeeName(employees, 'Ngọc'), '')
  assert.equal(resolveEmployeeName(employees, 'Nhân viên ngoài bộ phận'), '')
  assert.equal(resolveEmployeeName(employees, ''), '')
})
test('ambiguous shortened names cannot silently select a different employee', () => {
  const employees = ['Linh Đan - A', 'Linh Đan - B']
  assert.equal(resolveEmployeeName(employees, 'linh dan'), '')
  assert.equal(resolveEmployeeName(employees, 'linh dan - b'), 'Linh Đan - B')
  assert.equal(resolveEmployeeName(['Vân', 'Van'], 'van'), '')
})
test('each existing module can supply its own options without duplicate suggestions', () => {
  assert.deepEqual(employeeOptions(['Cẩm Vân', { username: 'Cẩm Vân' }, { employee_username: 'Ngọc Châu' }, { employee_name: 'Linh Đan' }, { 'Tên Hệ thống': 'Đỗ Ánh' }, null]), ['Cẩm Vân', 'Ngọc Châu', 'Linh Đan', 'Đỗ Ánh'])
})
