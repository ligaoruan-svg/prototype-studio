// 对话记录里的用户消息要显示当时带的截图和点选位置（以前只在发送那一刻显示）
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { appSource } from './appSource.js'

const panel = readFileSync(new URL('../src/components/layout/ConversationPanel.vue', import.meta.url), 'utf8')

test('历史消息显示截图和点选位置', () => {
  assert.match(panel, /v-if="message\.role === 'user' && message\.image"/)
  assert.match(panel, /\/chat-images\/\$\{message\.image\}/)
  assert.match(panel, /message\.target/)
})

test('改好保存后，点选 / 框选的目标自动取消', () => {
  const app = appSource()
  assert.match(app, /current\.committed = true; (s\.)?closeSelection\(\)/)
})

test('讨论卡：建议改好之后打勾、不再挂「按这个改」', () => {
  const card = readFileSync(new URL('../src/components/chat/ResultCard.vue', import.meta.url), 'utf8')
  assert.match(card, /applied: \{ type: Array/)
  assert.match(card, /v-if="!allDone" class="primary suggest-apply"/)
  assert.match(panel, /:applied="appliedFor\(message\)"/)
})
