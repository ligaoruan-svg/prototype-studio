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

import { pickToSelection, CARD_SCRIPT } from '../src/probeTree.js'

const gwp = { id: 7, title: '新增 GWP 值', layerSel: '#modal', label: '下一步 · GWP值' }

test('卡片里点中一个元素 → 选择器对回真实页面，并带上所在弹窗', () => {
  const sel = pickToSelection(gwp, [{ rel: 'div.modal > div:nth-of-type(2) > input', tag: 'input', text: '', outer_html: '<input>' }])
  assert.equal(sel.selector, '#modal > div.modal > div:nth-of-type(2) > input')
  assert.equal(sel.modal, '新增 GWP 值')
  assert.deepEqual(sel.card, { nodeId: 7, rels: ['div.modal > div:nth-of-type(2) > input'] })
  assert.equal(sel.kind, undefined, '单选走普通选中，能进属性面板')
})

test('Shift 多选同一张卡片 → 和预览里多选一样是一组 targets', () => {
  const sel = pickToSelection(gwp, [
    { rel: 'div > label:nth-of-type(1)', tag: 'label', text: '温室气体', outer_html: '<label>温室气体</label>' },
    { rel: 'div > label:nth-of-type(2)', tag: 'label', text: 'GWP 值', outer_html: '<label>GWP 值</label>' },
  ])
  assert.equal(sel.kind, 'region')
  assert.deepEqual(sel.targets.map(t => t.selector), ['#modal > div > label:nth-of-type(1)', '#modal > div > label:nth-of-type(2)'])
  assert.ok(sel.targets.every(t => t.modal === '新增 GWP 值'))
  assert.equal(sel.text, '温室气体 · GWP 值')
})

test('能点选的卡片才带脚本，页面缩略图仍然是纯静态', () => {
  assert.match(cardDocument({}, '<div data-pa-layer></div>', { pickable: true }), /CARD_PICK/)
  assert.doesNotMatch(cardDocument({}, '<div></div>'), /<script/)
  assert.doesNotThrow(() => new Function(CARD_SCRIPT), '注入的脚本至少要能被解析')
})

import { originOf, crumbOf, ORIGIN_LABEL } from '../src/probeTree.js'

test('卡片按从哪儿打开分组：页面按钮 / 列表行 / 弹窗里的下一步', () => {
  assert.equal(originOf({ isPage: true }), 'page')
  assert.equal(originOf(nodes[0]), 'button')
  assert.equal(originOf({ id: 9, parent: null, label: '表格行 · 编辑' }), 'row')
  assert.equal(originOf(nodes[2]), 'step')
  assert.equal(ORIGIN_LABEL.row, '列表行操作')
})

test('来源一行写清楚是怎么点开的', () => {
  assert.equal(crumbOf(nodes, nodes[2]), '页面按钮 → 新增因子 → 下一步 · 运输因子')
  assert.equal(crumbOf([{ id: 1, parent: null, label: '表格行 · 设为当前版本' }], { id: 1, parent: null, label: '表格行 · 设为当前版本' }), '列表行 → 设为当前版本')
  assert.equal(crumbOf(nodes, { isPage: true }), '当前页面')
})

test('页面卡片里点中的是静态元素：选择器从 body 往下，不挂弹窗', () => {
  const sel = pickToSelection({ id: 0, isPage: true, title: '环境影响因子库清单' }, [{ rel: 'div.app > main > h1', tag: 'h1', text: '环境影响因子库清单', outer_html: '<h1>' }], '环境影响因子库清单')
  assert.equal(sel.selector, 'body > div.app > main > h1')
  assert.equal(sel.modal, '')
  assert.equal(sel.place, '环境影响因子库清单')
})

test('弹窗卡片的选中带上位置：页面 › 弹窗', () => {
  const sel = pickToSelection(gwp, [{ rel: 'p', tag: 'p', text: '说明', outer_html: '<p>' }], '环境影响因子库管理')
  assert.equal(sel.place, '环境影响因子库管理 › 新增 GWP 值')
  assert.equal(sel.viewTitle, '新增 GWP 值')
})

test('卡片拉框用指针事件：取消 pointerdown 会让浏览器吞掉后面的 mousedown/mouseup，拉框就永远开始不了', () => {
  assert.match(CARD_SCRIPT, /addEventListener\('pointerdown'/)
  assert.match(CARD_SCRIPT, /addEventListener\('pointerup'/)
  assert.doesNotMatch(CARD_SCRIPT, /addEventListener\('mouseup'/)
})
