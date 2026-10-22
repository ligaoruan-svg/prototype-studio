// AI 改到一半要真跑一下页面：后台发来 page_check 事件，这里取那份还没保存的页面，
// 在看不见的副本里跑（打开 / 点一遍 / 量一下），把结果交回后台，后台再交给 AI
import { pageCheck } from '../lib/probe.js'

export function usePageCheck(s) {
  async function runPageCheck(event) {
    let result
    try {
      const response = await fetch(`/api/page-checks/${event.id}/preview`)
      if (!response.ok) throw new Error('取不到要检查的页面')
      const html = await response.text()
      result = await pageCheck({ kind: event.kind, args: event.args || {}, makeDoc: route => s.makeProbeDoc(route, html), width: s.canvasWidth.value || 1200 })
    } catch (e) { result = { error: String(e?.message || e) } }
    result.baseline = [...s.runtimeErrors.value]   // 预览里本来就有的报错：不算这次改出来的
    try { await fetch(`/api/page-checks/${event.id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(result) }) } catch { /* 后台等不到会按超时处理 */ }
  }
  return { runPageCheck }
}
