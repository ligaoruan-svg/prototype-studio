// 和预览 iframe 之间的消息：原型里点选、框选、画笔、路由、报错、点击记录……都从这里进来
import { nextTick } from 'vue'

export function usePreviewBridge(s) {
  const { previewFrame, previewDoc, project, pageId, send, mode, tool, selected, loading, inspection, textValue, rightOpen, leftOpen,
    previewScroll, canvasWidth, pendingReplay, openedModal, pendingHighlights, previewRoute, boardOpen, boardRoute,
    runtimeErrors, recentClicks, api, endpoint, error, toast } = s
  // 预览框载入以后没等到原型的 READY：多半被页面脚本带到了别处（表单提交、location.reload 在 srcdoc 里会变成浏览器错误页）。
  // 重新载入一次源码，别让人对着一张「网页无法连接」
  // READY 在 DOMContentLoaded 就发了，比 iframe 的 load 早：看「上一次 load 以来」有没有收到过
  let lastReadyAt = 0, lastLoadAt = 0, rescued = 0
  function previewLoaded() {
    const since = lastLoadAt; lastLoadAt = Date.now()
    setTimeout(() => {
      if (lastReadyAt > since || !previewDoc.value) { rescued = 0; return }
      if (rescued++ >= 2) return
      previewDoc.value = s.forceReload(previewDoc.value)
      toast('预览被页面脚本带走了，已重新载入')
    }, 2500)
  }
  async function inspect(target) {
    selected.value = target; inspection.value = null; textValue.value = target.text
    if (!target.refresh) { rightOpen.value = true; if (window.innerWidth <= 960) leftOpen.value = false }
    try {
      const extra = target.styleSel ? '&style_selector=' + encodeURIComponent(target.styleSel) + (target.leaf && target.text ? '&text=' + encodeURIComponent(target.text.slice(0, 200)) : '') : ''
      const result = await api(endpoint('/inspect') + '?selector=' + encodeURIComponent(target.selector) + extra)
      if (selected.value?.selector !== target.selector) return
      inspection.value = result
      if (result.text_editable) textValue.value = result.text
    } catch (e) {
      if (selected.value?.selector !== target.selector) return
      error.value = e.message
      inspection.value = { editable: false, failed: true }   // 别一直转「定位中」：说清没定位到，还可以写意见给 AI
    }
  }
  async function onMessage(event) {
    if (event.source !== previewFrame.value?.contentWindow) return
    const data = event.data || {}
    if (data.source !== 'prototype-agent' || data.projectId !== project.value?.id || data.pageId !== pageId.value) return
    if (data.type === 'READY') {
      lastReadyAt = Date.now()
      send({ type: 'PA_SET_MODE', mode: mode.value })
      send({ type: 'PA_SET_DRAG', enabled: tool.value === 'comment' })
      send({ type: 'PA_RENDER_MARKERS', annotations: s.visiblePins() })
      if (selected.value && selected.value.kind !== 'region' && !selected.value.card) send({ type: 'PA_SELECT', selector: selected.value.selector })
    }
    if (data.type === 'SELECTED' && !loading.value) await inspect(data)
    if (data.type === 'DRAWING' && !loading.value) {
      if (!data.count) { s.drawing.value = null; if (selected.value?.drawing) s.clearSelectionOnly(); return }
      s.drawing.value = { count: data.count, redo: data.redo || 0 }
      selected.value = data; inspection.value = { editable: false, kind: 'region' }; rightOpen.value = true
      nextTick(() => s.drawInput.value?.focus())
    }
    if (data.type === 'DRAW_SHOT') s.shotArrived(data)
    if (data.type === 'REGION_SELECTED' && !loading.value) { selected.value = data; inspection.value = { editable: false, kind: 'region' }; textValue.value = data.text; rightOpen.value = true; if (window.innerWidth <= 960) leftOpen.value = false }
    if (data.type === 'NOTICE') toast(data.message)
    if (data.type === 'SELECTION_MISSING') s.closeSelection()
    if (data.type === 'SELECTION_CLEARED') s.clearSelectionOnly()   // 按住 Shift 把最后一个也取消掉了
    if (data.type === 'SCROLL_STATE') previewScroll.value = data.state
    if (data.type === 'WIDTH') canvasWidth.value = data.width
    // 预览里按的快捷键转过来；⌘↵（发给 AI）不收——原型里的脚本也能伪造这条消息，不能让它替你发需求
    if (data.type === 'SHORTCUT' && !(data.key === 'Enter' || data.key === 'enter')) s.keydown(data)
    if (data.type === 'LOADED' && pendingReplay.value) { const node = pendingReplay.value; pendingReplay.value = null; setTimeout(() => send({ type: 'PA_REPLAY', path: node.path }), 450); openedModal.value = { title: node.title, trail: node.trail, pending: true } }
    if (data.type === 'REPLAYED') {
      if (data.ok) { openedModal.value = { title: data.title || openedModal.value?.title, trail: openedModal.value?.trail || '' }; toast(`已打开「${openedModal.value.title}」，直接点选要改的地方`) }
      else { openedModal.value = null; toast('没能自动打开这个弹窗，可以在预览里切到交互模式手动点开') }
    }
    if (data.type === 'LOADED' && pendingHighlights.value.length) { send({ type: 'PA_HIGHLIGHT', targets: pendingHighlights.value }); pendingHighlights.value = [] }
    if (data.type === 'ROUTE') { previewRoute.value = data.hash; if (boardOpen.value && !boardRoute.value) boardRoute.value = data.hash }
    if (data.type === 'STORAGE') { try { localStorage.setItem(s.runtimeKey(), JSON.stringify(data.data)) } catch {} }
    if (data.type === 'RUNTIME_ERROR' && !runtimeErrors.value.includes(data.message)) runtimeErrors.value.push(data.message)
    // 预览里真点过的几下（点了什么、有没有反应、报没报错）：发需求时一起交给 AI，「点了没反应」它就知道是哪个
    if (data.type === 'CLICK_TRACE') recentClicks.value = [...recentClicks.value, { label: data.label, selector: data.selector, tag: data.tag, hashBefore: data.hashBefore, hashAfter: data.hashAfter, changed: !!data.changed, opened: !!data.opened, errors: data.errors || [], at: Date.now() }].slice(-6)
    if (data.type === 'NAVIGATE') {
      try { const resolved = await api(`/api/projects/${project.value.id}/resolve?href=${encodeURIComponent(data.href)}&page_id=${pageId.value}`); if (resolved.page_id) await s.choosePage(resolved.page_id); else toast('导入的项目中没有这个页面') } catch (e) { error.value = e.message }
    }
  }
  return { previewLoaded, inspect, onMessage }
}
