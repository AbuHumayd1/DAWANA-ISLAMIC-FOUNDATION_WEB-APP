// Read-only source checks. No dotenv, Python execution, database or network.
import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
const root = process.cwd()
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8').replace(/^\uFEFF/, '')
const dir = 'backend/dic/migrations'
const files = fs.readdirSync(path.join(root, dir)).filter(file => /^\d{4}_.+\.py$/.test(file))
const names = new Set(files.map(file => file.slice(0, -3)))
assert.equal(new Set(files.map(file => file.slice(0, 4))).size, files.length, 'Duplicate migration numbers')
const parents = new Set()
for (const file of files) {
  const text = read(`${dir}/${file}`)
  const dependencies = text.match(/\bdependencies\s*=\s*\[([\s\S]*?)\]/)?.[1] || ''
  for (const match of dependencies.matchAll(/\(['"]dic['"],\s*['"](\d{4}_[^'"]+)['"]\)/g)) {
    assert.ok(names.has(match[1]), `Missing migration dependency ${match[1]}`)
    parents.add(match[1])
  }
  const before = text.match(/\brun_before\s*=\s*\[([\s\S]*?)\]/)?.[1] || ''
  for (const match of before.matchAll(/\(['"]dic['"],\s*['"](\d{4}_[^'"]+)['"]\)/g)) {
    assert.ok(names.has(match[1]), `Missing run_before target ${match[1]}`)
    parents.add(file.slice(0, -3))
  }
}
const leaves = [...names].filter(name => !parents.has(name))
assert.deepEqual(leaves, ['0039_camper_fulfillment'])
const migration = read(`${dir}/0039_camper_fulfillment.py`)
assert.match(migration, /0038_registration_guardian_declaration/)
assert.doesNotMatch(migration, /RunPython|RunSQL/)
assert.deepEqual([...migration.matchAll(/migrations\.([A-Z]\w*)\(/g)].map(match => match[1]), ['CreateModel'],
  'Recovery migration must only create its independent outbox')
assert.match(migration, /OneToOneField\(on_delete=django\.db\.models\.deletion\.PROTECT/)
for (const name of ['dic_fulfillment_queue_idx', 'dic_fulfillment_state_valid']) {
  assert.ok(migration.includes(name) && read('backend/dic/fulfillment_models.py').includes(name), `Missing model/migration definition ${name}`)
}
assert.equal(files.filter(file => file.startsWith('0034_')).join(), '0034_approved_2026_fees.py')
const model = read('backend/dic/fulfillment_models.py')
for (const field of ['order', 'state', 'attempts', 'retry_at', 'reason_code', 'processed_by', 'created_at', 'updated_at']) {
  assert.match(model, new RegExp(`\\b${field} = models\\.`))
  assert.ok(migration.includes(`('${field}',`), `Missing migration field ${field}`)
}
const settings = read('backend/config/settings/base.py')
assert.match(settings, /DIC_AUTO_FULFILLMENT_ENABLED = env.bool\('DIC_AUTO_FULFILLMENT_ENABLED', default=False\)/)
const service = read('backend/dic/fulfillment.py')
assert.match(service, /order_has_verified_settlement\(order\)/)
assert.match(service, /settlement_reason\(attempt\)/)
assert.match(service, /select_for_update\(\)/)
assert.match(service, /get_or_create\(order=order\)/)
assert.doesNotMatch(service, /allocate_batch\(|process_claim\(|HouseAllocation\.objects|HousingJob\.objects/)
assert.match(read('backend/dic/payment_views.py'), /enqueue_housing\(order\)[\s\S]*enqueue_verified\(order, attempt\)/)
const command = read('backend/dic/management/commands/process_camper_fulfillment.py')
for (const gate of ["options['approve_writes']", "options['database_name']", "options['edition'] > 0",
  "settings.DATABASE_ROUTERS", "1 <= options['limit'] <= 100", "django.db.backends.postgresql"]) {
  assert.ok(command.includes(gate), `Missing worker execution gate ${gate}`)
}
assert.ok(command.indexOf('raise CommandError') < command.indexOf('CamperFulfillmentJob.objects'), 'Worker must reject unsafe configuration before querying jobs')
const branding = read('backend/dic/templates/admin/base_site.html').match(/{% block branding %}([\s\S]*?){% endblock %}/)?.[1] || ''
assert.match(branding, /href="\{\{ public_site_url\|default:'\/' \}\}" class="admin-public-return"/)
console.log(JSON.stringify({ status: 'PASS', migrationFiles: files.length, leaves,
  checks: ['migration source dependencies and unique numbers', 'create-only migration, protected unique order and named index/constraint', 'additive model fields', 'default-off rollout', 'verified settlement gates', 'ID/housing separation', 'bounded explicit worker execution gates'],
  limitation: 'Source checks only; not Python syntax, Django migration parity, applied schema or PostgreSQL concurrency acceptance.' }, null, 2))
