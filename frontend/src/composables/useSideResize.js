// 左边对话栏可以拖宽拖窄：AI 的话、代码片段长的时候拉宽看，改页面时收窄给画布让地方。
// 宽度记在本机，下次打开还是这个宽；双击分隔线回到默认
import { onMounted, onUnmounted, ref } from 'vue'

const KEY = 'pa-side-width'
const MIN = 260
// 画布至少留这么宽：再窄原型就看不清了
const CANVAS_MIN = 480
const maxWidth = () => Math.max(MIN, Math.min(760, window.innerWidth - CANVAS_MIN))
const clamp = w => Math.round(Math.min(maxWidth(), Math.max(MIN, w)))

export function useSideResize() {
  const sideWidth = ref(0)   // 0 = 用默认宽度（样式表里的 --left-width）
  try { const saved = Number(localStorage.getItem(KEY)); if (saved > 0) sideWidth.value = clamp(saved) } catch { /* 读不到就用默认 */ }
  const save = () => { try { sideWidth.value ? localStorage.setItem(KEY, String(sideWidth.value)) : localStorage.removeItem(KEY) } catch { /* 存不上就只管这一次 */ } }
  const dragging = ref(false)

  function startResize(event) {
    if (event.button !== 0) return
    event.preventDefault()
    const handle = event.currentTarget
    const left = handle.parentElement.getBoundingClientRect().left
    dragging.value = true
    // 拖的时候鼠标会滑进预览 iframe，事件就被它吃掉了：拖动期间让 iframe 不接鼠标
    document.body.classList.add('resizing-side')
    try { handle.setPointerCapture(event.pointerId) } catch { /* 老浏览器没有也能拖 */ }
    const move = e => { sideWidth.value = clamp(e.clientX - left) }
    const end = () => {
      dragging.value = false
      document.body.classList.remove('resizing-side')
      handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', end); handle.removeEventListener('pointercancel', end)
      save()
    }
    handle.addEventListener('pointermove', move); handle.addEventListener('pointerup', end); handle.addEventListener('pointercancel', end)
  }
  function resetWidth() { sideWidth.value = 0; save() }
  // 键盘也能调：左右方向键每次 16 像素
  function nudge(event) {
    const step = event.key === 'ArrowLeft' ? -16 : event.key === 'ArrowRight' ? 16 : 0
    if (!step) return
    event.preventDefault()
    const now = sideWidth.value || event.currentTarget.parentElement.querySelector('.conversation-panel, .inspector')?.getBoundingClientRect().width || 312
    sideWidth.value = clamp(now + step); save()
  }
  // 窗口变窄了：别让对话栏把画布挤没
  const fit = () => { if (sideWidth.value) sideWidth.value = clamp(sideWidth.value) }
  onMounted(() => window.addEventListener('resize', fit))
  onUnmounted(() => window.removeEventListener('resize', fit))
  return { sideWidth, dragging, startResize, resetWidth, nudge }
}
