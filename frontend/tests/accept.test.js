// 按业务梳理验收：清单从梳理来，系统 / 外部角色做的不找按钮；界面接上了
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { acceptRequest, acceptSummary, checklist, itemText, parseAction } from '../src/lib/accept.js'
import { appSource } from './appSource.js'

const spec = {
  status: 'confirmed', roles: [{ name: '调度员' }, { name: '维修工' }],
  objects: [{ name: '工单', actions: ['派单：待派单→处理中（调度员）', '退回：处理中/已挂起→待派单（维修工）', '评价：已完成→已评价（业主）', '超时升级：待派单→待派单（系统）', '随便写的一句'] }],
}

test('动作写法：从、到、谁；多个起点；系统和外部角色不在后台点', () => {
  assert.deepEqual(parseAction('派单：待派单→处理中（调度员）', ['调度员']), { action: '派单', from: ['待派单'], to: '处理中', who: '调度员', ui: true })
  assert.deepEqual(parseAction('退回: 处理中/已挂起 -> 待派单').from, ['处理中', '已挂起'])
  assert.equal(parseAction('超时升级：待派单→待派单（系统）').ui, false)
  assert.equal(parseAction('评价：已完成→已评价（业主）', ['调度员']).ui, false)
  assert.equal(parseAction('随便写的一句'), null)
  assert.deepEqual(parseAction('生成：—→待核对（财务对账员）', ['财务对账员']).from, [])   // 起点是空的：新建一条
  const close = parseAction('关闭：待派单→已关闭（客服，需填原因；超时的标红）', ['物业客服'])
  assert.deepEqual([close.who, close.ui], ['客服', true])   // 后面是说明，「客服」就是「物业客服」
  assert.equal(parseAction('评价：待评价→已完成（业主在小程序评价后自动更新）', ['物业客服']).ui, false)
  assert.equal(parseAction('启用：停用→在岗（系统管理员）', ['主管', '系统管理员']).ui, true)   // 角色名里带「系统」也是人
  assert.equal(parseAction('自动完成：待评价→已完成（系统，满 7 天）', ['主管', '系统管理员']).ui, false)
})

test('清单只从确认过的梳理来，写不成「动作：从→到」的跳过', () => {
  assert.deepEqual(checklist({ ...spec, status: 'draft' }), [])
  const items = checklist(spec)
  assert.equal(items.length, 4)
  assert.equal(itemText(items[0]), '「待派单」的工单点「派单」→ 变成「处理中」')
  assert.equal(itemText({ object: '对账单', action: '生成', from: [], to: ['待核对'], ui: true }), '新建对账单：点「生成」→ 变成「待核对」')
  assert.match(itemText(items[2]), /业主做，不在后台点/)
  const both = checklist({ status: 'confirmed', roles: [{ name: '客服' }], objects: [{ name: '对账', actions: ['导入并核对：待对账→已核对（客服）', '导入并核对：待对账→有差异（客服）'] }] })
  assert.equal(both.length, 1)   // 同一个动作结果二选一：合成一条，到哪个都算
  assert.equal(itemText(both[0]), '「待对账」的对账点「导入并核对」→ 变成「已核对」或「有差异」')
})

test('汇总和交给 AI 的话', () => {
  assert.equal(acceptSummary({ items: [{}, {}, {}], fails: ['x'], missing: ['合同'], skipped: '' }), '按梳理验收：2/3 条流转走通，合同 还没做')
  assert.match(acceptSummary({ skipped: '验收超时' }), /没跑/)
  assert.match(acceptRequest(['甲', '乙']), /^【验收】[\s\S]*\n1\. 甲\n2\. 乙$/)
})

test('界面接上了：改完自检后验收、画布上能手动验收并交给 AI 修', () => {
  const run = readFileSync(new URL('../src/composables/useAgentRun.js', import.meta.url), 'utf8')
  assert.match(run, /s\.checkAccept\(html\)/)
  assert.match(run, /acceptRequest\(acc\.fails\)/)
  const board = readFileSync(new URL('../src/components/architecture/ArchitectureBoard.vue', import.meta.url), 'utf8')
  assert.match(board, /s\.runAcceptance\(\)/)
  assert.match(board, /s\.fixAcceptance\(\)/)
  assert.match(appSource(), /useAccept\(s\)/)
})
