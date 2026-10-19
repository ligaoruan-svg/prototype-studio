// 对话记录里的用户消息要显示当时带的截图和点选位置（以前只在发送那一刻显示）
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const panel = readFileSync(new URL('../src/components/layout/ConversationPanel.vue', import.meta.url), 'utf8')

test('历史消息显示截图和点选位置', () => {
  assert.match(panel, /v-if="message\.role === 'user' && message\.image"/)
  assert.match(panel, /\/chat-images\/\$\{message\.image\}/)
  assert.match(panel, /message\.target/)
})

test('改好保存后，点选 / 框选的目标自动取消', () => {
  const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  assert.match(app, /current\.committed = true; closeSelection\(\)/)
})
