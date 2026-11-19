import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { getAftercampReportUrl } from './operationsApi.js'

test('After-camp exports accept only positive edition identifiers and known formats', () => {
  assert.match(getAftercampReportUrl(1,'docx'), /aftercamp-report\/\?edition=1&export=docx$/)
  assert.match(getAftercampReportUrl('2','print'), /aftercamp-report\/\?edition=2&export=print$/)
  assert.throws(() => getAftercampReportUrl('../1','docx'))
  assert.throws(() => getAftercampReportUrl('1','pdf'))
})
test('Comprehensive aftercamp reporting is distinct from domain reporting', () => {
  const operations = readFileSync(new URL('../pages/Operations.jsx',import.meta.url),'utf8')
  const screen = readFileSync(new URL('../pages/AftercampReport.jsx',import.meta.url),'utf8')
  assert.match(operations, /path="reporting-hub".*<AftercampReport/)
  assert.match(operations, /path="reporting".*<Reporting/)
  assert.match(screen, /Download consolidated Word report/)
  assert.match(screen, /Detailed operational analytics/)
  assert.match(screen, /section\.state==='restricted'/)
})
