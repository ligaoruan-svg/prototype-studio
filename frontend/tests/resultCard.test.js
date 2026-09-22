import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('../src/ResultCard.vue', import.meta.url), 'utf8')
const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

test('every event the card fires is declared', () => {
  const declared = source.match(/defineEmits\(\[([^\]]*)\]\)/)[1].match(/'([^']+)'/g).map(s => s.slice(1, -1))
  const fired = [...source.matchAll(/\$emit\('([^']+)'/g)].map(m => m[1])
  for (const name of fired) assert.ok(declared.includes(name), `未声明的事件：${name}`)
  for (const name of declared) assert.ok(app.includes(`@${name}=`), `App 未监听：${name}`)
})

test('choosing a clarification option carries the question it answers', () => {
  assert.match(source, /\$emit\('choose', \{ option, clarification: result\.clarification \}\)/)
})

test('a discussion reply renders its answer and its suggestions', () => {
  assert.match(source, /discussion\?\.suggestions\?\.length/)
  assert.match(source, /\$emit\('apply', \{ suggestion, discussion \}\)/)
  assert.match(source, /discussion\.value\?\.answer/)
})

test('超出圈定范围的改动会在卡片上提示出来', () => {
  assert.match(source, /report\?\.out_of_scope/)
  assert.match(source, /out_of_scope\.lines/)
  assert.match(source, /out_of_scope\.places\.join/)
})

const card = readFileSync(new URL('../src/ExecutionCard.vue', import.meta.url), 'utf8')
const bridge = readFileSync(new URL('../../backend/bridge.py', import.meta.url), 'utf8')

test('进度标题按实际在做的事显示，不是一律"修改中"', () => {
  // 标题不能再是写死的三元表达式
  assert.doesNotMatch(card, /busy \? '修改中'/)
  assert.match(card, /const heading = computed/)
  assert.match(card, /props\.run\.steps\.length \? '正在看这个页面' : '思考中'/)
  assert.match(card, /run\.editing \? '修改中' : '正在看代码'/)
  assert.match(card, /discussing\.value \? '这次回复未完成' : '这次修改未完成'/)
})

test('那句"改动较大…缩小范围重试"已经去掉', () => {
  // 它在每次超过 30 秒的运行里都会出现，却给不出用户当下能做的事，
  // 整页生成本来就要一分钟以上，等于一直挂在那里吓人。
  assert.doesNotMatch(card, /改动较大/)
  assert.doesNotMatch(card, /slow-note/)
  assert.doesNotMatch(card, /slowNote/)
})

test('只有真的应用过修改才把这次标成修改中', () => {
  assert.match(app, /event\.tool === 'apply_operations' && event\.type === 'step_done'/)
  assert.match(app, /current\.editing = true/)
})

test('记下一条之后会清掉当前选中，好接着标下一处', () => {
  assert.match(app, /clearSelectionOnly\(\)\n?\s*await refresh\(false\)/)
  assert.match(app, /已记下第 \$\{annotations\.value\.length\} 条/)
  assert.match(app, /function clearSelectionOnly\(\)/)
  // 上一次画的框要擦掉，否则残留在画布上
  assert.match(app, /\+\+regionKey\.value/)
  assert.match(app, /:key="regionKey"/)
})

test('框选用命中测试，挡住的元素不再被穿透选中', () => {
  assert.match(bridge, /function visibleAt\(el,x,y\)/)
  assert.match(bridge, /document\.elementFromPoint\(x,y\)/)
  assert.match(bridge, /被弹窗或遮罩挡住了/)
  // 不能再是"只按几何位置筛"
  assert.doesNotMatch(bridge, /return b\.width>0&&b\.height>0&&x>=r\.left&&x<=r\.right&&y>=r\.top&&y<=r\.bottom;\n    \}\)\.filter/)
})
