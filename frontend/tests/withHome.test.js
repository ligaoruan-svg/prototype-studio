import test from 'node:test'
import assert from 'node:assert/strict'
import { withHome } from '../src/probe.js'

test('首页不在菜单链接里：补上「刚打开时那一页」', () => {
  const routes = [{ hash: '#page/0', title: '业务流程总览' }, { hash: '#page/4', title: '实时客流监测' }]
  assert.deepEqual(withHome(routes, '', '门店经营总览')[0], { hash: '', title: '门店经营总览' })
})
test('菜单里已经有同名页面（默认路由）：不重复加', () => {
  const routes = [{ hash: '#factor-list', title: '▦ 环境影响因子库清单' }, { hash: '#boundary', title: '企业碳排边界配置' }]
  assert.equal(withHome(routes, '', '环境影响因子库清单').length, 2)
  assert.equal(withHome(routes, '#boundary', '随便').length, 2)
  assert.equal(withHome(routes, '', '').length, 2)
})
