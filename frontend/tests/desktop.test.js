// 桌面版里存文件走原生「存储为」对话框；浏览器里照旧下载
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('桌面版：有 pywebview 接口就交给它，取消了不报「已导出」', async () => {
  const calls = []
  globalThis.window = { pywebview: { api: { save_text: async (n, t) => { calls.push(['save', n, t]); return false }, download: async u => { calls.push(['dl', u]); return true } } } }
  const { saveFile, downloadUrl, isDesktop } = await import('../src/lib/desktop.js')
  assert.equal(isDesktop(), true)
  assert.equal(await saveFile('a.html', '<p>'), false)
  assert.equal(await downloadUrl('/api/x'), true)
  assert.deepEqual(calls, [['save', 'a.html', '<p>'], ['dl', '/api/x']])
  const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  assert.match(app, /saveFile\(fileName, html\)\.then\(saved =>/)
  assert.match(app, /downloadUrl\(zip \?/)
  assert.doesNotMatch(app, /window\.location\.assign\(zip/)
})
