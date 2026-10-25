// 架构模式：树的增删改移、删除影响、页面清单、流程和数据的布局、发给 AI 的话、界面接上了
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { addChild, addSibling, emptyArchitecture, findNode, generateMessage, impactOf, layoutData, layoutFlow, moveNode, rebuildMessage, removeNode, screens, connector } from '../src/lib/architecture.js'
import { appSource } from './appSource.js'

function sample() {
  const a = emptyArchitecture('设备管理')
  const mod = a.nodes[0]
  const page = addChild(a, mod.id, 'page', '设备巡检计划')
  const tab1 = addChild(a, page.id, 'tab', '路线配置')
  const tab2 = addChild(a, page.id, 'tab', '巡检点')
  addChild(a, tab1.id, 'drawer', '路线详情')
  a.entities = [
    { id: 'e1', name: '巡检点', fields: [{ name: '关联设备', kind: 'ref', ref: '设备档案' }] },
    { id: 'e2', name: '路线', fields: [{ name: '巡检点', kind: 'ref', ref: '巡检点', note: '有序' }] },
    { id: 'e3', name: '设备档案', fields: [] }]
  a.steps = [{ id: 's1', lane: 'l_user', name: '配巡检点', next: ['s2'], node: tab2.id }, { id: 's2', lane: 'l_user', name: '配路线', next: [] }]
  return { a, mod, page, tab1, tab2 }
}

test('加子项、加同级、上下移', () => {
  const { a, page, tab1, tab2 } = sample()
  assert.equal(page.children.length, 2)
  const sib = addSibling(a, tab1.id)
  assert.equal(page.children[1].id, sib.id)
  assert.equal(sib.type, 'tab')
  assert.ok(moveNode(a, tab2.id, -1))
  assert.equal(page.children[1].id, tab2.id)
  assert.equal(moveNode(a, page.children[0].id, -1), false)   // 已经在最上面
})

test('删除：带着下面的一起走，流程里指向它的链接断开', () => {
  const { a, tab1, tab2 } = sample()
  assert.match(impactOf(a, tab1.id), /含 1 项/)
  assert.match(impactOf(a, tab2.id), /流程里 1 步/)
  const removed = removeNode(a, tab2.id)
  assert.equal(removed.name, '巡检点')
  assert.equal(findNode(a, tab2.id), null)
  assert.equal(a.steps[0].node, undefined)
})

test('一个菜单页一步：页签算在页面里', () => {
  const { a } = sample()
  const list = screens(a)
  assert.deepEqual(list.map(s => s.name), ['设备巡检计划'])
  assert.deepEqual(list[0].tabs, ['路线配置', '巡检点'])
  assert.equal(list[0].module, '新模块')
})

test('数据：被依赖的在左边一列，没写关系的引用也画线', () => {
  const { a } = sample()
  const { columns, edges } = layoutData(a)
  assert.deepEqual(columns.map(c => c.map(e => e.name)), [['设备档案'], ['巡检点'], ['路线']])
  assert.ok(edges.some(e => e.from === '巡检点' && e.to === '路线' && e.label.includes('有序')))
})

test('流程：按箭头从左往右排，同一格不重叠', () => {
  const { a } = sample()
  a.steps.push({ id: 's3', lane: 'l_user', name: '另一个起点', next: [] })
  const { cells, edges } = layoutFlow(a)
  const col = Object.fromEntries(cells.map(c => [c.step.id, c.col]))
  assert.equal(col.s1, 0); assert.equal(col.s2, 1)
  assert.notEqual(col.s3, col.s1)
  assert.deepEqual(edges, [{ from: 's1', to: 's2' }])
  assert.match(connector({ x: 0, y: 0, w: 10, h: 10 }, { x: 100, y: 0, w: 10, h: 10 }), /^M10 5 C/)
})

test('发给 AI 的话：按顺序列页面，重做只动一页', () => {
  const { a, tab1 } = sample()
  const msg = generateMessage(a, [{ name: '设备定义', module: '设备管理' }, { name: '设备巡检计划', module: '设备管理', tabs: ['巡检点', '路线配置'] }])
  assert.match(msg, /1\. 设备管理 › 设备定义\n2\. 设备管理 › 设备巡检计划（页签：巡检点、路线配置）/)
  assert.match(msg, /finish_step/)
  assert.match(rebuildMessage(a, tab1), /只重做「设备巡检计划 \/ 路线配置」这一页签/)
})

test('界面接上了：顶栏有「架构」、按架构生成时带上 architecture', () => {
  const header = readFileSync(new URL('../src/components/layout/AppHeader.vue', import.meta.url), 'utf8')
  assert.match(header, /@click="showArch"/)
  assert.match(appSource(), /architecture: !!options\.architecture/)
  assert.match(appSource(), /architecture: true/)
})

test('手动编：大纲视图、粘贴功能清单、键盘加删改名；AI 起草能看进度、能停；生成顺序默认收成一行', () => {
  const board = readFileSync(new URL('../src/components/architecture/ArchitectureBoard.vue', import.meta.url), 'utf8')
  const outline = readFileSync(new URL('../src/components/architecture/ArchOutline.vue', import.meta.url), 'utf8')
  const logic = readFileSync(new URL('../src/composables/useArchitecture.js', import.meta.url), 'utf8')
  assert.match(board, /s\.stopDraft\(\)/)
  assert.match(board, /arch-order-toggle/)
  assert.match(board, /s\.fromExpand\(\)/)
  assert.match(outline, /s\.applyOutline\(archOutline\)/)
  assert.match(outline, /s\.importText\(paste\.value, pasteMode\.value\)/)
  assert.match(logic, /key === 'Enter'[\s\S]*archSibling/)
  assert.match(logic, /key === 'Tab'[\s\S]*archAdd/)
  assert.match(logic, /consumeAgentStream/)
})

test('分到弹什么：按钮点了打开谁、页面结构视图一次看一页', async () => {
  const { ACTIONS, CHILD_TYPES, targetsIn, screenOf } = await import('../src/lib/architecture.js')
  assert.deepEqual(Object.keys(ACTIONS), ['open', 'jump', 'run', 'confirm'])
  assert.ok(CHILD_TYPES.page.includes('button') && CHILD_TYPES.table.includes('button'))
  const { a, tab1 } = sample()
  const btn = addChild(a, tab1.id, 'button', '新增路线')
  addChild(a, tab1.id, 'modal', '新增路线弹窗')
  assert.equal(screenOf(a, btn.id).name, '设备巡检计划')
  assert.ok(targetsIn(a, btn.id, 'open').includes('新增路线弹窗'))
  assert.ok(targetsIn(a, btn.id, 'jump').includes('设备巡检计划'))
  // 顶上只留页面树、业务流程；大纲、数据关系是内部的，收在「⋯」里
  const board = readFileSync(new URL('../src/components/architecture/ArchitectureBoard.vue', import.meta.url), 'utf8')
  assert.match(board, /const views = \[\{ id: 'tree', label: '页面树' \}, \{ id: 'flow', label: '业务流程' \}\]/)
  assert.match(board, /openExtra\('outline'\)/)
  assert.match(board, /openExtra\('data'\)/)
})

test('表格的状态列跟着数据里的状态流转', async () => {
  const { statesOf } = await import('../src/lib/architecture.js')
  const { a, tab1 } = sample()
  const table = addChild(a, tab1.id, 'table', '路线列表')
  a.entities[1].states = ['草稿', '启用', '停用']
  tab1.data = ['路线']
  assert.deepEqual(statesOf(a, table.id), ['草稿', '启用', '停用'])

})
