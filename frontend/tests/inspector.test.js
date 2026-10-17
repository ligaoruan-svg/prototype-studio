// 编辑模式的属性面板：分组齐全、图层能换着选、几条样式一次改
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const panel = readFileSync(new URL('../src/components/layout/InspectorPanel.vue', import.meta.url), 'utf8')
const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
const bridge = readFileSync(new URL('../../backend/bridge.py', import.meta.url), 'utf8')

test('属性按 尺寸 / 布局 / 文字 / 填充 / 边框 / 效果 分组', () => {
  for (const name of ['图层', '尺寸', '布局', '文字', '填充', '边框', '效果'])
    assert.match(panel, new RegExp(`<summary>${name}`), name)
})

test('宽高有 适应 / 固定 / 填满 三种', () => {
  for (const key of ['hug', 'fixed', 'fill']) assert.match(panel, new RegExp(`key: '${key}'`))
  assert.match(bridge, /function sizeMode\(/)
})

test('图层：点一下换着选，移上去在页面上框出来', () => {
  assert.match(panel, /@click="selectLayer\(l\.selector\)"/)
  assert.match(panel, /@mouseenter="hoverLayer\(l\.selector\)"/)
  assert.match(app, /type: 'PA_HOVER'/)
  assert.match(bridge, /m\.type==='PA_HOVER'/)
  assert.match(bridge, /send\('SELECTED',detail\(picked\[0\]\)\)/)
})

test('横向排列是一次修改：display 和方向一起提交', () => {
  assert.match(panel, /edit\('display', 'flex', \{ 'flex-direction': key \}\)/)
  assert.match(app, /more: extra/)
})
