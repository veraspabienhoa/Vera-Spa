import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import {JSDOM} from 'jsdom'

const php = fs.readFileSync(path.resolve('../integrations/wordpress/booking-form-ux.php'), 'utf8')
const script = php.match(/<script>([\s\S]*?)<\/script>/)?.[1]
assert.ok(script, 'booking UX JavaScript is present')

function makeForm(order, includeStaff = true) {
  const fields = order.map((name) => `<div class="vera-booking-field"><input name="${name}"></div>`).join('')
  const staff = includeStaff ? '<div class="vera-booking-field vera-booking-staff"><select name="requested-staff"></select></div>' : ''
  return `<form class="wpcf7-form"><div class="vera-booking-form"><div class="vera-booking-fields">${fields}</div>${staff}</div></form>`
}

const order = ['your-name', 'number-721', 'date-175', 'checkbox-444', 'number-999', 'menu-396']
const initial = ['menu-396', 'number-999', 'date-175', 'checkbox-444', 'your-name', 'number-721']

test('public booking form removes staff request and follows the requested field order', () => {
  const dom = new JSDOM(makeForm(initial), {runScripts: 'outside-only', url: 'https://veraspa.vn/booking/'})
  dom.window.eval(script)
  const form = dom.window.document.querySelector('form')
  assert.deepEqual([...form.querySelectorAll('.vera-booking-fields input')].map((field) => field.name), order)
  assert.equal(form.querySelector('[name="requested-staff"]'), null)
  assert.match(php, /nth-child\(5\)[\s\S]*nth-child\(6\).*grid-column: 1 \/ -1/)
  dom.window.close()
})

test('Contact Form 7 initialization also arranges dynamically rendered booking forms', () => {
  const dom = new JSDOM('<main></main>', {runScripts: 'outside-only', url: 'https://veraspa.vn/booking/'})
  dom.window.eval(script)
  const host = dom.window.document.querySelector('main')
  host.innerHTML = makeForm(initial)
  const form = host.querySelector('form')
  form.dispatchEvent(new dom.window.CustomEvent('wpcf7init', {bubbles: true}))
  assert.deepEqual([...form.querySelectorAll('.vera-booking-fields input')].map((field) => field.name), order)
  assert.equal(form.querySelector('.vera-booking-staff'), null)
  dom.window.close()
})
