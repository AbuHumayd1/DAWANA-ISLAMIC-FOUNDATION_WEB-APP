import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { reportingPath } from './reporting.js'

test('ordinary Reports hosts premium individual domains and raw extracts are separate',()=>{
  const src=readFileSync(new URL('../pages/Operations.jsx',import.meta.url),'utf8')
  assert.match(src, /path="reports" element=\{user\.permissions\.export_reports \? <Reporting/)
  assert.match(src, /path="reports\/data" element=\{user\.permissions\.export_reports \? <ReportsPage/)
  assert.match(src, /path="reporting-hub" element=\{user\.can_access_campsite && user\.permissions\.export_reports \? <AftercampReport/)
})
test('premium Word exports retain authorized domain and filters',()=>{
  const url=reportingPath({edition:'1',domain:'registration',date_from:'2026-12-23',page:'4'},'docx')
  assert.match(url,/export=docx$/)
  assert.match(url,/date_from=2026-12-23/)
  assert.doesNotMatch(url,/page=/)
  assert.throws(()=>reportingPath({edition:1,domain:'registration'},'xlsx'))
})
