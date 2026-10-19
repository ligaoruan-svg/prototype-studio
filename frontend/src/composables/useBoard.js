// 展开视图：把这一页的弹窗、子页面铺开看；点卡片后在预览里复现打开路径
import { watch } from 'vue'
import { bindExpand, setFocusRoute } from '../lib/expandStore.js'
import { preparePreviewDocument } from '../lib/previewDocument.js'

export function useBoard(s) {
  const { page, previewDoc, boardOpen, boardRoute, boardFocus, boardMounted, previewRoute, view, mode, send, selected,
    project, pageId, previewOwner, previewHash, canvasWidth, loading, openedModal, pendingReplay, inspection, textValue,
    rightOpen, leftOpen } = s
  function toggleBoard() {
    if (!page.value || !previewDoc.value) return
    if (boardOpen.value) { showPreview(); return }
    showBoard()
  }
  // 展开是一种查看方式：在里面只能点选或拉框，「交互」要回到预览
  function showBoard() {
    if (!page.value || !previewDoc.value) return
    if (!boardOpen.value) boardRoute.value = previewRoute.value
    boardMounted.value = true
    view.value = 'preview'; boardOpen.value = true
    // 展开主要是用来选中修改的：从预览的交互模式进来，默认切到点选；想交互再切回去
    if (mode.value === 'interact') { mode.value = 'select'; send({ type: 'PA_SET_MODE', mode: 'select' }) }
  }
  // 从展开视图回到预览：预览跟到展开里正在看的那一页
  // 预览和展开都一直挂着，切换只是换哪个露在前面：不重载、不重拍，点一下就到
  function showPreview() { if (boardOpen.value) gotoRoute(boardRoute.value); view.value = 'preview'; boardOpen.value = false; boardFocus.value = null }
  // 预览跟到展开里正在看的那一页：原型是单页应用，换个 #路由 就行，不用整页重载
  function gotoRoute(route) { if (route == null || route === previewRoute.value) return; previewRoute.value = route; send({ type: 'PA_ROUTE', hash: route }) }
  // 后台副本的源码：和预览同一份、同样的演示数据，只是路由换成要展开的那一页；它点出来的改动不会写回来
  function makeProbeDoc(route, html = previewDoc.value) {
    let stored = {}
    try { stored = JSON.parse(localStorage.getItem(s.runtimeKey()) || '{}') } catch {}
    return preparePreviewDocument(html.replace(/\n<!-- pa-open \d+ -->$/, ''), { stored, route, scroll: null, probe: true })
  }
  watch([boardOpen, boardRoute, previewRoute], () => setFocusRoute(boardOpen.value ? boardRoute.value : previewRoute.value), { immediate: true })
  // 换页、提交新版本时告诉展开总管：已展开过的页面会在后台自动同步
  // 只在新项目 / 新页面的源码真正载入后才绑：切项目那一刻 project 已经换了、预览还是旧的，
  // 以前就是拿旧原型去展开、结果还存进了新项目。源码在绑定时定格，后台展开用的永远是这一版
  watch([previewOwner, previewHash], ([owner, hash]) => {
    const pid = project.value?.id, id = pageId.value, html = previewDoc.value
    if (!pid || !id || !hash || !html || owner !== `${pid}:${id}`) return
    bindExpand({ pid, pageId: id, hash, makeDoc: route => makeProbeDoc(route, html), width: canvasWidth.value || 1150 })
  })
  // 在展开视图的卡片里点选：和预览里点选走同一条路，改的是同一份源码
  async function pickFromBoard(data) {
    if (loading.value) return
    openedModal.value = data.modal ? { title: data.modal, trail: data.trail || '' } : null
    send({ type: 'PA_SELECT', selector: '' })
    if (data.kind === 'region') { selected.value = data; inspection.value = { editable: false, kind: 'region' }; textValue.value = data.text; rightOpen.value = true; if (window.innerWidth <= 960) leftOpen.value = false; return }
    await s.inspect(data)
  }
  // 预览重新载入：带上最新的路由、滚动位置和演示数据。结尾的编号保证 srcdoc 一定变化、一定重载。
  function reseedPreview() {
    if (previewDoc.value) previewDoc.value = s.forceReload(s.preparePreview(previewDoc.value))
  }
  function openFromBoard(node) {
    // 页面本身：预览切到那一页就行
    if (node.isPage) { gotoRoute(node.route ?? boardRoute.value); boardOpen.value = false; boardFocus.value = null; return }
    // 先把预览重新载入到干净的页面状态，再按记下的路径一步步点开
    pendingReplay.value = node; openedModal.value = null
    previewRoute.value = node.route ?? boardRoute.value   // 在展开视图里切到了别的页，预览也跟过去
    boardOpen.value = false; boardFocus.value = null
    s.setMode('select')
    reseedPreview()   // 只有「在预览中打开某个弹窗」才需要重载：回到干净状态再按路径点开
  }
  return { toggleBoard, showBoard, showPreview, gotoRoute, makeProbeDoc, pickFromBoard, openFromBoard }
}
