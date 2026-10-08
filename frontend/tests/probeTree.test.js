import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildTree, cardDocument, thumbFrame, trailOf, shortLabel } from '../src/probeTree.js'

// 真实场景：环境影响因子库管理，「新增因子」先选类型，点下一步再按类型进到不同表单
const nodes = [
  { id: 1, parent: null, label: '行业分类 +', title: '新增行业分类' },
  { id: 2, parent: null, label: '新增因子', title: '新增因子' },
  { id: 3, parent: 2, label: '下一步 · 运输因子', title: '新增运输因子' },
  { id: 4, parent: 2, label: '下一步 · GWP值（温室气体）', title: '新增 GWP 值' },
]

test('按谁打开了谁挂成树，弹窗挂在它的按钮链下面而不是单独列出来', () => {
  const tree = buildTree(nodes)
  assert.deepEqual(tree.map(n => n.title), ['新增行业分类', '新增因子'])
  assert.deepEqual(tree[1].children.map(n => n.title), ['新增运输因子', '新增 GWP 值'])
  assert.equal(tree[0].children.length, 0)
})

test('父节点丢了的当顶层，不会整条消失', () => {
  assert.deepEqual(buildTree([{ id: 9, parent: 7, title: 'x' }]).map(n => n.id), [9])
})

test('路径从顶层按钮一路写到这个弹窗', () => {
  assert.equal(trailOf(nodes, nodes[2]), '新增因子 › 下一步 · 运输因子')
})

test('卡片快照带样式、不带脚本，还关掉了淡入动画', () => {
  const doc = cardDocument({ head: '<style>.modal{color:red}</style>', base: 'http://127.0.0.1:5173/preview-assets/p/', html: { class: 'a"b' }, body: { class: 'app' } }, '<div class="modal">新增因子</div>')
  assert.match(doc, /<base href="http:\/\/127\.0\.0\.1:5173\/preview-assets\/p\/">/)
  assert.match(doc, /\.modal\{color:red\}/)
  assert.match(doc, /animation:none!important/)
  assert.match(doc, /<html class="a&quot;b">/, '属性里的引号要转义，不然整页结构被截断')
  assert.doesNotMatch(doc, /<script/)
})

test('相对的 base（about:srcdoc 这类）不写进去，免得样式和图片全挂', () => {
  assert.doesNotMatch(cardDocument({ base: 'about:srcdoc' }, ''), /<base/)
})

test('缩略图只框住弹窗本体，宽度贴合卡片', () => {
  const t = thumbFrame({ x: 295, y: 292, w: 560, h: 216 }, 248, 196)
  assert.equal(t.width, 248)
  assert.ok(Math.abs(t.scale - 248 / 560) < 1e-9)
  assert.match(t.transform, /^translate\(-130\.\d+px, -129\.\d+px\) scale\(0\.44/)
})

test('小弹窗不无限放大，高弹窗截到上限', () => {
  assert.equal(thumbFrame({ x: 0, y: 0, w: 200, h: 100 }, 248).scale, 0.6)
  assert.equal(thumbFrame({ x: 0, y: 0, w: 1090, h: 2000 }, 248, 196).height, 196)
})

test('进度里的按钮名去掉「表格行」前缀并截短', () => {
  assert.equal(shortLabel('表格行 · 编辑'), '编辑')
  assert.equal(shortLabel('下一步 · 间接排放因子（外购电力/热力）', 10), '下一步 · 间接排放…')
})
