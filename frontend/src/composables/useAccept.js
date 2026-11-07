// 按业务梳理验收：AI 改完页面自动跑（useAgentRun 的自检里），架构画布上也能手动点「验收」
import { ref } from 'vue'
import { acceptRequest, runAccept } from '../lib/accept.js'

export function useAccept(s) {
  const acceptReport = ref(null), accepting = ref(false)
  // 只认用户确认过的梳理；没有就不验（返回 null）
  async function checkAccept(html) {
    await s.loadArch().catch(() => {})
    const spec = s.arch.value?.spec
    if (spec?.status !== 'confirmed' || !html) return null
    const report = await runAccept({ spec, makeDoc: route => s.makeProbeDoc(route, html), width: s.canvasWidth.value || 1200 })
    acceptReport.value = report
    return report
  }
  async function runAcceptance() {
    if (accepting.value) return
    accepting.value = true
    try { await checkAccept(s.previewDoc.value) } finally { accepting.value = false }
  }
  function fixAcceptance() {
    const fails = acceptReport.value?.fails || []
    if (!fails.length || s.locked.value) return
    s.showPreview()
    s.runAgent(acceptRequest(fails), '', { intent: 'edit', selfReview: 1, display: { kind: 'check', title: `验收没过 ${fails.length} 条，交给 AI 修`, items: fails } })
  }
  return { acceptReport, accepting, checkAccept, runAcceptance, fixAcceptance }
}
