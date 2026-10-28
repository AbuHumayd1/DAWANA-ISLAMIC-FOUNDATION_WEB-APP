import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const config = JSON.parse(fs.readFileSync(new URL('../../../backend/dic/config/dic_2026_houses.json', import.meta.url), 'utf8'))
let server, Leaderboard
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  Leaderboard = (await server.ssrLoadModule('/src/pages/HouseScoring.jsx')).CombinedLeaderboard
})
after(async () => { await server?.close() })

test('approved inventory retains eight exact houses, four of each gender and 240 places', () => {
  assert.equal(config.year, 2026)
  assert.equal(config.houses.length, 8)
  assert.equal(config.houses.filter(row => row.gender === 'male').length, 4)
  assert.equal(config.houses.filter(row => row.gender === 'female').length, 4)
  assert.equal(config.houses.reduce((sum,row) => sum+row.capacity, 0), 240)
  assert.deepEqual(config.houses.map(row => row.name), ['ʿUkkāshah ibn Miḥṣan','Al-Barāʾ ibn Mālik','ʿAbdullāh ibn Umm Maktūm','Usayd ibn Ḥuḍayr','Nusaybah bint Kaʿb','Asmāʾ bint Yazīd','Umm Sulaym','Al-Shifāʾ bint ʿAbdullāh'])
  assert.ok(config.houses.every(row => row.capacity === 30 && row.status === 'active' && row.purpose === 'participants'))
})

test('approved colour mapping and Unicode metadata remain exact and complete', () => {
  assert.deepEqual(config.houses.map(row => row.badge_colour), ['#147D64','#244B91','#B46B19','#743B94','#B83F75','#168A9C','#A53E46','#677D29'])
  assert.ok(config.houses.every(row => /[\u0600-\u06ff]/.test(row.arabic_name) && row.motto && row.colour_name))
  assert.equal(config.houses[3].motto, 'Guided by the Qurʾān')
})

test('all eight full names and colours render in the existing zero-score leaderboard', () => {
  const rows = config.houses.map((row,index) => ({ house_id:index+1, name:row.name, colour:row.badge_colour, rank:1, awarded:0, deducted:0, net:0 }))
  const markup = renderToStaticMarkup(createElement(Leaderboard, { rows }))
  for (const row of rows) { assert.ok(markup.includes(row.name)); assert.ok(markup.includes(row.colour)) }
  assert.equal((markup.match(/<strong>0<\/strong>/g) || []).length,8)
})
