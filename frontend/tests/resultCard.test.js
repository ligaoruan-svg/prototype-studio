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

test('点选可以多选，同一种改动不用一条一条写', () => {
  // 表单里散着好几个「手工填写」标签，框选框不到一起，
  // 只能点一个写一条实在不合理。Shift / ⌘ 点击往选中里加减。
  assert.match(bridge, /e\.shiftKey\|\|e\.metaKey\|\|e\.ctrlKey/)
  assert.match(bridge, /picked\.splice\(at, ?1\)/)
  assert.match(bridge, /picked\.length<16/)      // 有上限，别一口气选上百个
})

test('选中几处就画几个框，多选才标序号', () => {
  assert.match(bridge, /function paintPicks/)
  assert.match(bridge, /picked\.length>1\?'block':'none'/)
})

test('多选走和拉框同一条路', () => {
  // 复用已经跑通的 targets 数组，不另起一套
  assert.match(bridge, /picked\.length===1.*?SELECTED/s)
  assert.match(bridge, /REGION_SELECTED.*?kind:'region'.*?targets/s)
})

test('取消掉最后一个会通知父层清空', () => {
  assert.match(bridge, /SELECTION_CLEARED/)
  assert.match(app, /SELECTION_CLEARED'\) clearSelectionOnly\(\)/)
})

test('模型的旁白和它接下来做的事排在一起', () => {
  // 以前只看得到一串工具名（查找「绿电」、读取相关代码），
  // 判断不出它在正经干活还是在瞎转。旁白要按轮次插进步骤列表。
  assert.match(app, /note_delta/)
  assert.match(app, /kind: 'note'/)
  assert.match(card, /step\.kind === 'note'/)
})

test('旁白不会被下一轮擦掉', () => {
  // model_wait 会清空 streamText；旁白如果也走那个变量，每换一轮就没了。
  assert.match(app, /current\.steps\.push\(\{ id: 'note-'/)
  assert.doesNotMatch(app, /note_delta'\) current\.streamText/)
})

test('旁白和最终结论走不同通道', () => {
  const client = readFileSync(new URL('../../backend/deepseek_client.js', import.meta.url).pathname.replace('.js', '.py'), 'utf8')
  assert.match(client, /on_delta\(delta\['content'\], 'note'\)/)
  assert.match(client, /'result'\)/)
})

test('提示词要求它边做边说', () => {
  const prompt = readFileSync(new URL('../../prompts/agent-system.md', import.meta.url), 'utf8')
  assert.match(prompt, /# 边做边说/)
  assert.match(prompt, /调工具之前，先用一句话说/)
})
