// 导出展开图：一个独立 HTML，按业务页面分节、每页一棵树，意见挂在对应卡片下
import test from 'node:test'
import assert from 'node:assert/strict'
import { buildExpandExport } from '../src/expandExport.js'

const styles = { head: '<style>.x{color:red}</style>' }
const result = (nodes = []) => ({ title: 'A', styles, page: '<div>page</div>', width: 1000, height: 700, nodes })
const nodes = [
  { id: 1, parent: null, label: '新增', title: '新增弹窗', html: '<div>m</div></script><script>alert(1)</script>', box: { x: 100, y: 100, w: 400, h: 300 } },
  { id: 2, parent: 1, label: '下一步', title: '第二步', html: '<p>2</p>', box: { x: 0, y: 0, w: 400, h: 200 } },
  { id: 3, parent: null, label: '表格行 · 详情', title: '详情', kind: 'subpage', html: '<main>detail</main>' },
]

test('按页面清单导出，没展开的列进目录', () => {
  const r = buildExpandExport({ projectName: '零碳', routes: [{ hash: '#a', title: 'A页' }, { hash: '#b', title: 'B页' }], entries: { '#a': { hash: 'h', result: result(nodes) } }, currentHash: 'h' })
  assert.equal(r.pages, 1); assert.equal(r.views, 4); assert.equal(r.missing, 1)
  assert.match(r.html, /B页<\/td><td>—<\/td><td class="muted">未展开/)
  assert.match(r.html, /<span class="edge" title="下一步">下一步<\/span>/)
  assert.match(r.html, /<i>列表行<\/i>详情/)
  // 树的层级：第二步挂在新增弹窗那一枝下面
  const sub = r.html.split('新增弹窗</h3>')[1]
  assert.ok(sub.indexOf('第二步') < sub.indexOf('详情'), '第二步应在新增弹窗的下一层，排在下一条按钮链之前')
})

test('快照里的 </script> 不会截断导出文件，卡片不跑脚本', () => {
  const r = buildExpandExport({ routes: [{ hash: '#a', title: 'A' }], entries: { '#a': { hash: 'h', result: result(nodes) } }, currentHash: 'h' })
  const data = r.html.split('id="pa-data">')[1].split('</script>')[0]
  const parsed = JSON.parse(data)
  assert.equal(parsed.cards.length, 4)
  assert.ok(parsed.bodies[1].includes('</script>'))
  assert.match(r.html, /setAttribute\('sandbox',''\)/)
})

test('同一套样式只存一份', () => {
  const r = buildExpandExport({ routes: [{ hash: '#a', title: 'A' }, { hash: '#b', title: 'B' }], entries: { '#a': { hash: 'h', result: result(nodes) }, '#b': { hash: 'h', result: result([]) } }, currentHash: 'h' })
  const parsed = JSON.parse(r.html.split('id="pa-data">')[1].split('</script>')[0])
  assert.equal(parsed.styleSets.length, 2)   // 弹窗一份、能滚动的页面一份
})

test('旧版本、没展开完要标出来；意见挂在对应卡片', () => {
  const r = buildExpandExport({ routes: [{ hash: '#a', title: 'A' }], entries: { '#a': { hash: 'old', result: result(nodes) } }, currentHash: 'new',
    notes: [{ note: '标题改短', in_modal: '新增弹窗', view_route: '#a' }, { note: '别的页面的', in_modal: '新增弹窗', view_route: '#z' }] })
  assert.match(r.html, /不是最新版本/)
  assert.match(r.html, /标题改短/)
  assert.doesNotMatch(r.html, /别的页面的/)
})
