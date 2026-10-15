import test from 'node:test'
import assert from 'node:assert/strict'
import { newLabels, topLabels } from '../src/probe.js'

test('改版后多出来的按钮能认出来', () => {
  const init = { triggers: [{ text: '新增设备' }, { text: '表格行 · 详情' }, { text: '表格行 · 编辑' }], tabs: [{ text: '巡检计划' }] }
  const now = topLabels(init)
  assert.deepEqual(now, ['新增设备', '详情', '编辑', '页签 · 巡检计划'].sort())
  assert.deepEqual(newLabels(now, { top: ['详情', '页签 · 巡检计划'] }).sort(), ['新增设备', '编辑'].sort())
  assert.deepEqual(newLabels(now, { top: now }), [])
})

test('旧结果没记 top：用节点、待补、没反应、跳过的按钮名凑', () => {
  const now = ['新增设备', '详情', '编辑']
  const prev = { nodes: [{ parent: null, label: '表格行 · 详情' }], dead: [], coverage: { none: { labels: ['新增设备'] }, skipped: {} } }
  assert.deepEqual(newLabels(now, prev), ['编辑'])
})
