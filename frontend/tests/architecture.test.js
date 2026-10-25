// 架构：原型的页面树。树的增删改移、和上次同步时比改了什么、同步时发给 AI 的话、界面接上了
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { addChild, addSibling, changeLabel, clone, diffNodes, emptyArchitecture, findNode, impactOf, moveNode, removeNode, screens, syncMessage } from '../src/lib/architecture.js'
import { appSource } from './appSource.js'

function sample() {
  const a = emptyArchitecture('设备管理')
  const mod = a.nodes[0]
  const page = addChild(a, mod.id, 'page', '设备巡检计划')
  const tab1 = addChild(a, page.id, 'tab', '路线配置')
  const tab2 = addChild(a, page.id, 'tab', '巡检点')
  addChild(a, tab1.id, 'drawer', '路线详情')
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

test('删除：带着下面的一起走', () => {
  const { a, tab1 } = sample()
  assert.match(impactOf(a, tab1.id), /含 1 项/)
  assert.equal(removeNode(a, tab1.id).name, '路线配置')
  assert.equal(findNode(a, tab1.id), null)
})

test('一个菜单页一页：页签算在页面里', () => {
  const { a } = sample()
  const list = screens(a)
  assert.deepEqual(list.map(s => s.name), ['设备巡检计划'])
  assert.deepEqual(list[0].tabs, ['路线配置', '巡检点'])
})

test('和上次同步时比：加了、删了、改名、改字段，只记最上面那一个', () => {
  const { a, mod, tab1, tab2 } = sample()
  const synced = clone(a.nodes)
  const test1 = addChild(a, '', 'module', '测试')
  const modal = addChild(a, tab2.id, 'modal', '新增巡检点')
  modal.fields = ['点位名称*', '类型*（下拉：温度/压力）']
  addChild(a, modal.id, 'button', '保存')                       // 挂在新弹窗下面的，不单独算一条
  removeNode(a, tab1.id)
  mod.name = '设备'
  const changes = diffNodes(synced, a.nodes)
  assert.deepEqual(changes.map(c => c.kind).sort(), ['add', 'add', 'remove', 'rename'])
  assert.ok(changes.some(c => c.kind === 'add' && c.id === test1.id))
  assert.deepEqual(changes.map(changeLabel).filter(l => l.startsWith('新增')).sort(), ['新增弹窗「新增巡检点」', '新增模块「测试」'])
  const msg = syncMessage(changes)
  assert.match(msg, /只改下面这几处/)
  assert.match(msg, /新增 一级菜单页（左侧菜单加一项，点了直接进这一页）「测试」/)   // 空模块就是一个一级菜单页
  assert.match(msg, /弹窗「新增巡检点」；字段：点位名称\*、类型\*（下拉：温度\/压力）\n {2}- 按钮「保存」/)
  assert.match(msg, /删掉「设备 \/ 设备巡检计划」里的页签「路线配置」/)
  assert.match(msg, /「新模块」改名为「设备」/)
  // 改字段：只说加了哪个、去掉哪个
  const again = clone(a.nodes)
  modal.fields = ['点位名称*', '备注']
  const edit = diffNodes(again, a.nodes)
  assert.equal(changeLabel(edit[0]), '改了「新增巡检点」的字段')
  assert.match(syncMessage(edit), /字段加上 备注；去掉 类型/)
  assert.deepEqual(diffNodes(clone(a.nodes), a.nodes), [])
})

test('界面接上了：顶栏有「架构」、同步时带上 architecture、只剩页面树', () => {
  const header = readFileSync(new URL('../src/components/layout/AppHeader.vue', import.meta.url), 'utf8')
  const board = readFileSync(new URL('../src/components/architecture/ArchitectureBoard.vue', import.meta.url), 'utf8')
  const logic = readFileSync(new URL('../src/composables/useArchitecture.js', import.meta.url), 'utf8')
  assert.match(header, /@click="showArch"/)
  assert.match(appSource(), /architecture: !!options\.architecture/)
  assert.match(logic, /architecture: true/)
  assert.match(board, /s\.syncToPrototype\(\)/)
  assert.match(board, /s\.discardChanges/)
  assert.doesNotMatch(board, /业务流程|数据关系|统一规则|一致性检查/)
  assert.match(logic, /key === 'Enter'[\s\S]*archSibling/)
  assert.match(logic, /key === 'Tab'[\s\S]*archAdd/)
  const outline = readFileSync(new URL('../src/components/architecture/ArchOutline.vue', import.meta.url), 'utf8')
  assert.match(outline, /s\.applyOutline\(archOutline\)/)
  assert.match(outline, /s\.importText\(paste\.value, pasteMode\.value\)/)
})

test('分到弹什么：按钮点了打开谁', async () => {
  const { ACTIONS, CHILD_TYPES, targetsIn, screenOf } = await import('../src/lib/architecture.js')
  assert.deepEqual(Object.keys(ACTIONS), ['open', 'jump', 'run', 'confirm'])
  assert.ok(CHILD_TYPES.page.includes('button') && CHILD_TYPES.table.includes('button') && CHILD_TYPES.root.includes('page'))
  const { a, tab1 } = sample()
  const btn = addChild(a, tab1.id, 'button', '新增路线')
  addChild(a, tab1.id, 'modal', '新增路线弹窗')
  assert.equal(screenOf(a, btn.id).name, '设备巡检计划')
  assert.ok(targetsIn(a, btn.id, 'open').includes('新增路线弹窗'))
  assert.ok(targetsIn(a, btn.id, 'jump').includes('设备巡检计划'))
})

test('表格的状态列：同一页里「xx状态」下拉的选项就是状态流转', async () => {
  const { statesOf } = await import('../src/lib/architecture.js')
  const { a, tab1 } = sample()
  const filter = addChild(a, tab1.id, 'block', '筛选')
  filter.fields = ['路线名称', '路线状态（下拉：草稿/启用/停用）']
  const table = addChild(a, tab1.id, 'table', '路线列表')
  assert.deepEqual(statesOf(a, table.id), ['草稿', '启用', '停用'])
})

test('空模块自己算一个页面', async () => {
  const { isScreenNode } = await import('../src/lib/architecture.js')
  const a = emptyArchitecture('测试')
  assert.ok(isScreenNode(a.nodes[0]))
  assert.deepEqual(screens(a).map(x => x.name), [a.nodes[0].name])
  addChild(a, a.nodes[0].id, 'page', '工单')
  assert.ok(!isScreenNode(a.nodes[0]))
})
