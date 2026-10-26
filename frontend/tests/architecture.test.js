// 架构画布：树的增删改移、两棵树比改了什么、和原型对不对得上、界面接上了
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { addChild, addSibling, changeLabel, clone, diffNodes, emptyArchitecture, findNode, impactOf, moveNode, pendingChanges, protoState, removeNode, screens, syncMessage } from '../src/lib/architecture.js'
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
  assert.match(node, /s\.syncToPrototype\(node\.id\)/)                         // 卡片工具条上只同步这一块
  assert.doesNotMatch(board, /业务流程|数据关系|统一规则|arch-sub/)
  assert.match(board, /label: '全部'/)                                    // 一下全展开，不用一个个点
  assert.match(board, /s\.syncToPrototype\(\)/)
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

test('还没同步到原型的：只看原型里看得出来的，原型里删掉的不算；拼成一段话交给 AI', () => {
  const { a, mod, tab1, tab2 } = sample()
  for (const { node } of [...(function* w(ns) { for (const n of ns) { yield { node: n }; yield* w(n.children || []) } })(a.nodes)]) { node.proto = node.seen = true }
  const base = clone(a.nodes)
  tab1.desc = '只写在画布上的介绍'                                   // 不用同步
  const modal = addChild(a, tab2.id, 'modal', '新增巡检点')
  modal.fields = ['点位名称*', '类型*（下拉：温度/压力）']
  addChild(a, modal.id, 'button', '保存')
  mod.name = '设备'
  const gone = addChild(a, tab2.id, 'drawer', '旧抽屉'); gone.seen = true   // 原型里已经没有、画布上还留着
  const changes = pendingChanges(base, a.nodes)
  assert.deepEqual(changes.map(c => c.kind).sort(), ['add', 'rename'])
  assert.deepEqual(changes.map(changeLabel).sort(), ['「新模块」改名为「设备」', '新增弹窗「新增巡检点」'])
  const msg = syncMessage(changes)
  assert.match(msg, /只改下面这几处/)
  assert.match(msg, /在「设备 \/ 设备巡检计划 \/ 巡检点」下面新增 弹窗「新增巡检点」；字段：点位名称\*、类型\*（下拉：温度\/压力）\n {2}- 按钮「保存」/)
  modal.fields = ['点位名称*', '备注']
  const again = pendingChanges(clone(a.nodes), a.nodes)
  assert.deepEqual(again, [])
  const base2 = clone(a.nodes); modal.fields = ['点位名称*']
  assert.match(syncMessage(pendingChanges(base2, a.nodes)), /字段去掉 备注/)
  const fresh = emptyArchitecture('x'); fresh.nodes[0].name = '设备管理'
  assert.ok(pendingChanges(null, fresh.nodes).length === 1)                  // 从零编的：整棵都算
  assert.deepEqual(pendingChanges(null, emptyArchitecture('x').nodes), [])  // 还没起名的「新模块」不算
})

test('卡片上的同步：只同步这一块（连同下面的）', async () => {
  const { changesUnder } = await import('../src/lib/architecture.js')
  const { a, tab1, tab2 } = sample()
  const base = clone(a.nodes)
  const modal = addChild(a, tab2.id, 'modal', '新增巡检点')
  tab1.name = '路线'
  removeNode(a, tab1.children[0].id)
  const all = diffNodes(base, a.nodes)
  assert.deepEqual(changesUnder(a, all, tab2.id).map(c => c.id), [modal.id])
  assert.deepEqual(changesUnder(a, all, tab1.id).map(c => c.kind).sort(), ['remove', 'rename'])   // 删掉的子项也算这一块
})

test('没有记下的改动也能同步：照画布核对这一块 / 整个原型', async () => {
  const { checkMessage } = await import('../src/lib/architecture.js')
  const { a, tab1 } = sample()
  const msg = checkMessage(a, tab1)
  assert.match(msg, /核对原型里的「新模块 \/ 设备巡检计划 \/ 路线配置」这一页签/)
  assert.match(msg, /页签「路线配置」\n {2}- 抽屉「路线详情」/)
  assert.match(checkMessage(a), /核对整个原型/)
})

test('同步卡片：点好几块合成一张，上下级不重复', async () => {
  const { syncIds, syncAttachFor } = await import('../src/lib/architecture.js')
  const a = emptyArchitecture()
  const m = addChild(a, '', 'module'); m.name = '报修管理'
  const p1 = addChild(a, m.id, 'page'); p1.name = '工单列表'
  const p2 = addChild(a, '', 'page'); p2.name = '维修工'
  const base = clone(a.nodes)
  p1.fields = ['备注']
  const changes = pendingChanges(base, a.nodes)
  let ids = syncIds(a, [], p1.id)
  ids = syncIds(a, ids, p2.id)
  assert.deepEqual(ids, [p1.id, p2.id])
  const card = syncAttachFor(a, changes, ids)
  assert.equal(card.title, '同步「工单列表」「维修工」到原型')
  assert.equal(card.items.length, 2)
  assert.match(card.message, /另外：/)
  assert.deepEqual(syncIds(a, ids, m.id), [p2.id, m.id])   // 点上层：下面的并进去
  assert.deepEqual(syncIds(a, [m.id], p1.id), [m.id])      // 上层已经在：不重复
  assert.deepEqual(syncIds(a, ids, ''), [''])              // 底部按钮：整个
  assert.equal(syncAttachFor(a, changes, ['']).title, '同步到原型')
})
