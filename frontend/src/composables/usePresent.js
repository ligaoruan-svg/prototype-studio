// 演示：全屏、收起所有面板，只剩原型本身；Esc 或右上角退出
import { ref } from 'vue'

export function usePresent(s) {
  const { page, previewDoc, boardOpen, send, toast, tool } = s
  const presenting = ref(false)
  // 演示时「退出」按钮别一直压在原型右上角：开始时露 2.5 秒，之后鼠标移到屏幕最上沿再出来
  const exitShown = ref(false)
  let exitTimer = 0
  function peekExit() { clearTimeout(exitTimer); exitShown.value = true }
  function hideExitSoon(delay = 1200) { clearTimeout(exitTimer); exitTimer = setTimeout(() => { exitShown.value = false }, delay) }
  // 用户按 Esc 时浏览器先退全屏、按键传不到页面：跟着退出演示。只认「真进过全屏又退出」，进不去全屏不算
  let wentFullscreen = false
  function startPresent() {
    if (!page.value || !previewDoc.value) return
    if (boardOpen.value) s.showPreview()
    s.closeSelection(); presenting.value = true; s.setMode('interact'); peekExit(); hideExitSoon(2500)
    send({ type: 'PA_RENDER_MARKERS', annotations: [] })
    wentFullscreen = false
    document.documentElement.requestFullscreen?.().catch(() => {})   // 浏览器不让全屏也照样演示（只是没铺满屏幕）
    toast('演示中：按 Esc 退出')
  }
  function stopPresent() {
    if (!presenting.value) return
    presenting.value = false; tool.value = 'browse'
    send({ type: 'PA_RENDER_MARKERS', annotations: s.visiblePins() })
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {})
  }
  if (typeof document !== 'undefined') document.addEventListener('fullscreenchange', () => {
    if (document.fullscreenElement) wentFullscreen = true
    else if (wentFullscreen) { wentFullscreen = false; stopPresent() }
  })
  return { presenting, exitShown, peekExit, hideExitSoon, startPresent, stopPresent }
}
