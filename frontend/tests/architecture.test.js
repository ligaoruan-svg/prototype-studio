// 架构画布：树的增删改移、两棵树比改了什么、和原型对不对得上、界面接上了
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { addChild, addSibling, clone, diffNodes, emptyArchitecture, findNode, impactOf, moveNode, protoState, removeNode, screens } from '../src/lib/architecture.js'
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

test('两棵树比：加了、删了、改名、改字段，整棵加进来的只记最上面那一个', () => {
  const { a, mod, tab1, tab2 } = sample()
  const before = clone(a.nodes)
  const test1 = addChild(a, '', 'module', '测试')
  const modal = addChild(a, tab2.id, 'modal', '新增巡检点')
  addChild(a, modal.id, 'button', '保存')
  removeNode(a, tab1.id)
  mod.name = '设备'
  const changes = diffNodes(before, a.nodes)
  assert.deepEqual(changes.map(c => c.kind).sort(), ['add', 'add', 'remove', 'rename'])
  assert.ok(changes.some(c => c.kind === 'add' && c.id === test1.id))
  assert.equal(changes.find(c => c.kind === 'remove').path.join(' / '), '设备 / 设备巡检计划 / 路线配置')
  const again = clone(a.nodes)
  modal.fields = ['点位名称*']
  assert.deepEqual(diffNodes(again, a.nodes).map(c => [c.kind, c.props]), [['edit', ['fields']]])
  assert.deepEqual(diffNodes(clone(a.nodes), a.nodes), [])
})

test('和原型对不对得上：读到了 / 规划中 / 原型里已经没有', () => {
  assert.equal(protoState({ proto: true, seen: true }), 'in')
  assert.equal(protoState({}), 'planned')
  assert.equal(protoState({ seen: true }), 'gone')
})

test('界面接上了：顶栏有「架构」、打开画布才有「架构」模式、只剩画布', () => {
  const header = readFileSync(new URL('../src/components/layout/AppHeader.vue', import.meta.url), 'utf8')
  const board = readFileSync(new URL('../src/components/architecture/ArchitectureBoard.vue', import.meta.url), 'utf8')
  const node = readFileSync(new URL('../src/components/architecture/ArchNode.vue', import.meta.url), 'utf8')
  const logic = readFileSync(new URL('../src/composables/useArchitecture.js', import.meta.url), 'utf8')
  const panel = readFileSync(new URL('../src/components/layout/ConversationPanel.vue', import.meta.url), 'utf8')
  assert.match(header, /@click="showArch"/)
  assert.match(panel, /\.\.\.\(archOpen \? \[\{ value: 'architecture', label: '架构'/)
  assert.match(logic, /composerIntent\.value = 'architecture'/)
  assert.match(appSource(), /intent !== 'architecture'/)                 // 画布开着时，别的模式把画布当背景
  assert.match(appSource(), /result\.intent === 'architecture'[\s\S]*afterArchChat/)
  assert.match(node, /s\.makeInPrototype\(node\)/)
  assert.doesNotMatch(board, /业务流程|数据关系|统一规则|同步到原型|arch-sub|展开到/)
  assert.match(logic, /key === 'Enter'[\s\S]*archSibling/)
  assert.match(logic, /key === 'Tab'[\s\S]*archAdd/)
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
