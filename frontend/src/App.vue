<script setup>
import { computed, nextTick, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { PanelsTopLeft, Plus, Upload, X, Hand, Undo2, Check, LoaderCircle, AlertCircle, Braces, Copy, Pencil } from 'lucide-vue-next'
import { MessageCircle, Redo2, PenLine } from 'lucide-vue-next'
import ExpandBoard from './components/expand/ExpandBoard.vue'
import AppHeader from './components/layout/AppHeader.vue'
import ConversationPanel from './components/layout/ConversationPanel.vue'
import InspectorPanel from './components/layout/InspectorPanel.vue'
import StudioDialog from './components/layout/StudioDialog.vue'
import { adoptPresync, bindExpand, dropPresync, presync, setFocusRoute, expand, expandAll, isFresh } from './lib/expandStore.js'
import { buildExpandExport } from './lib/expandExport.js'
import { previewMessage, PREVIEW_SANDBOX } from './lib/previewMessage.js'
import { preparePreviewDocument } from './lib/previewDocument.js'
import { consumeAgentStream, responseError } from './lib/streamAgent.js'
import { selfTest, selfTestRequest } from './lib/probe.js'

const projects = ref([]), project = ref(null), pageId = ref('')
const sourceInfo = ref({ source: '', hash: '', tokens: {}, defaults: {}, regions: [] })
const model = ref({ model: '', base_url: '', has_key: false, profiles: [] })
// 输入框下面一点就能换模型：保存过的每一套（地址 + 模型 + 密钥）都在这里，不用每次进设置重填
const modelMenu = ref(false), switchingModel = ref(false)
// 常见服务商的模型名，填的时候可以直接选（DeepSeek 目前就这两个，填错名字接口会报 400）
const knownModels = computed(() => /deepseek/i.test(configDraft.value?.base_url || '') ? ['deepseek-flash', 'deepseek-v4-pro'] : [])
async function switchModel(p) {
  if (p.active) { modelMenu.value = false; return }
  switchingModel.value = true
  try { model.value = await api('/api/config/switch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: p.id }) }); modelMenu.value = false; toast(`已切换到 ${p.name || p.model}${p.supports_vision ? '' : '（这个模型看不了图片）'}`) }
  catch (e) { toast(e.message) } finally { switchingModel.value = false }
}
// 点别处收起；点进预览（iframe 里的点击传不到这里，只会让窗口失焦）、按 Esc 也收起
const closeModelMenu = () => { modelMenu.value = false }
const escModelMenu = e => { if (e.key === 'Escape') modelMenu.value = false }
onMounted(() => { window.addEventListener('click', closeModelMenu); window.addEventListener('blur', closeModelMenu); window.addEventListener('keydown', escModelMenu) })
onUnmounted(() => { window.removeEventListener('click', closeModelMenu); window.removeEventListener('blur', closeModelMenu); window.removeEventListener('keydown', escModelMenu) })
const mode = ref('interact'), view = ref('preview'), device = ref('desktop')
const stored = key => { try { return localStorage.getItem(key) } catch { return null } }
const keepInspector = ref(stored('pf-inspector-pinned') === 'true')
// 「始终展开属性面板」在模型设置里勾，勾了马上生效、记在本机
watch(keepInspector, v => { try { localStorage.setItem('pf-inspector-pinned', String(v)) } catch { /* 存不了就只管这次 */ } if (v) rightOpen.value = true })
const leftOpen = ref(window.innerWidth > 960), rightOpen = ref(keepInspector.value)
const showGuide = ref(stored('pf-hide-guide') !== 'true')
const selected = ref(null), inspection = ref(null), textValue = ref(''), note = ref(''), input = ref('')
const busy = ref(false), saving = ref(false), loading = ref(false), status = ref('本地工作区')
const error = ref(''), notice = ref(''), pendingUser = ref(''), pendingRef = ref(null), lastResult = ref(null)
const previewFrame = ref(null), previewDoc = ref(''), composer = ref(null), chatBox = ref(null), fileInput = ref(null)
const dialog = ref(null), dialogType = ref(''), dialogBusy = ref(false), dialogError = ref('')
const configDraft = ref({ base_url: '', model: '', api_key: '' }), projectName = ref(''), brief = ref('')
const codeRegion = ref('all'), codeCopied = ref(false), runtimeErrors = ref([]), recentClicks = ref([]), previewRoute = ref('')
const imageInput = ref(null), reference = ref(null)
const specDraft = ref(''), specSaved = ref(''), specInput = ref(null), specNotice = ref('')
const componentList = ref([]), componentInput = ref(null), specTab = ref('spec')
const memoryCount = ref(0), skillList = ref([])
const fileManagerRevision = ref(0)
const runs = ref([]), canvasWidth = ref(0), previewScroll = ref(null), pendingHighlights = ref([]), savedAt = ref('')
const validationDetails = ref(''), composerIntent = ref('auto'), previewHash = ref('')
const previewOwner = ref('')   // 当前预览源码属于哪个「项目:页面」——切项目时源码还没换完，不能拿旧源码去展开
// 展开视图：把这一页的弹窗铺开看；点卡片后在预览里复现打开路径
const moreMenu = ref(null)
const cardPatch = ref(null)
let patchSeq = 0
const boardMounted = ref(false)   // 展开第一次打开后就一直留着，卡片不用每次重新载入
const boardOpen = ref(false), boardFocus = ref(null), boardRoute = ref(''), pendingReplay = ref(null), openedModal = ref(null)
let reloadNonce = 0
const currentRuns = computed(() => runs.value.filter(r => r.pageId === pageId.value && r.projectId === project.value?.id && !['complete', 'dismissed'].includes(r.status)))
let toastTimer, loadSequence = 0

const page = computed(() => project.value?.pages.find(p => p.id === pageId.value))
const annotations = computed(() => (project.value?.annotations || []).filter(a => a.page_id === pageId.value && a.status === 'active'))
const messages = computed(() => (project.value?.chat || []).filter(m => !m.page_id || m.page_id === pageId.value))
const locked = computed(() => busy.value || saving.value || loading.value)
// 展开里放大交互：演示数据不保存。这时属性面板也不能往源码里写，否则「不保存」和「已保存」同时出现
const playing = computed(() => boardOpen.value && boardFocus.value != null && mode.value === 'interact')   // 页面卡的编号是 0，不能用真假判断
// 脚本生成的元素（源码里没有它的标签）：样式按「同类元素」写规则，文字在源码里能找到原样的那一处就直接换。
// 展开卡片里的快照没有现场 DOM，还是交给 AI
const dynEdit = computed(() => !!selected.value && !selected.value.card && selected.value.kind !== 'region' && !!inspection.value && !inspection.value.editable && !!inspection.value.dynamic && !!selected.value.styleSel)
const canEdit = computed(() => (!!inspection.value?.editable || dynEdit.value) && !locked.value && !playing.value)
const textEditable = computed(() => inspection.value?.editable ? !!inspection.value.text_editable : dynEdit.value && !!selected.value?.leaf && inspection.value?.literal_count === 1)
const undoCount = computed(() => page.value?.undo_count || 0)
const colorNames = { '--color-primary': '主色', '--color-bg': '页面背景', '--color-surface': '表面色', '--color-text': '正文', '--color-muted': '辅助文字', '--color-border': '边框', '--color-danger': '警示', '--color-success': '成功' }
const colors = computed(() => Object.entries({ ...sourceInfo.value.defaults, ...sourceInfo.value.tokens }).filter(([, v]) => /^#[\da-f]{3,8}$/i.test(v.trim())).map(([key, value]) => ({ key, value: value.trim(), label: colorNames[key] || key.replace(/^--/, '') })))
const codeText = computed(() => {
  const source = sourceInfo.value.source
  if (codeRegion.value === 'all') return source
  const start = source.indexOf('#region ' + codeRegion.value), end = source.indexOf('#endregion ' + codeRegion.value, start)
  return start < 0 || end < 0 ? source : source.slice(source.lastIndexOf('\n', start) + 1, source.indexOf('\n', end) < 0 ? source.length : source.indexOf('\n', end))
})
const lineNumbers = computed(() => codeText.value.split('\n').map((_, i) => i + 1).join('\n'))
const endpoint = (suffix = '') => `/api/projects/${project.value.id}/pages/${pageId.value}${suffix}`
const runtimeKey = () => `pf-runtime-${project.value?.id}-${pageId.value}`

async function api(url, options = {}) {
  const response = await fetch(url, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw responseError(data)
  return data
}
const post = (url, body = {}) => api(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
function toast(message) { notice.value = message; clearTimeout(toastTimer); toastTimer = setTimeout(() => notice.value = '', 3000) }
function send(message) { previewFrame.value?.contentWindow?.postMessage(previewMessage(message), '*') }
function setMode(value) { mode.value = value === 'box' ? 'select' : value; if (view.value === 'code') view.value = 'preview'; send({ type: 'PA_SET_MODE', mode: mode.value }); if (window.innerWidth <= 960) { leftOpen.value = false; rightOpen.value = false } }
// 四种用法，参照 Claude Design：浏览（像用户一样点）/ 评论（点一下或拖一个框，留意见给 AI）/
// 编辑（选中直接改属性，不经过 AI）/ 演示（全屏，只剩原型）。底下预览只有两种状态：能点（interact）、能选（select）
const tool = ref('browse')
const TOOLS = [
  { id: 'browse', label: '浏览', key: 'H', icon: Hand, tip: '像真用户一样点、跳转、开弹窗' },
  { id: 'comment', label: '评论', key: 'C', icon: MessageCircle, tip: '点一下元素，或按住拖动在页面上画圈、划线，写意见交给 AI' },
  { id: 'edit', label: '编辑', key: 'V', icon: Pencil, tip: '选中元素，直接改文字、颜色、字号、间距（不调用 AI）；按住 Shift 多选' },
]
function setTool(value) {
  if (value === 'present') { startPresent(); return }
  tool.value = value
  setMode(value === 'browse' ? 'interact' : 'select')
  rightOpen.value = value !== 'browse'   // 评论、编辑：左栏换成评论 / 属性；浏览：回到对话
  if (value === 'comment') toast('点一下元素，或者按住拖动在页面上画，写下怎么改')
  if (value === 'edit') toast('点选要改的元素；按住 Shift 或 ⌘ 可以多选')
}
// 别处（展开、指给它看）直接切了预览的状态：工具跟着变，能选默认算「编辑」
watch(mode, value => {
  if (value === 'interact' && (tool.value === 'comment' || tool.value === 'edit')) tool.value = 'browse'
  if (value !== 'interact' && tool.value === 'browse') tool.value = 'edit'
})
// 演示：全屏、收起所有面板，只剩原型本身；Esc 或右上角退出
// 每次修改的自检结果（按 change_id 挂到对应的结果卡片上；只在这次打开期间有）
const selftests = ref({})
const presenting = ref(false)
// 演示时「退出」按钮别一直压在原型右上角：开始时露 2.5 秒，之后鼠标移到屏幕最上沿再出来
const exitShown = ref(false)
let exitTimer = 0
function peekExit() { clearTimeout(exitTimer); exitShown.value = true }
function hideExitSoon(delay = 1200) { clearTimeout(exitTimer); exitTimer = setTimeout(() => { exitShown.value = false }, delay) }
function startPresent() {
  if (!page.value || !previewDoc.value) return
  if (boardOpen.value) showPreview()
  closeSelection(); presenting.value = true; setMode('interact'); peekExit(); hideExitSoon(2500)
  send({ type: 'PA_RENDER_MARKERS', annotations: [] })
  wentFullscreen = false
  document.documentElement.requestFullscreen?.().catch(() => {})   // 浏览器不让全屏也照样演示（只是没铺满屏幕）
  toast('演示中：按 Esc 退出')
}
function stopPresent() {
  if (!presenting.value) return
  presenting.value = false; tool.value = 'browse'
  send({ type: 'PA_RENDER_MARKERS', annotations: visiblePins() })
  if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {})
}
// 用户按 Esc 时浏览器先退全屏、按键传不到页面：跟着退出演示。只认「真进过全屏又退出」，进不去全屏不算
let wentFullscreen = false
if (typeof document !== 'undefined') document.addEventListener('fullscreenchange', () => {
  if (document.fullscreenElement) wentFullscreen = true
  else if (wentFullscreen) { wentFullscreen = false; stopPresent() }
})
// 评论：写在右侧，存成一条意见（攒几条一起交给 AI），或者直接发给 AI
const commentDraft = ref('')
// 画笔：评论模式里在页面上拖动就是画。笔迹圈到的元素（源码位置）报上来；发送时再拍一张带红圈的截图
const drawing = ref(null), drawNote = ref(''), drawBusy = ref(false), drawInput = ref(null)
let shotSeq = 0
const shotWaiters = new Map()
function requestShot() {
  return new Promise(resolve => {
    const id = ++shotSeq
    const timer = setTimeout(() => { shotWaiters.delete(id); resolve(null) }, 6000)
    shotWaiters.set(id, data => { clearTimeout(timer); resolve(data?.ok ? data : null) })
    send({ type: 'PA_DRAW_SHOT', id })
  })
}
function drawClear() { send({ type: 'PA_DRAW_CLEAR' }); drawing.value = null; drawNote.value = ''; if (selected.value?.drawing) clearSelectionOnly() }
async function drawSend() {
  const note = drawNote.value.trim()
  if (!note || !drawing.value || drawBusy.value || locked.value) { drawInput.value?.focus(); return }
  drawBusy.value = true
  try {
    // 模型能看图才带截图；看不了图就只给笔迹圈到的元素位置，照样能改
    if (model.value.supports_vision) {
      const shot = await requestShot()
      if (shot) reference.value = { data_url: shot.data_url, name: '页面上画的标记', regions: [] }
    }
    const selection = selected.value
    drawClear()
    await runAgent(note, '', { selection })
  } finally { drawBusy.value = false }
}
async function drawSave() {
  const note = drawNote.value.trim()
  if (!note || !drawing.value || !selected.value || drawBusy.value || locked.value) { drawInput.value?.focus(); return }
  drawBusy.value = true
  try {
    const shot = await requestShot()
    await post(endpoint('/annotations'), { ...selected.value, ...modalContext(selected.value), note, shot: shot?.thumb || '' })
    drawClear(); await refresh(false)
    toast(`已记下第 ${annotations.value.length} 条，可以接着画下一处`)
  } catch (e) { error.value = e.message } finally { drawBusy.value = false }
}
const shotUrl = a => `/api/projects/${project.value?.id}/shots/${a.id}`// 评论气泡只在评论模式里钉在页面上；浏览、编辑、演示时收起来，不挡视线（和 Claude Design 一样）
const visiblePins = () => (tool.value === 'comment' && !presenting.value ? annotations.value : [])
watch(tool, value => {
  if (value !== 'comment' && drawing.value) drawClear()
  send({ type: 'PA_RENDER_MARKERS', annotations: visiblePins() }); send({ type: 'PA_SET_DRAG', enabled: value === 'comment' }) })
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
// 右侧「放大编辑」：回到展开视图，把选中元素所在的那张卡放大
function focusSelected() {
  const card = selected.value?.card
  if (card == null) return
  showBoard()
  if (card.route != null) boardRoute.value = card.route   // 卡片编号只在它那一页里唯一，先回到那一页
  boardFocus.value = card.nodeId
}
function quickFill(kind) {
  const text = (selected.value?.text || '').replace(/\s+/g, ' ').slice(0, 60)
  input.value = kind === 'short' ? `把选中的说明缩短，意思不变：「${text}」` : `把选中的「${text}」改为：`
  toAI()
}
// 后台副本的源码：和预览同一份、同样的演示数据，只是路由换成要展开的那一页；它点出来的改动不会写回来
function makeProbeDoc(route, html = previewDoc.value) {
  let stored = {}
  try { stored = JSON.parse(localStorage.getItem(runtimeKey()) || '{}') } catch {}
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
  await inspect(data)
}
// 预览重新载入：带上最新的路由、滚动位置和演示数据。结尾的编号保证 srcdoc 一定变化、一定重载。
function reseedPreview() {
  if (previewDoc.value) previewDoc.value = preparePreview(previewDoc.value).replace(/\n<!-- pa-open \d+ -->$/, '') + `\n<!-- pa-open ${++reloadNonce} -->`
}
function openFromBoard(node) {
  // 页面本身：预览切到那一页就行
  if (node.isPage) { gotoRoute(node.route ?? boardRoute.value); boardOpen.value = false; boardFocus.value = null; return }
  // 先把预览重新载入到干净的页面状态，再按记下的路径一步步点开
  pendingReplay.value = node; openedModal.value = null
  previewRoute.value = node.route ?? boardRoute.value   // 在展开视图里切到了别的页，预览也跟过去
  boardOpen.value = false; boardFocus.value = null
  setMode('select')
  reseedPreview()   // 只有「在预览中打开某个弹窗」才需要重载：回到干净状态再按路径点开
}
// 展开视图打开时，预览 iframe 整个卸掉，收起时重新挂上、重新载入。
// 以前用 display:none 藏着：Safari 里藏过的 iframe 再显示出来是一片空白，换了 srcdoc 也不重绘。
function clearSelectionOnly() { selected.value = null; inspection.value = null; note.value = ''; textValue.value = ''; send({ type: 'PA_SELECT', selector: '' }) }
function closeSelection() { clearSelectionOnly(); if (!keepInspector.value) rightOpen.value = false }
function hideGuide() { showGuide.value = false; localStorage.setItem('pf-hide-guide', 'true') }
// 选中的东西在弹窗里时，告诉 AI 是哪个弹窗、怎么点开的——不然它只能满文件搜按钮文字
function modalContext(target) {
  if (!target) return {}
  const ctx = {}
  const title = target.modal || target.targets?.find(t => t.modal)?.modal || ''
  const trail = target.trail || (openedModal.value?.title === title ? openedModal.value.trail : '')
  if (title) Object.assign(ctx, { in_modal: title, modal_trail: trail })
  if (target.viewKind === 'subpage') Object.assign(ctx, { in_subpage: target.viewTitle, modal_trail: trail })
  if (target.card?.route != null) ctx.view_route = target.card.route
  return ctx
}
// 选中的东西只能交给 AI 改（弹窗里的、脚本生成的、多选的），右侧换成「位置 + 内容 + 写需求」
const aiOnly = computed(() => !!selected.value && !!inspection.value && !inspection.value.editable && !dynEdit.value)
const selectionPlace = computed(() => {
  const t = selected.value
  if (!t) return ''
  if (t.place) return t.place
  return t.modal ? `${page.value?.title || ''} › ${t.modal}` : ''
})
function elementLabel(target) { const kinds = { button: '按钮', input: '输入框', textarea: '输入框', h1: '标题', h2: '标题', p: '文字', a: '链接' }; return target?.kind === 'region' ? `已选中 ${target.targets.length} 个元素` : `${target?.text?.slice(0, 22) || '选中'} · ${kinds[target?.tag] || '区域'}` }
function preparePreview(html) {
  let stored = {}
  try { stored = JSON.parse(localStorage.getItem(runtimeKey()) || '{}') } catch {}
  return preparePreviewDocument(html, { stored, route: previewRoute.value, scroll: previewScroll.value })
}
async function refresh(reload = true) {
  if (!project.value || !pageId.value) return
  const serial = ++loadSequence, pid = project.value.id, id = pageId.value
  const [meta, info] = await Promise.all([api(`/api/projects/${pid}`), api(`/api/projects/${pid}/pages/${id}/source`)])
  if (serial !== loadSequence) return
  project.value = meta; sourceInfo.value = info
  send({ type: 'PA_RENDER_MARKERS', annotations: visiblePins() })
  if (reload || previewHash.value !== info.hash) {
    const response = await fetch(`/preview/${pid}/${id}`)
    if (!response.ok) throw new Error('预览加载失败，请重试')
    const html = await response.text()
    if (serial !== loadSequence) return
    runtimeErrors.value = []; recentClicks.value = []; previewDoc.value = preparePreview(html); previewHash.value = info.hash; previewOwner.value = `${pid}:${id}`
  }
  await nextTick(); if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
}
// 没发出去的输入和参考截图跟着「项目:原型文件」走：切走时收好，切回来还在；不会被带到别的项目里发出去
const drafts = new Map()
const draftKey = () => project.value && pageId.value ? `${project.value.id}:${pageId.value}` : ''
function stashDraft() { const k = draftKey(); if (!k) return; if (input.value.trim() || reference.value) drafts.set(k, { input: input.value, reference: reference.value }); else drafts.delete(k) }
function restoreDraft() { const d = drafts.get(draftKey()); input.value = d?.input || ''; reference.value = d?.reference || null }
async function chooseProject(id) {
  if (locked.value || !id) return
  stashDraft()
  loading.value = true; error.value = ''; closeSelection(); previewRoute.value = ''; boardRoute.value = ''; boardFocus.value = null; pendingReplay.value = null; openedModal.value = null; previewScroll.value = null; runs.value = []
  try {
    project.value = await api(`/api/projects/${id}`); pageId.value = project.value.pages[0]?.id || ''; restoreDraft()
    if (!pageId.value) { previewDoc.value = ''; sourceInfo.value = { source: '', hash: '', tokens: {}, defaults: {}, regions: [] }; runtimeErrors.value = [] }
    localStorage.setItem('pf-project', id); lastResult.value = null; status.value = '已就绪'
    await refresh()
  } catch (e) { error.value = e.message } finally { loading.value = false }
}
async function choosePage(id) {
  if (locked.value || id === pageId.value) return
  stashDraft()
  pageId.value = id; restoreDraft(); previewRoute.value = ''; boardRoute.value = ''; boardFocus.value = null; pendingReplay.value = null; openedModal.value = null; previewScroll.value = null; runs.value = []; closeSelection(); loading.value = true
  try { await refresh(); status.value = '已就绪' } catch (e) { error.value = e.message } finally { loading.value = false }
}
async function loadProjects(preferred = '') {
  projects.value = await api('/api/projects')
  if (!projects.value.length) {
    ++loadSequence; closeSelection(); project.value = null; pageId.value = ''; previewDoc.value = ''; runtimeErrors.value = []
    sourceInfo.value = { source: '', hash: '', tokens: {}, defaults: {}, regions: [] }; lastResult.value = null
    localStorage.removeItem('pf-project'); status.value = '工作区为空 · 可新建、导入或从回收站恢复'; return
  }
  const id = preferred || localStorage.getItem('pf-project')
  await chooseProject(projects.value.some(p => p.id === id) ? id : projects.value[0]?.id)
}
async function filesChanged() {
  try {
    projects.value = await api('/api/projects')
    if (!project.value || !projects.value.some(p => p.id === project.value.id)) { await loadProjects(); return }
    project.value = await api(`/api/projects/${project.value.id}`)
    if (!project.value.pages.some(p => p.id === pageId.value)) await chooseProject(project.value.id)
  } catch (e) { error.value = e.message }
}
async function openManagedProject(id) { closeDialog(); await chooseProject(id) }
async function upload(event) {
  const file = event.target.files?.[0]; if (!file || locked.value) return
  loading.value = true; error.value = ''
  try {
    const data = new FormData(); data.append('file', file); data.append('name', file.name.replace(/\.(html?|zip)$/i, ''))
    const result = await api('/api/projects/upload', { method: 'POST', body: data })
    loading.value = false; await loadProjects(result.id); toast('原型已导入，可以直接点选修改')
  } catch (e) { error.value = e.message } finally { loading.value = false; event.target.value = '' }
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
    send({ type: 'PA_SET_MODE', mode: mode.value })
    send({ type: 'PA_SET_DRAG', enabled: tool.value === 'comment' })
    send({ type: 'PA_RENDER_MARKERS', annotations: visiblePins() })
    if (selected.value && selected.value.kind !== 'region' && !selected.value.card) send({ type: 'PA_SELECT', selector: selected.value.selector })
  }
  if (data.type === 'SELECTED' && !loading.value) await inspect(data)
  if (data.type === 'DRAWING' && !loading.value) {
    if (!data.count) { drawing.value = null; if (selected.value?.drawing) clearSelectionOnly(); return }
    drawing.value = { count: data.count, redo: data.redo || 0 }
    selected.value = data; inspection.value = { editable: false, kind: 'region' }; rightOpen.value = true
    nextTick(() => drawInput.value?.focus())
  }
  if (data.type === 'DRAW_SHOT' && shotWaiters.has(data.id)) { shotWaiters.get(data.id)(data); shotWaiters.delete(data.id) }
  if (data.type === 'REGION_SELECTED' && !loading.value) { selected.value = data; inspection.value = { editable: false, kind: 'region' }; textValue.value = data.text; rightOpen.value = true; if (window.innerWidth <= 960) leftOpen.value = false }
  if (data.type === 'NOTICE') toast(data.message)
  if (data.type === 'SELECTION_MISSING') closeSelection()
  if (data.type === 'SELECTION_CLEARED') clearSelectionOnly()   // 按住 Shift 把最后一个也取消掉了
  if (data.type === 'SCROLL_STATE') previewScroll.value = data.state
  if (data.type === 'WIDTH') canvasWidth.value = data.width
  // 预览里按的快捷键转过来；⌘↵（发给 AI）不收——原型里的脚本也能伪造这条消息，不能让它替你发需求
  if (data.type === 'SHORTCUT' && !(data.key === 'Enter' || data.key === 'enter')) keydown(data)
  if (data.type === 'LOADED' && pendingReplay.value) { const node = pendingReplay.value; pendingReplay.value = null; setTimeout(() => send({ type: 'PA_REPLAY', path: node.path }), 450); openedModal.value = { title: node.title, trail: node.trail, pending: true } }
  if (data.type === 'REPLAYED') {
    if (data.ok) { openedModal.value = { title: data.title || openedModal.value?.title, trail: openedModal.value?.trail || '' }; toast(`已打开「${openedModal.value.title}」，直接点选要改的地方`) }
    else { openedModal.value = null; toast('没能自动打开这个弹窗，可以在预览里切到交互模式手动点开') }
  }
  if (data.type === 'LOADED' && pendingHighlights.value.length) { send({ type: 'PA_HIGHLIGHT', targets: pendingHighlights.value }); pendingHighlights.value = [] }
  if (data.type === 'ROUTE') { previewRoute.value = data.hash; if (boardOpen.value && !boardRoute.value) boardRoute.value = data.hash }
  if (data.type === 'STORAGE') { try { localStorage.setItem(runtimeKey(), JSON.stringify(data.data)) } catch {} }
  if (data.type === 'RUNTIME_ERROR' && !runtimeErrors.value.includes(data.message)) runtimeErrors.value.push(data.message)
  // 预览里真点过的几下（点了什么、有没有反应、报没报错）：发需求时一起交给 AI，「点了没反应」它就知道是哪个
  if (data.type === 'CLICK_TRACE') recentClicks.value = [...recentClicks.value, { label: data.label, selector: data.selector, tag: data.tag, hashBefore: data.hashBefore, hashAfter: data.hashAfter, changed: !!data.changed, opened: !!data.opened, errors: data.errors || [], at: Date.now() }].slice(-6)
  if (data.type === 'NAVIGATE') {
    try { const resolved = await api(`/api/projects/${project.value.id}/resolve?href=${encodeURIComponent(data.href)}&page_id=${pageId.value}`); if (resolved.page_id) await choosePage(resolved.page_id); else toast('导入的项目中没有这个页面') } catch (e) { error.value = e.message }
  }
}

async function checkAndCommit(candidate) {
  if (!candidate.changed || !candidate.pending_id) return {}
  status.value = '检查中'
  const response = await fetch(candidate.preview_url)
  if (!response.ok) throw responseError({ code: 'validation', message: '无法读取待确认的修改，请重试' })
  const previousDoc = previewDoc.value, baseline = [...runtimeErrors.value]
  const html = preparePreview(await response.text())
  pendingHighlights.value = candidate.targets || []
  previewDoc.value = html
  // 运行检查要一两秒：这段时间展开副本已经用候选版本去拍正在看的那页了
  { const html = previewDoc.value; presync(candidate.pending_id, boardOpen.value ? boardRoute.value : previewRoute.value, route => makeProbeDoc(route, html)) }
  try {
    const errors = await new Promise((resolve, reject) => {
      const frame = document.createElement('iframe')
      frame.title = '后台检查'; frame.setAttribute('sandbox', PREVIEW_SANDBOX); frame.setAttribute('aria-hidden', 'true'); frame.tabIndex = -1
      // 和展开的副本一样放在屏幕内、透明、点不到：放到屏幕外会被浏览器限速，慢一点的页面检查超时，好好的修改被拒
      Object.assign(frame.style, { position: 'fixed', left: '0', top: '0', width: (canvasWidth.value || 1200) + 'px', height: '800px', border: '0', opacity: '0', pointerEvents: 'none', zIndex: '-1' })
      const found = []; let finishTimer, ready = false
      const cleanup = () => { clearTimeout(timeout); clearTimeout(finishTimer); window.removeEventListener('message', listener); frame.remove() }
      const listener = event => {
        if (event.source !== frame.contentWindow || event.data?.source !== 'prototype-agent') return
        const message = event.data
        if (message.type === 'RUNTIME_ERROR' && !baseline.includes(message.message) && !found.includes(message.message)) found.push(message.message)
        if (message.type === 'READY') ready = true
        if (message.type === 'LOADED' && ready) finishTimer = setTimeout(() => { cleanup(); resolve(found) }, 700)
      }
      const timeout = setTimeout(() => { cleanup(); reject(responseError({ code: 'validation', message: '检查超时，已保留上一版，请重试' })) }, 15000)
      window.addEventListener('message', listener); frame.srcdoc = html; document.body.appendChild(frame)
    })
    const committed = await post('/api/candidates/' + candidate.pending_id + '/commit', { runtime_checked: true, errors })
    adoptPresync(candidate.pending_id, committed.hash)   // 必须在 previewHash 变之前：别让刚拍好的那页又排队同步一遍
    previewHash.value = committed.hash
    savedAt.value = new Date().toLocaleTimeString('zh-CN')
    validationDetails.value = candidate.validation?.syntax_checked ? '页面结构、脚本语法及页面启动检查通过；不代表所有交互均已验证' : '页面结构及页面启动检查通过；本机没有执行脚本语法检查'
    status.value = '已保存 · 刚刚'
    return committed
  } catch (e) {
    pendingHighlights.value = []; previewDoc.value = previousDoc; runtimeErrors.value = baseline
    dropPresync(candidate.pending_id)
    throw e
  }
}


async function edit(prop, value, more = null) {
  if (locked.value || (!prop.startsWith('--') && (!canEdit.value || playing.value))) return
  const selector = selected.value?.selector || ''
  const dyn = dynEdit.value && !prop.startsWith('--')
  saving.value = true; error.value = ''; status.value = '修改中'
  // 同类元素一起改：预览里先把同类的都改上
  const extra = prop === 'text' || prop.startsWith('--') ? {} : Object.fromEntries(Object.entries(more || {}).map(([k, v]) => [k, String(v)]))
  for (const [p, v] of [[prop, String(value)], ...Object.entries(extra)])
    send(dyn && p !== 'text' ? { type: 'PA_PREVIEW', selector: selected.value.styleSel, all: true, prop: p, value: v } : { type: 'PA_PREVIEW', selector, prop: p, value: v })
  const card = selected.value?.card
  let committed = false
  if (card || prop.startsWith('--')) cardPatch.value = { seq: ++patchSeq, prop, value: String(value), route: prop.startsWith('--') ? null : card.route, nodeId: prop.startsWith('--') ? null : card.nodeId, rels: card?.rels || [] }
  try {
    const result = await post(endpoint('/edit'), { selector, prop, value: String(value), expected_hash: sourceInfo.value.hash, more: extra,
      ...(dyn ? (prop === 'text' ? { literal: selected.value.text } : { style_selector: selected.value.styleSel }) : {}) })
    if (dyn && prop === 'text' && result.changed) selected.value = { ...selected.value, text: String(value) }
    await checkAndCommit(result); committed = !!result.changed
    if (committed && selected.value?.selector === selector && !prop.startsWith('--')) selected.value = { ...selected.value, styles: { ...(selected.value.styles || {}), [prop]: String(value), ...extra } }
    if (!result.changed) status.value = '没有新的改动'
    await refresh(false)
  } catch (e) {
    if (committed) status.value = '已保存 · 预览刷新失败'
    else {
      error.value = e.message; status.value = '修改未保存 · 已保留原页面'
      // 展开卡片上先改了样子，保存没成：卡片退回原样，别让它显示一个没存进去的值
      if (cardPatch.value) cardPatch.value = { ...cardPatch.value, seq: ++patchSeq, revert: true }
    }
    await refresh().catch(() => {})
  }
  finally {
    saving.value = false
    reselect()
  }
}
// 改完以后在预览里重新选中同一个元素，好让属性面板读到新值。
// 多选、拉框、在展开卡片里选的不能这样做：预览只会退回成一个元素，甚至因为找不到而把选择清掉
function reselect() { const s = selected.value; if (s && s.kind !== 'region' && !s.card && !(s.targets?.length > 1)) send({ type: 'PA_SELECT', selector: s.selector }) }
// 属性面板的图层列表：点一下换成选那一层，移上去在页面上框出来
function selectLayer(selector) { if (selector) send({ type: 'PA_SELECT', selector }) }
function hoverLayer(selector) { send({ type: 'PA_HOVER', selector: selector || '' }) }
async function undo(changeId = '') {
  if (locked.value || !undoCount.value) return
  saving.value = true; error.value = ''
  try {
    await checkAndCommit(await post(endpoint('/undo'), { change_id: typeof changeId === 'string' ? changeId : '' }))
    await refresh(false); toast('已撤销上一步')
  } catch (e) { error.value = e.message; status.value = '撤销失败 · 页面没变' }
  finally { saving.value = false; reselect() }
}


async function saveNote(text) {
  const fromPanel = typeof text === 'string'
  const content = (fromPanel ? text : input.value).trim()
  if (!selected.value || !content || locked.value) return
  const wasRegion = selected.value.kind === 'region'
  saving.value = true
  try {
    await post(endpoint('/annotations'), { ...selected.value, ...modalContext(selected.value), note: content })
    if (fromPanel) commentDraft.value = ''
    else if (input.value.trim() === content) input.value = ''
    // 记下之后立刻把这次的选中清掉：保留着它，下一次框选会顶掉它而不是新起一条，
    // 右侧还一直显示上一处，看不出这条到底记住了没有。清干净，留在当前模式，
    // 就可以直接接着框下一处 / 点下一个。
    clearSelectionOnly()
    await refresh(false)
    toast(`已记下第 ${annotations.value.length} 条，${wasRegion ? '可以接着框选下一处' : '可以接着点选下一个位置'}`)
  } catch (e) { error.value = e.message } finally { saving.value = false }
}


async function removeAnnotation(id) {
  try { await api(`/api/projects/${project.value.id}/annotations/${id}`, { method: 'DELETE' }); await refresh(false) } catch (e) { error.value = e.message }
}
// 对话和属性 / 评论共用左侧一栏（和 Claude Design 一样），用顶上的页签切换
function openLeft() { leftOpen.value = true; rightOpen.value = false }
function showChat() { leftOpen.value = true; rightOpen.value = false }
function showPanel() { rightOpen.value = true }
function toggleRight() { rightOpen.value = !rightOpen.value; if (rightOpen.value && window.innerWidth <= 960) leftOpen.value = false }
async function commentToAI() {
  const text = commentDraft.value.trim()
  if (!text || !selected.value) return
  input.value = text; commentDraft.value = ''
  await runAgent()
}
async function toAI() { leftOpen.value = true; rightOpen.value = false; await nextTick(); composer.value?.focus() }
// 预览现场：停在哪一页、最近 5 分钟里点过什么、页面报过什么错
function previewScene() {
  const since = Date.now() - 5 * 60_000
  return { route: previewRoute.value || '', clicks: recentClicks.value.filter(c => c.at >= since).map(({ at, ...c }) => c), errors: runtimeErrors.value.slice(-5) }
}
async function runAgent(text = '', runtimeFeedback = '', options = {}) {
  const message = (typeof text === 'string' && text ? text : input.value).trim() || (annotations.value.length ? '请逐条处理已记下的修改意见，保留其他区域。' : '')
  if (locked.value || !message || !pageId.value) return
  if (!model.value.has_key || (reference.value && !model.value.supports_vision)) { openDialog('settings'); dialogError.value = reference.value ? '这张截图需要支持图片输入和工具调用的模型。' : '请先配置模型密钥。'; return }
  const activeSelection = options.selection === undefined ? selected.value : options.selection
  const target = activeSelection ? { selector: activeSelection.selector, text: activeSelection.text, tag: activeSelection.tag, outer_html: activeSelection.outer_html, targets: activeSelection.targets || [], ...modalContext(activeSelection) } : null
  const intent = options.intent || composerIntent.value
  const run = { intent, options: { ...options, intent }, id: Date.now(), projectId: project.value.id, pageId: pageId.value, request: message, started: Date.now(), status: 'running', label: '理解需求中', steps: [], error: null, streamText: '', plan: [] }
  runs.value.push(run)
  const current = runs.value[runs.value.length - 1]
  busy.value = true; error.value = ''; pendingUser.value = message
  // 截图跟着这一条发出去就算用过了：从输入框上方拿掉，挂到这条消息上；停止或失败再放回来
  const sentRef = reference.value
  // 自检发现问题：这次结束后自动再修一轮；修完再查，如果修出了新的报错，再修第二轮，之后不再自动修
  let followUp = '', followRound = 0
  const selfRound = options.selfReview || 0
  pendingRef.value = sentRef
  if (!text || input.value.trim() === message) input.value = ''
  reference.value = null
  lastResult.value = null; status.value = intent === 'edit' ? '正在读页面' : '思考中'; leftOpen.value = true
  try {
    const response = await fetch('/api/projects/' + project.value.id + '/agent/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ page_id: pageId.value, message, selection: target, runtime_feedback: runtimeFeedback, reference: sentRef, scene: previewScene(), intent, include_annotations: options.includeAnnotations !== false }) })
    const result = await consumeAgentStream(response, event => {
      if (event.type === 'started' && event.run_id) current.runId = event.run_id
      // 模型服务忙：后台自动等几秒重试，这里只记一笔，让人知道不是卡住了
      if (event.type === 'model_retry') current.steps.push({ id: `retry-${event.round}-${event.attempt}`, label: event.label, state: 'done' })
      if (event.type === 'intent') { current.intent = event.intent; current.options.intent = event.intent; status.value = event.intent === 'discuss' ? '讨论中 · 不会修改文件' : '正在读页面' }
      if (event.type === 'plan') { current.plan = event.steps; if (event.brief) current.brief = event.brief }
      if (event.type === 'model_wait') { current.streamText = ''; current.round = event.round }
      if (event.type === 'text_delta') current.streamText += event.text
      if (event.type === 'note_delta') {
        // 模型的旁白按轮次接在步骤列表里，和它接下来做的事排在一起。
        // 以前所有文字共用一个 streamText，每换一轮就被擦掉，
        // 于是你只看得到工具名，看不到它为什么要查这个。
        const tail = current.steps[current.steps.length - 1]
        if (tail?.kind === 'note' && tail.round === current.round) tail.label += event.text
        else current.steps.push({ id: 'note-' + current.steps.length, kind: 'note', round: current.round, label: event.text })
      }
      if (event.label) current.label = event.label
      if (event.type.startsWith('step_')) {
        let step = current.steps.find(item => item.id === event.id)
        if (!step) { current.steps.push({ id: event.id, label: event.label }); step = current.steps[current.steps.length - 1] }
        step.state = event.type === 'step_start' ? 'running' : event.type === 'step_done' ? 'done' : 'error'
        step.error = event.error?.message || event.error?.error || ''
        if (event.detail) step.detail = event.detail
        // 记下真的动过文件的那一刻，卡片标题在那之前不该说"修改中"。
        if (event.tool === 'apply_operations' && event.type === 'step_done') { current.editing = true; status.value = '修改中' }
      }
    })
    current.result = result
    if (result.changed) { current.status = 'checking'; Object.assign(result, await checkAndCommit(result)); current.committed = true }
    // 做完自检：改动不小（新做一页、一大块）时，像验收那样把每页按钮点一遍，有问题自动交回去修一轮
    if (result.changed && current.intent !== 'discuss' && (options.selfReview || (result.diff?.additions || 0) >= 30 || (result.change_count || 0) >= 6)) {
      status.value = '自检中 · 把每页的按钮点一遍'
      current.steps.push({ id: 'selftest', label: '做完自检：把每页的按钮点一遍', state: 'running' })
      const step = current.steps[current.steps.length - 1], html = previewDoc.value
      const report = await selfTest({ makeDoc: route => makeProbeDoc(route, html), width: canvasWidth.value || 1200 })
      const again = report.issues.length && (selfRound === 0 || (selfRound === 1 && report.issues.some(i => i.kind === '报错')))
      result.selftest = { ...report, round: selfRound + 1, final: !again }
      if (result.change_id) selftests.value = { ...selftests.value, [result.change_id]: result.selftest }
      step.state = 'done'
      step.label = report.skipped ? '自检没跑完：' + report.skipped
        : report.issues.length ? `自检发现 ${report.issues.length} 个问题${again ? '，接着自动修一轮' : ''}`
        : `自检通过：${report.routes} 个页面、${report.clicked} 个按钮都点过`
      if (again) { followUp = selfTestRequest(report.issues); followRound = selfRound + 1 }
      status.value = again ? '自检发现问题 · 马上自动修一轮' : report.issues.length ? `已保存 · 自检还剩 ${report.issues.length} 个问题` : '已保存 · 自检通过'
    }
    else status.value = result.clarification ? '等待你确认' : result.discussion ? '讨论完成 · 未修改文件' : '没有改动页面'
    lastResult.value = result
    await refresh(false); projects.value = await api('/api/projects')
    current.status = 'complete'
    refreshMemoryCount(); setTimeout(refreshMemoryCount, 20_000)   // 后台整理记忆要一会儿，过一阵再看一次
  } catch (e) {
    if (e.code === 'stopped') {   // 自己点的停止、而且还没改动：不是失败，原需求放回输入框
      current.status = 'stopped'; current.error = { code: 'stopped', message: '已停止，当前文件没有改动' }
      current.steps.filter(s => s.state === 'running').forEach(s => { s.state = 'done' })
      if (!input.value.trim()) input.value = message
      if (!reference.value && sentRef) reference.value = sentRef
      status.value = '已停止 · 页面没有改动'; return
    }
    if (current.committed) {   // 已经存进去了，只是刷新预览没成功：不能报「未保存」，否则重试会再改一遍
      current.status = 'complete'; lastResult.value = current.result
      status.value = '已保存 · 预览刷新失败'; toast('修改已保存，但预览刷新失败，可以刷新页面')
      await refresh(false).catch(() => {}); return
    }
    current.status = 'failed'
    current.steps.filter(s => s.state === 'running').forEach(s => { s.state = 'error'; s.error = '本次处理已停止' })
    current.error = { code: e.code || 'network', message: e.message, detail: e.detail || e.message }
    if (!input.value.trim()) input.value = message
    if (!reference.value && sentRef) reference.value = sentRef
    status.value = current.intent === 'discuss' ? '本次回复未完成 · 可以重试' : '本次修改未保存'
    await refresh(false).catch(() => {})
  } finally {
    current.finished = Date.now(); busy.value = false; pendingUser.value = ''; pendingRef.value = null
    await nextTick(); if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
    if (followUp) setTimeout(() => runAgent(followUp, '', { intent: 'edit', includeAnnotations: false, selection: null, selfReview: followRound }), 0)
  }
}
// 停止：告诉后台在下一步之前停下。已经改好的部分照常检查、保存，可以一键撤销；还没改就什么都不动
const activeRun = computed(() => [...runs.value].reverse().find(r => r.status === 'running') || null)
async function stopAgent() {
  const run = activeRun.value
  if (!run?.runId || run.stopping || !project.value) return
  run.stopping = true; run.label = '正在停止…已经改好的部分会保留并检查'
  try { await post(`/api/projects/${project.value.id}/agent/stop`, { run_id: run.runId }) } catch { run.stopping = false }
}
async function chooseAnswer({ option, clarification }) {
  await runAgent('原需求：' + clarification.request + '\n你的问题：' + clarification.question + '\n我的选择：' + option, '', { intent: clarification.intent || 'discuss' })
}
// 讨论卡片上勾了几条就一起改：一条照原样发，几条编号列出来，模型逐条做完再汇报
async function applySuggestion({ suggestion, suggestions, discussion }) {
  const list = suggestions?.length ? suggestions : [suggestion]
  const message = list.length === 1 ? '按已讨论的建议修改：' + list[0].instruction
    : `按已讨论的建议修改，这 ${list.length} 条都要做：\n` + list.map((s, i) => `${i + 1}. ${s.label}：${s.instruction}`).join('\n')
  await runAgent(message, '', { intent: 'edit', includeAnnotations: false, selection: discussion?.selection || null })
}
// 建议清单底下的「其他」：跟着这次讨论的选区，按输入框当前的模式发出去
async function customSuggestion({ text, discussion }) {
  await runAgent(text, '', { includeAnnotations: false, selection: discussion?.selection || null })
}
async function discussSuggestion(suggestion) {
  composerIntent.value = 'discuss'; input.value = '关于“' + suggestion.label + '”：'; await toAI()
}
async function saveSpec() {
  dialogBusy.value = true; dialogError.value = ''
  try {
    const result = await api('/api/design-spec', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: specDraft.value }) })
    specSaved.value = specDraft.value
    specNotice.value = `已保存 ${result.chars} 字，下一次修改起生效`
  } catch (e) { dialogError.value = e.message } finally { dialogBusy.value = false }
}
async function addComponent(event) {
  const file = event.target.files?.[0]; event.target.value = ''
  if (!file) return
  dialogBusy.value = true; dialogError.value = ''; specNotice.value = ''
  try {
    const data = new FormData(); data.append('file', file); data.append('name', file.name)
    const result = await api('/api/components', { method: 'POST', body: data })
    const shelf = await api('/api/components')
    componentList.value = shelf.components; skillList.value = shelf.skills || []
    if (result.kind === 'skill') {
      specNotice.value = `已装上 skill「${result.name}」，附带 ${result.files.length} 个文件，结构原样保留`
        + (result.skipped_count ? `，跳过 ${result.skipped_count} 个非文本文件` : '')
      return
    }
    const skipped = result.skipped_count ? `，跳过 ${result.skipped_count} 个非 html/md 文件` : ''
    const hasSpec = result.imported.some(n => n.endsWith('.md'))
    specNotice.value = (result.imported.length > 1
      ? `已加入 ${result.imported.length} 个组件${skipped}，下次修改时 AI 就能直接取用`
      : `已加入「${result.imported[0]}」${skipped}，下次修改时 AI 就能直接取用`)
      + (hasSpec ? '。包里带了说明文档——如果它写了配色和尺寸，记得把「规范正文」也换成你们的，否则两套规范会打架。' : '')
  } catch (e) { dialogError.value = e.message } finally { dialogBusy.value = false }
}
watch(() => project.value?.id, id => { memoryCount.value = 0; if (id) refreshMemoryCount() })
async function openMemory() { await openDialog('spec'); specTab.value = 'memory' }
async function refreshMemoryCount() { const id = project.value?.id; if (!id) return; try { const m = await api(`/api/projects/${id}/memory`); if (project.value?.id !== id) return; memoryCount.value = (m.project?.memory?.length || 0) + (m.global?.memory?.length || 0) } catch { /* 读不到就不显示数 */ } }
async function forgetFromCard(id) {
  try { await api(`/api/projects/${project.value.id}/memory/${id}`, { method: 'DELETE' }); toast('已忘掉这条约定') } catch (e) { toast(e.message) }
}
async function removeSkill(name) {
  dialogBusy.value = true; dialogError.value = ''
  try {
    await api('/api/skills/' + encodeURIComponent(name), { method: 'DELETE' })
    const shelf = await api('/api/components')
    componentList.value = shelf.components; skillList.value = shelf.skills || []
    specNotice.value = `已卸掉「${name}」`
  } catch (e) { dialogError.value = e.message } finally { dialogBusy.value = false }
}
async function removeComponent(name) {
  dialogBusy.value = true; dialogError.value = ''
  try {
    await api('/api/components/' + encodeURIComponent(name), { method: 'DELETE' })
    componentList.value = (await api('/api/components')).components
    specNotice.value = `已移除「${name}」`
  } catch (e) { dialogError.value = e.message } finally { dialogBusy.value = false }
}
async function importSpecTokens(event) {
  const file = event.target.files?.[0]; event.target.value = ''
  if (!file) return
  dialogBusy.value = true; dialogError.value = ''; specNotice.value = ''
  try {
    const data = new FormData(); data.append('file', file)
    const result = await api('/api/design-spec/extract', { method: 'POST', body: data })
    const rows = Object.entries(result.tokens).map(([name, value]) => `| \`${name}\` | \`${value}\` |`).join('\n')
    specDraft.value = specDraft.value.replace(/\n*## 本项目配色[\s\S]*?(?=\n## |$)/, '').trimEnd()
      + `\n\n## 本项目配色\n\n取自 ${file.name}，请确认后保存。\n\n| 变量 | 值 |\n|---|---|\n${rows}\n`
    specNotice.value = `读到 ${result.count} 个变量，已插到末尾，确认后点保存`
  } catch (e) { dialogError.value = e.message } finally { dialogBusy.value = false }
}
async function useRephrase(hint) { input.value = hint; await toAI() }
async function copyMessage(text) {
  try { await navigator.clipboard.writeText(text); toast('已复制') } catch { toast('复制失败，请手动选中') }
}
async function editAndResend(message) {
  input.value = message.content
  await toAI()
  composer.value?.setSelectionRange(input.value.length, input.value.length)
}
// 「拆小一点」：以前是在原话前面加「先只修改一个位置：」就直接再发一遍，AI 拿到的信息和上次一模一样，照样找不到。
// 现在把原话放回输入框，由你删成一小步再发
async function smallerRequest(run) { input.value = run.request; leftOpen.value = true; await nextTick(); composer.value?.focus(); toast('要求放回输入框了，删成一小步再发，比如先只改一处') }
// 「指给它看」：找不到通常是没指位置。点了没反应这类先切到交互把问题点一遍（AI 能看到你点了什么），别的切到点选点一下
async function pointAt(run) {
  // 已经选中了：原话照发，选中的位置本来就会跟着需求一起交给 AI。以前在前面加「只修改当前选中的位置」，
  // 要整体重做的需求也被限死在一个元素上
  if (selected.value) { input.value = run.request; await toAI(); return }
  input.value = run.request; leftOpen.value = true
  const clicky = /没反应|点击|点了|点不|报错|跳转|打不开|切换|不动/.test(run.request)
  setMode(clicky ? 'interact' : 'select')
  toast(clicky ? '先在预览里把出问题的操作点一遍，再按发送：AI 能看到你点了什么、有没有报错' : '在页面上点一下要改的地方，再按发送')
}


async function openDialog(type) {
  dialogType.value = type; dialogError.value = ''
  if (type === 'settings') configDraft.value = { base_url: model.value.base_url || 'https://api.deepseek.com', model: model.value.model || 'deepseek-flash', api_key: '', supports_vision: !!model.value.supports_vision, max_tokens: model.value.max_tokens || 32000, context_budget: model.value.context_budget || 200000, max_rounds: model.value.max_rounds || 24, stream: model.value.stream !== false, keepInspector: keepInspector.value }
  if (type === 'new') { projectName.value = ''; brief.value = '' }
  if (type === 'files') fileManagerRevision.value++
  if (type === 'spec') {
    specNotice.value = ''; specTab.value = 'spec'
    try {
      specDraft.value = specSaved.value = (await api('/api/design-spec')).content
      const shelf = await api('/api/components')
      componentList.value = shelf.components; skillList.value = shelf.skills || []
      if (project.value) { const m = await api(`/api/projects/${project.value.id}/memory`); memoryCount.value = (m.project?.memory?.length || 0) + (m.global?.memory?.length || 0) }
    } catch (e) { dialogError.value = e.message }
  }
  await nextTick(); dialog.value.showModal()
}
function closeDialog() { if (!dialogBusy.value) { dialog.value.close(); configDraft.value.api_key = '' } }
async function uploadImage(event) {
  const file = event.target.files?.[0]; if (!file) return
  event.target.value = ''
  await attachImage(file)
}
// 截图可以直接粘贴（⌘/Ctrl + V）、拖进输入框，也可以点按钮选文件。
// 附上后在输入框上方显示缩略图；要圈出具体位置再点缩略图。还没打开项目时才弹出对话框（要选新建还是改当前）
const dragging = ref(false)
function imageFrom(list) { return [...(list || [])].map(x => (x.kind === 'file' ? x.getAsFile() : x)).find(f => f && /^image\/(png|jpe?g|webp|gif)$/.test(f.type)) }
async function pasteImage(event) {
  const file = imageFrom(event.clipboardData?.items)
  if (!file) return
  event.preventDefault()
  await attachImage(file)
}
async function dropImage(event) {
  dragging.value = false
  const file = imageFrom(event.dataTransfer?.files)
  if (!file) { if (event.dataTransfer?.files?.length) toast('只能放 PNG、JPG、WebP 图片'); return }
  await attachImage(file)
}
// 焦点不在输入框时截完图直接 ⌘V 也能贴进来
function globalPaste(event) {
  const el = event.target
  if (el instanceof Element && el.closest('input, textarea, [contenteditable=""], [contenteditable="true"], dialog[open]')) return
  if (imageFrom(event.clipboardData?.items)) pasteImage(event)
}
onMounted(() => window.addEventListener('paste', globalPaste))
onUnmounted(() => window.removeEventListener('paste', globalPaste))
async function attachImage(file) {
  if (locked.value) { toast('AI 正在修改，等它完成再加截图'); return }
  if (file.size > 8 * 1024 * 1024) { toast('请用 8 MB 以内的截图'); return }
  const pasted = !file.name || /^image\.(png|jpe?g|webp|gif)$/i.test(file.name)
  const name = pasted ? `粘贴的截图 ${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}` : file.name
  try {
    const dataUrl = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('截图读取失败')); reader.readAsDataURL(file) })
    const img = await new Promise((resolve, reject) => { const image = new window.Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error('无法识别这张图片')); image.src = dataUrl })
    const scale = Math.min(1, 1800 / Math.max(img.width, img.height)), canvas = document.createElement('canvas')
    canvas.width = Math.round(img.width * scale); canvas.height = Math.round(img.height * scale)
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
    reference.value = { name, data_url: canvas.toDataURL('image/png'), width: canvas.width, height: canvas.height, regions: [] }
    if (!project.value) { await openDialog('image'); return }
    leftOpen.value = true
    toast(model.value.supports_vision ? '截图已附上，发送时一起带上；点缩略图可以圈出要改的地方' : '截图已附上，但当前模型看不了图片，发送前要在设置里换成支持图片的模型')
    nextTick(() => composer.value?.focus())
  } catch (e) { toast(e.message) }
}
async function useReference(createNew = false) {
  if (locked.value) { dialogError.value = 'AI 正在修改，等它完成再用截图'; return }
  if (createNew || !project.value) {
    dialogBusy.value = true
    const carried = reference.value
    try { const result = await post('/api/projects/new', { name: carried.name.replace(/\.[^.]+$/, '') }); reference.value = null; await loadProjects(result.id); reference.value = carried } catch (e) { dialogError.value = e.message; return } finally { dialogBusy.value = false }
  }
  if (!input.value.trim()) input.value = reference.value.regions.length ? '参考截图中框选区域的意见，修改对应位置，保留其他区域。' : '参考这张截图，调整当前原型的布局和样式。'
  closeDialog(); await toAI(); toast('截图和框选意见已加入本轮需求')
}
async function saveSettings() {
  dialogBusy.value = true; dialogError.value = ''
  try { model.value = await post('/api/config', configDraft.value); configDraft.value.api_key = ''; keepInspector.value = configDraft.value.keepInspector; localStorage.setItem('pf-inspector-pinned', String(keepInspector.value)); rightOpen.value = keepInspector.value || !!selected.value; localStorage.removeItem('pa_deepseek_key'); toast('模型配置已保存到本机'); dialog.value.close() } catch (e) { dialogError.value = e.message } finally { dialogBusy.value = false }
}
async function testConnection() {
  dialogBusy.value = true; dialogError.value = ''
  try { model.value = await post('/api/config', configDraft.value); configDraft.value.api_key = ''; const result = await post('/api/config/test'); if (!result.ok) throw new Error('模型没有返回有效回复'); toast('模型连接成功') } catch (e) { dialogError.value = e.message } finally { dialogBusy.value = false }
}
async function createProject() {
  if (!projectName.value.trim()) return
  dialogBusy.value = true; dialogError.value = ''
  try {
    const result = await post('/api/projects/new', { name: projectName.value })
    await loadProjects(result.id)
    input.value = brief.value; dialog.value.close(); await toAI(); toast('原型骨架已创建')
    if (brief.value.trim() && model.value.has_key) { dialogBusy.value = false; await runAgent('', '', { intent: 'edit' }) }
  } catch (e) { dialogError.value = e.message; } finally { dialogBusy.value = false }
}
async function restore(version) {
  if (locked.value) { dialogError.value = 'AI 正在修改，等它完成再退回'; return }
  dialogBusy.value = true; error.value = ''; dialogError.value = ''
  try { const result = await post(endpoint(`/restore/${version}`)); await checkAndCommit(result); closeSelection(); await refresh(false); dialog.value.close(); toast(`已退回到 v${version}`) } catch (e) { dialogError.value = e.message; status.value = '退回失败 · 页面没变' } finally { dialogBusy.value = false }
}
async function copySource() { try { await navigator.clipboard.writeText(codeText.value); codeCopied.value = true; setTimeout(() => codeCopied.value = false, 1800) } catch { toast('请选中源码后复制') } }
// 导出展开图：已展开的业务页面一页一棵树，存成一个独立 HTML，发给别人双击就能看、也能打印成 PDF
// 导出前先看完不完整：有页面没展开、或者改过以后还没同步，先问要不要展开完再导出（展开完会自动导出）
const pendingExport = ref(false)
function requestExport() {
  if (!project.value || !page.value) return
  const routes = expand.routes
  const missing = routes.filter(r => !expand.entries[r.hash]?.result?.styles).length
  const stale = routes.filter(r => expand.entries[r.hash]?.result?.styles && !isFresh(r.hash)).length
  if (!routes.length || missing || stale) {
    const what = !routes.length ? '还没有找过这个原型有哪些业务页面，现在只能导出已经展开的页面。'
      : [missing && `${missing} 个业务页面还没展开`, stale && `${stale} 个页面不是最新版本`].filter(Boolean).join('，') + '。'
    if (window.confirm(`${what}\n\n确定：先把所有业务页面展开到最新，完成后自动导出（展开期间可以照常使用）\n取消：直接导出现在已有的`)) {
      pendingExport.value = true; expandAll(boardRoute.value || previewRoute.value)
      toast('正在展开全部业务页面，完成后会自动导出'); return
    }
  }
  exportExpand()
}
// 等到全部展开好再导出；有的页面展开失败（原型没响应）就永远等不到「全部好」——
// 所以后台没事可做了也导出，用现有的，并说清哪些没展开成。不能卡着，过很久又突然下载
watch(() => {
  if (!pendingExport.value || expand.discovering || !expand.routes.length) return ''
  if (expand.routes.every(r => isFresh(r.hash))) return 'ready'
  return !Object.keys(expand.jobs).length && !expand.queued.length && !expand.batch ? 'idle' : ''
}, state => {
  if (!state) return
  pendingExport.value = false
  const failed = state === 'idle' ? expand.routes.filter(r => !isFresh(r.hash)).length : 0
  exportExpand()
  if (failed) toast(`有 ${failed} 个页面没展开成功，导出的是其余页面${expand.error ? '（' + expand.error + '）' : ''}`)
})
watch(() => expand.scope, () => { pendingExport.value = false })   // 切到别的项目 / 页面就不再自动导出
function exportExpand() {
  if (!project.value || !page.value) return
  const name = project.value.name || '原型', file = page.value.path || page.value.title || ''
  const { html, pages, views, missing } = buildExpandExport({ projectName: name, fileName: file, version: page.value.version, routes: expand.routes, entries: expand.entries, currentHash: expand.hash, notes: annotations.value })
  if (!pages) { toast('还没有展开好的页面可以导出'); return }
  const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url; a.download = `${name}-展开图-v${page.value.version}.html`.replace(/[\\/:*?"<>|]/g, '_')
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000)
  toast(`已导出 ${pages} 个业务页面、${views} 个视图${missing ? `；还有 ${missing} 个页面没展开，先点「一键展开」可以导出完整的` : ''}`)
}
function download(zip = false) { if (project.value) window.location.assign(zip ? `/api/projects/${project.value.id}/export` : endpoint('/download')) }
// 一个格式器反复用：每次 toLocaleString 都新建一个，聊天长了以后每敲一个字都要重算几百次
const timeFormat = new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
function formatTime(value) { const d = new Date(value); return isNaN(d) ? '' : timeFormat.format(d) }
function keydown(event) {
  if (dialog.value?.open) return
  const key = event.key.toLowerCase(), command = event.metaKey || event.ctrlKey
  const editing = event.target?.closest?.('input,textarea,select,[contenteditable=true]')
  if (command && key === 'enter') { event.preventDefault?.(); runAgent(); return }
  if (editing || event.altKey) return
  if (command && key === 'z' && !event.shiftKey) { event.preventDefault?.(); undo(); return }
  if (command) return
  if (key === 'escape') { if (presenting.value) { stopPresent(); return } if (boardFocus.value != null) { boardFocus.value = null; return } if (boardOpen.value) { showPreview(); return } closeSelection(); setTool('browse') }
  if (presenting.value) return
  if (key === 'e' && page.value) { event.preventDefault?.(); toggleBoard(); return }
  const next = { h: 'browse', c: 'comment', b: 'comment', v: 'edit', p: 'present' }[key]
  if (next && page.value) { event.preventDefault?.(); setTool(next) }
}


watch(view, value => { if (value === 'preview' && previewDoc.value) previewDoc.value = preparePreview(previewDoc.value) })
watch(mode, () => send({ type: 'PA_SET_MODE', mode: mode.value }))
// 后台在跑的是旧代码（改过没重启）：页面是新的、接口是旧的，新功能会报「Method Not Allowed」。挂一条提示说清楚怎么办
const backendStale = ref(false)
async function checkBackend() {
  try { const h = await api('/api/health'); backendStale.value = !h.code_epoch ? true : h.code_epoch > h.started_epoch + 1 } catch { /* 连不上另有提示 */ }
}
onMounted(checkBackend)
onMounted(async () => { window.addEventListener('message', onMessage); window.addEventListener('keydown', keydown); try { model.value = await api('/api/config'); await loadProjects() } catch (e) { error.value = e.message } })
onUnmounted(() => { window.removeEventListener('message', onMessage); window.removeEventListener('keydown', keydown); clearTimeout(toastTimer) })

// 拆出去的界面块（AppHeader / ConversationPanel / InspectorPanel / StudioDialog）用到的状态和函数：按原名交给它们
provide('studio', {
  TOOLS, activeRun, addComponent, aiOnly, annotations, applySuggestion, boardOpen, brief,
  busy, canEdit, canvasWidth, chatBox, chooseAnswer, choosePage, chooseProject,
  closeDialog, closeSelection, colors, commentDraft, commentToAI, componentInput, componentList, composer,
  composerIntent, copyMessage, createProject, currentRuns, device, dialog, dialogBusy, dialogError,
  dialogType, discussSuggestion, download, dragging, drawClear, drawing, dropImage, dynEdit,
  edit, editAndResend, elementLabel, fileInput, fileManagerRevision, filesChanged, forgetFromCard, formatTime,
  hideGuide, imageInput, importSpecTokens, input, inspection, keepInspector, lastResult, leftOpen,
  loading, locked, memoryCount, messages, model, modelMenu, moreMenu,
  openDialog, openLeft, openManagedProject, openMemory, page, pageId, pasteImage, pendingRef,
  pendingUser, playing, pointAt, previewDoc, project, projectName, projects, reference,
  removeAnnotation, removeComponent, removeSkill, restore, rightOpen, runAgent, saveNote, saveSpec, customSuggestion, selftests, selectLayer, hoverLayer, toast,
  saving, selected, selectionPlace, setMode, setTool, shotUrl, showBoard, showChat,
  showGuide, showPanel, showPreview, skillList, smallerRequest, sourceInfo, specDraft, specInput,
  specNotice, specSaved, specTab, stopAgent, switchModel, switchingModel, textEditable, textValue,
  toAI, toggleRight, tool, undo, undoCount, upload, uploadImage, useReference,
  useRephrase, view
})
</script>

<template>
  <div class="studio" :class="{ presenting }">
    <div v-if="presenting" class="present-edge" @mouseenter="peekExit"></div>
    <button v-if="presenting" class="present-exit" :class="{ shown: exitShown }" @click="stopPresent" @mouseenter="peekExit" @mouseleave="hideExitSoon"><X :size="14" />退出演示 <kbd>Esc</kbd></button>
    <AppHeader />

    <main class="workspace" :class="{ 'side-closed': !leftOpen && !rightOpen }">
      <div v-if="(leftOpen || rightOpen)" class="mobile-scrim" @click="leftOpen = false; rightOpen = false"></div>
      <ConversationPanel />

      <section class="canvas-panel" aria-label="原型画布">
        <div v-if="view === 'preview'" class="canvas" :class="device">

          <ExpandBoard v-if="boardMounted" :class="{ 'view-hidden': !boardOpen }" :aria-hidden="!boardOpen" v-model:focus="boardFocus" v-model:route="boardRoute" :notes="annotations" :patch="cardPatch" :page-name="page?.title" :selection="selected" :mode="mode" @open="openFromBoard" @select="pickFromBoard" @clear="closeSelection" @mode="setMode" @export="requestExport" />
          <div class="preview-shell" :class="{ 'is-selecting': mode !== 'interact', 'view-hidden': boardOpen }" :aria-hidden="boardOpen"><iframe v-if="previewDoc" ref="previewFrame" title="原型预览" :srcdoc="previewDoc" :sandbox="PREVIEW_SANDBOX"></iframe><div v-else class="empty-canvas"><div class="empty-emblem"><PanelsTopLeft :size="30" :stroke-width="1.4" /></div><h1>给想法一个可操作的样子</h1><p>从已有的 HTML 开始修改，<br>或描述需求，让 AI 帮你搭建第一版。</p><div><button class="primary" @click="openDialog('new')"><Plus :size="16" />新建原型</button><button class="outline" @click="fileInput.click()"><Upload :size="16" />导入原型</button></div><span>支持 HTML、包含多页面的 ZIP</span></div><div v-if="drawing && tool === 'comment' && !boardOpen" class="draw-bar" @keydown.esc.stop="drawClear"><PenLine :size="15" /><input ref="drawInput" v-model="drawNote" maxlength="1000" :placeholder="`给画的 ${drawing.count} 笔写一句说明，比如：这块改成卡片布局`" aria-label="标记说明" @keydown.enter.exact.prevent="drawSend" @keydown.meta.enter.prevent="drawSend"><button class="icon-button" title="撤销一笔" aria-label="撤销一笔" :disabled="!drawing.count || drawBusy" @click="send({ type: 'PA_DRAW_UNDO' })"><Undo2 :size="15" /></button><button class="icon-button" title="重做" aria-label="重做" :disabled="!drawing.redo || drawBusy" @click="send({ type: 'PA_DRAW_REDO' })"><Redo2 :size="15" /></button><button class="quiet" :disabled="drawBusy" @click="drawClear">取消</button><button class="outline" title="先记下，攒几条一起改" :disabled="drawBusy || locked || !drawNote.trim()" @click="drawSave">记下</button><button class="primary" title="回车发送" :disabled="drawBusy || locked || !drawNote.trim()" @click="drawSend"><LoaderCircle v-if="drawBusy" :size="14" class="spin" /><span v-else>发送</span></button></div><div v-if="loading" class="loading-veil"><LoaderCircle class="spin" :size="25" /><span>正在加载原型…</span></div></div>
          
        </div>
        <div v-else class="code-panel"><div class="code-toolbar"><Braces :size="15" /><select aria-label="源码区域" v-model="codeRegion"><option value="all">完整文件 · 只读</option><option v-for="region in sourceInfo.regions" :key="region.name" :value="region.name">{{ region.label || '自定义区域' }}</option></select><span>{{ codeText.split('\n').length }} 行</span><button class="quiet" @click="copySource"><Check v-if="codeCopied" :size="14" /><Copy v-else :size="14" />{{ codeCopied ? '已复制' : '复制' }}</button></div><div class="source-scroll"><pre class="line-numbers" aria-hidden="true">{{ lineNumbers }}</pre><pre class="source-code"><code>{{ codeText }}</code></pre></div></div>
        <div v-if="error" class="error-banner" role="alert"><AlertCircle :size="16" /><span>{{ error }}</span><button class="icon-button" aria-label="关闭错误提示" @click="error = ''"><X :size="14" /></button></div>
        <footer class="canvas-status"><span v-if="page" class="status-version">v{{ page.version }} · {{ page.modification_count || 0 }} 次修改</span><span :title="validationDetails + (savedAt ? ' · ' + savedAt : '')"><LoaderCircle v-if="locked" :size="13" class="spin" /><Check v-else :size="13" />{{ status }}</span><details v-if="runtimeErrors.length" class="runtime-warning"><summary><AlertCircle :size="13" />{{ runtimeErrors.length }} 条运行提示</summary><div><p v-for="warning in runtimeErrors" :key="warning">{{ warning }}</p></div></details></footer>
      </section>

      <InspectorPanel />
    </main>

    <StudioDialog />
    <div v-if="backendStale" class="stale-banner" role="alert"><AlertCircle :size="15" /><span>后台服务还在跑旧代码，新功能可能用不了：关掉原型工坊的终端窗口，再双击「启动原型工坊」重启一下。</span><button type="button" class="icon-button" aria-label="知道了" @click="backendStale = false"><X :size="13" /></button></div>
    <div v-if="notice" class="toast" role="status"><Check :size="16" />{{ notice }}</div>
  </div>
</template>
