<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { PanelsTopLeft, Plus, Upload, History, Download, Settings2, ChevronDown, ChevronRight, X, MessageSquare, Square, MousePointer2, Hand, Code2, Monitor, Tablet, Smartphone, Undo2, ArrowUp, Check, CheckCheck, LoaderCircle, SlidersHorizontal, SquareMousePointer, Palette, AlertCircle, ShieldCheck, Braces, FileCode2, CircleHelp, PanelLeftClose, PanelRightClose, Copy, Pencil, Ruler, Sparkles } from 'lucide-vue-next'
import { Scan, ImagePlus, Image as ImageIcon, FolderOpen, Layers, Maximize2, MoreHorizontal, Brain } from 'lucide-vue-next'
import ExpandBoard from './ExpandBoard.vue'
import { adoptPresync, bindExpand, dropPresync, presync, setFocusRoute, expand, expandAll, isFresh } from './expandStore.js'
import { buildExpandExport } from './expandExport.js'
import ImageReference from './ImageReference.vue'
import RegionCapture from './RegionCapture.vue'
import FileManager from './FileManager.vue'
import { previewMessage, PREVIEW_SANDBOX } from './previewMessage.js'
import { preparePreviewDocument } from './previewDocument.js'
import { consumeAgentStream, responseError } from './streamAgent.js'
import ExecutionCard from './ExecutionCard.vue'
import MemoryPanel from './MemoryPanel.vue'
import ModelSettings from './ModelSettings.vue'
import ResultCard from './ResultCard.vue'

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
if (typeof window !== 'undefined') {
  window.addEventListener('click', () => { modelMenu.value = false })
  window.addEventListener('blur', () => { modelMenu.value = false })
  window.addEventListener('keydown', e => { if (e.key === 'Escape') modelMenu.value = false })
}
const mode = ref('interact'), view = ref('preview'), device = ref('desktop')
const stored = key => { try { return localStorage.getItem(key) } catch { return null } }
const keepInspector = ref(stored('pf-inspector-pinned') === 'true')
// 「始终展开属性面板」在模型设置里勾，勾了马上生效、记在本机
watch(keepInspector, v => { try { localStorage.setItem('pf-inspector-pinned', String(v)) } catch { /* 存不了就只管这次 */ } if (v) rightOpen.value = true })
const leftOpen = ref(window.innerWidth > 960), rightOpen = ref(keepInspector.value)
const showGuide = ref(stored('pf-hide-guide') !== 'true')
const selected = ref(null), inspection = ref(null), textValue = ref(''), note = ref(''), input = ref('')
const regionKey = ref(0)   // 自增一次就重挂 RegionCapture，把上一次画的框擦掉
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
const canEdit = computed(() => !!inspection.value?.editable && !locked.value && !playing.value)
const undoCount = computed(() => page.value?.undo_count || 0)
const colorNames = { '--color-primary': '主色', '--color-bg': '页面背景', '--color-surface': '表面色', '--color-text': '正文', '--color-muted': '辅助文字', '--color-border': '边框', '--color-danger': '警示', '--color-success': '成功' }
const colors = computed(() => Object.entries({ ...sourceInfo.value.defaults, ...sourceInfo.value.tokens }).filter(([, v]) => /^#[\da-f]{3,8}$/i.test(v.trim())).map(([key, value]) => ({ key, value: value.trim(), label: colorNames[key] || key.replace(/^--/, '') })))
const numericFields = [ { key: 'font-size', label: '字号', step: 2 }, { key: 'border-radius', label: '圆角', step: 2 }, { key: 'padding-top', label: '上内边距', step: 4 }, { key: 'padding-bottom', label: '下内边距', step: 4 }, { key: 'padding-left', label: '左内边距', step: 4 }, { key: 'padding-right', label: '右内边距', step: 4 } ]
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
function setMode(value) { mode.value = value; if (view.value === 'code') view.value = 'preview'; send({ type: 'PA_SET_MODE', mode: value }); if (window.innerWidth <= 960) { leftOpen.value = false; rightOpen.value = false } if (value === 'select') toast('点击选中；按住 Shift 或 ⌘ 可以多选几处'); if (value === 'box') toast('按住拖动，框选你想调整的区域') }
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
function clearSelectionOnly() { selected.value = null; inspection.value = null; note.value = ''; textValue.value = ''; ++regionKey.value; send({ type: 'PA_SELECT', selector: '' }) }
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
const aiOnly = computed(() => !!selected.value && !!inspection.value && !inspection.value.editable)
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
  send({ type: 'PA_RENDER_MARKERS', annotations: annotations.value })
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
    const result = await api(endpoint('/inspect') + '?selector=' + encodeURIComponent(target.selector))
    if (selected.value?.selector !== target.selector) return
    inspection.value = result
    if (result.text_editable) textValue.value = result.text
  } catch (e) { error.value = e.message }
}
async function onMessage(event) {
  if (event.source !== previewFrame.value?.contentWindow) return
  const data = event.data || {}
  if (data.source !== 'prototype-agent' || data.projectId !== project.value?.id || data.pageId !== pageId.value) return
  if (data.type === 'READY') {
    send({ type: 'PA_SET_MODE', mode: mode.value })
    send({ type: 'PA_RENDER_MARKERS', annotations: annotations.value })
    if (selected.value && selected.value.kind !== 'region' && !selected.value.card) send({ type: 'PA_SELECT', selector: selected.value.selector })
  }
  if (data.type === 'SELECTED' && !loading.value) await inspect(data)
  if (data.type === 'REGION_SELECTED' && !loading.value) { selected.value = data; inspection.value = { editable: false, kind: 'region' }; textValue.value = data.text; rightOpen.value = true; if (window.innerWidth <= 960) leftOpen.value = false }
  if (data.type === 'NOTICE') toast(data.message)
  if (data.type === 'SELECTION_MISSING') closeSelection()
  if (data.type === 'SELECTION_CLEARED') clearSelectionOnly()   // 按住 Shift 把最后一个也取消掉了
  if (data.type === 'SCROLL_STATE') previewScroll.value = data.state
  if (data.type === 'WIDTH') canvasWidth.value = data.width
  if (data.type === 'SHORTCUT') keydown(data)
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
      Object.assign(frame.style, { position: 'fixed', left: '-20000px', top: '0', width: (canvasWidth.value || 1200) + 'px', height: '800px', border: '0' })
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


async function edit(prop, value) {
  if (locked.value || (!prop.startsWith('--') && (!inspection.value?.editable || playing.value))) return
  const selector = selected.value?.selector || ''
  saving.value = true; error.value = ''; status.value = '修改中'
  send({ type: 'PA_PREVIEW', selector, prop, value: String(value) })
  const card = selected.value?.card
  let committed = false
  if (card || prop.startsWith('--')) cardPatch.value = { seq: ++patchSeq, prop, value: String(value), route: prop.startsWith('--') ? null : card.route, nodeId: prop.startsWith('--') ? null : card.nodeId, rels: card?.rels || [] }
  try {
    const result = await post(endpoint('/edit'), { selector, prop, value: String(value), expected_hash: sourceInfo.value.hash })
    await checkAndCommit(result); committed = !!result.changed
    if (committed && selected.value?.selector === selector && !prop.startsWith('--')) selected.value = { ...selected.value, styles: { ...(selected.value.styles || {}), [prop]: String(value) } }
    if (!result.changed) status.value = '没有新的改动'
    await refresh(false)
  } catch (e) {
    if (committed) status.value = '已保存 · 预览刷新失败'
    else { error.value = e.message; status.value = '修改未保存 · 已保留原页面' }
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
function changeNumber(key, event) {
  const raw = String(event.target.value ?? '').trim()
  if (!raw) return   // 清空了不是想改成 0
  const n = Number(raw)
  if (!Number.isFinite(n) || n < 0 || n > 160) { toast('请输入 0–160 之间的数值'); return }
  edit(key, `${n}px`)
}
async function undo(changeId = '') {
  if (locked.value || !undoCount.value) return
  saving.value = true; error.value = ''
  try {
    await checkAndCommit(await post(endpoint('/undo'), { change_id: typeof changeId === 'string' ? changeId : '' }))
    await refresh(false); toast('已撤销上一步')
  } catch (e) { error.value = e.message; status.value = '撤销失败 · 页面没变' }
  finally { saving.value = false; reselect() }
}


async function saveNote() {
  const content = input.value.trim()
  if (!selected.value || !content || locked.value) return
  const wasRegion = selected.value.kind === 'region'
  saving.value = true
  try {
    await post(endpoint('/annotations'), { ...selected.value, ...modalContext(selected.value), note: content })
    if (input.value.trim() === content) input.value = ''
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
function openLeft() { leftOpen.value = true; if (window.innerWidth <= 960) rightOpen.value = false }
function toggleRight() { rightOpen.value = !rightOpen.value; if (rightOpen.value && window.innerWidth <= 960) leftOpen.value = false }
async function toAI() { leftOpen.value = true; if (window.innerWidth <= 960) rightOpen.value = false; await nextTick(); composer.value?.focus() }
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
      if (event.type === 'plan') current.plan = event.steps
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
async function applySuggestion({ suggestion, discussion }) {
  await runAgent('按已讨论的建议修改：' + suggestion.instruction, '', { intent: 'edit', includeAnnotations: false, selection: discussion.selection || null })
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
async function refreshMemoryCount() { if (!project.value) return; try { const m = await api(`/api/projects/${project.value.id}/memory`); memoryCount.value = (m.project?.memory?.length || 0) + (m.global?.memory?.length || 0) } catch { /* 读不到就不显示数 */ } }
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
  if (selected.value) { input.value = '只修改当前选中的位置：' + run.request; await toAI(); return }
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
watch(() => pendingExport.value && !expand.discovering && expand.routes.length > 0 && expand.routes.every(r => isFresh(r.hash)), ready => {
  if (ready) { pendingExport.value = false; exportExpand() }
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
function formatTime(value) { return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }
function keydown(event) {
  if (dialog.value?.open) return
  const key = event.key.toLowerCase(), command = event.metaKey || event.ctrlKey
  const editing = event.target?.closest?.('input,textarea,select,[contenteditable=true]')
  if (command && key === 'enter') { event.preventDefault?.(); runAgent(); return }
  if (editing || event.altKey) return
  if (command && key === 'z' && !event.shiftKey) { event.preventDefault?.(); undo(); return }
  if (command) return
  if (key === 'escape') { if (boardFocus.value != null) { boardFocus.value = null; return } if (boardOpen.value) { showPreview(); return } closeSelection(); setMode('interact') }
  if (key === 'e' && page.value) { event.preventDefault?.(); toggleBoard(); return }
  if ({ h: 'interact', v: 'select', b: 'box' }[key] && page.value) { event.preventDefault?.(); setMode({ h: 'interact', v: 'select', b: 'box' }[key]) }
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
</script>

<template>
  <div class="studio">
    <header class="app-header">
      <div class="header-left"><a class="brand" href="/" aria-label="原型工坊首页"><span class="brand-symbol"><PanelsTopLeft :size="21" /></span><strong>原型工坊</strong><span class="local-badge">本地</span></a><div class="project-picker"><span class="divider"></span><select aria-label="切换项目" :value="project?.id || ''" :disabled="locked || !projects.length" @change="chooseProject($event.target.value)"><option v-if="!projects.length" value="">我的工作区</option><option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option></select><ChevronDown :size="14" /><label v-if="project?.pages.length > 1" class="file-picker" title="这个项目里有多个 HTML 文件，切换要看的那个"><span>/</span><select aria-label="切换原型文件" :value="pageId" :disabled="locked" @change="choosePage($event.target.value)"><option v-for="p in project.pages" :key="p.id" :value="p.id">{{ p.title }} · v{{ p.version }}</option></select><ChevronDown :size="13" /></label></div><button v-if="!leftOpen" class="icon-button" title="打开对话" aria-label="打开对话" @click="openLeft"><MessageSquare :size="17" /></button></div>
      <div class="header-center"><div class="view-tabs" role="tablist" aria-label="查看方式"><button :class="{ active: view === 'preview' && !boardOpen }" @click="showPreview"><Monitor :size="14" /><span>预览</span></button><button :class="{ active: view === 'preview' && boardOpen }" :disabled="!page || !previewDoc" title="展开这一页的所有弹窗 · E" @click="showBoard"><Layers :size="14" /><span>展开</span><kbd>E</kbd></button></div><div v-if="page && view !== 'code'" class="mode-tools" role="group" aria-label="操作方式"><button :class="{ active: mode === 'interact' }" :disabled="loading" title="交互 · H：像真用户一样点；在展开里点卡片可以交互" @click="setMode('interact')"><Hand :size="15" /><span>交互</span><kbd>H</kbd></button><button :class="{ active: mode === 'select' }" :disabled="loading" title="点选 · V（按住 Shift / ⌘ 多选同一视图内的元素）" @click="setMode('select')"><MousePointer2 :size="15" /><span>点选</span><kbd>V</kbd></button><button :class="{ active: mode === 'box' }" :disabled="loading" title="拉框 · B" @click="setMode('box')"><Scan :size="15" /><span>拉框</span><kbd>B</kbd></button></div></div>
      <nav class="header-right" aria-label="画布和项目操作"><div class="device-tools" v-if="view === 'preview' && !boardOpen"><button v-for="d in [{ id: 'desktop', label: '桌面', icon: Monitor }, { id: 'tablet', label: '平板', icon: Tablet }, { id: 'mobile', label: '手机', icon: Smartphone }]" :key="d.id" class="icon-button" :class="{ active: device === d.id }" :aria-label="d.label + '预览'" :title="d.label" @click="device = d.id"><component :is="d.icon" :size="16" /></button><span class="actual-width">{{ canvasWidth }} px</span></div><div class="history-tools"><button class="icon-button" aria-label="撤销上一步" :title="undoCount ? '撤销上一步 · ⌘/Ctrl + Z' : '暂无可撤销的修改'" :disabled="!undoCount || locked" @click="undo()"><Undo2 :size="16" /></button><button class="history-button" :disabled="!page || loading" title="历史版本" @click="openDialog('history')"><History :size="15" /><span>{{ page ? 'v' + page.version : '历史' }}</span></button></div><button class="export-button" :disabled="!page || locked" title="导出 HTML" @click="download()"><Download :size="15" /><span>导出</span></button><details ref="moreMenu" class="more-menu"><summary class="icon-button" aria-label="更多" title="新建、导入、文件管理、配色、设计规范、模型设置"><MoreHorizontal :size="18" /></summary><div class="more-list" @click="moreMenu?.removeAttribute('open')"><button :disabled="locked" @click="openDialog('new')"><Plus :size="15" />新建</button><button :disabled="locked" @click="fileInput.click()"><Upload :size="15" />导入</button><button :disabled="locked" @click="openDialog('files')"><FolderOpen :size="15" />文件管理</button><hr><button :disabled="!page || loading" @click="openDialog('palette')"><Palette :size="15" />项目配色</button><button @click="openDialog('spec')"><Ruler :size="15" />设计规范</button><button v-if="project?.pages.length > 1" @click="download(true)"><Download :size="15" />导出整个项目 ZIP</button><button @click="openDialog('settings')"><Settings2 :size="15" />模型设置</button></div></details><span class="divider"></span><button class="icon-button" :class="{ active: rightOpen }" aria-label="切换属性面板" @click="toggleRight"><SlidersHorizontal :size="17" /></button></nav>
      <input ref="fileInput" type="file" class="sr-only" accept=".html,.htm,.zip" @change="upload" />
      <input ref="imageInput" type="file" class="sr-only" accept="image/png,image/jpeg,image/webp" @change="uploadImage" />
    </header>

    <main class="workspace" :class="{ 'left-closed': !leftOpen, 'right-closed': !rightOpen }">
      <div v-if="(leftOpen || rightOpen)" class="mobile-scrim" @click="leftOpen = false; rightOpen = false"></div>
      <aside class="conversation-panel" :class="{ collapsed: !leftOpen }" aria-label="对话">
        <label class="mobile-project-picker"><span>当前项目</span><select aria-label="切换当前项目" :value="project?.id || ''" :disabled="locked || !projects.length" @change="chooseProject($event.target.value)"><option v-if="!projects.length" value="">尚未创建项目</option><option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option></select></label>
        <div class="panel-header"><strong class="panel-title"><MessageSquare :size="15" />对话</strong><button class="icon-button" aria-label="收起对话" @click="leftOpen = false"><PanelLeftClose :size="16" /></button></div>

          <div ref="chatBox" class="messages" aria-live="polite">
            <div v-if="!messages.length && !pendingUser && showGuide" class="conversation-empty compact-guide"><h2>先聊清楚，再动手。</h2><p>可以一起评价设计、比较方案；确定方向后，只改需要调整的位置。</p><button v-for="suggestion in ['现在的设计怎么样？', '有哪些地方值得优化？', selected ? '调整选中区域的对齐' : '检查一下交互有没有漏的']" :key="suggestion" class="prompt-suggestion" :disabled="!page" @click="input = suggestion; toAI()">{{ suggestion }}<ChevronRight :size="14" /></button><button class="text-button dismiss-guide" @click="hideGuide">不再显示</button></div>
            <article v-for="message in messages" :key="message.id" class="message" :class="message.role"><div class="message-author"><span>{{ message.role === 'user' ? '你' : '设计助手' }}</span><time>{{ formatTime(message.created_at) }}</time></div><ResultCard v-if="message.role === 'assistant' && (message.report || message.clarification || message.discussion || message.changed)" :result="message" :locked="locked" :can-undo="page?.last_undo_id === message.change_id" @undo="undo" @choose="chooseAnswer" @apply="applySuggestion" @discuss="discussSuggestion" @rephrase="useRephrase" @forget="forgetFromCard" /><p v-else>{{ message.content }}</p><div class="message-tools"><button class="icon-button" aria-label="复制这条内容" title="复制" @click="copyMessage(message.report?.summary || message.discussion?.answer || message.content)"><Copy :size="13" /></button><button v-if="message.role === 'user'" class="icon-button" aria-label="编辑后重新发送" title="编辑后重发" :disabled="locked" @click="editAndResend(message)"><Pencil :size="13" /></button></div></article>
            <article v-if="pendingUser && !messages.some(m => m.role === 'user' && m.content === pendingUser && m === messages[messages.length - 1])" class="message user"><div class="message-author">你</div><p>{{ pendingUser }}</p><img v-if="pendingRef" class="message-shot" :src="pendingRef.data_url" :alt="pendingRef.name"></article>
                        <ExecutionCard v-for="run in currentRuns" :key="run.id" :run="run" :locked="locked" @retry="runAgent(run.request, '', run.options)" @repair="runAgent(run.request, run.error.detail, run.options)" @settings="openDialog('settings')" @select="setMode('select')" @fill="smallerRequest(run)" @point="pointAt(run)" @dismiss="run.status = 'dismissed'" @stop="stopAgent" />

          </div>
          <div class="composer-area">
            <div v-if="selected" class="selection-context"><SquareMousePointer :size="14" /><span>{{ elementLabel(selected) }}<small v-if="selectionPlace">{{ selectionPlace }}</small></span><button class="icon-button" aria-label="清除选中目标" @click="closeSelection"><X :size="12" /></button></div>
            <button v-if="annotations.length" class="annotation-count batch-action" :disabled="locked" @click="runAgent('请逐条处理已记下的修改意见，保留其他区域。', '', { intent: 'edit' })"><CheckCheck :size="14" />已记下 {{ annotations.length }} 条，一起修改<ArrowUp :size="14" /></button>
            <div v-if="reference" class="reference-attachment"><button class="reference-open" @click="openDialog('image')"><img :src="reference.data_url" alt="参考截图缩略图"><span>{{ reference.name }}<small :class="{ warn: !model.supports_vision }">{{ !model.supports_vision ? '当前模型看不了图片' : reference.regions.length ? reference.regions.length + ' 个框选区域 · 点开修改' : '参考整张图 · 点开可圈选' }}</small></span></button><button class="icon-button" aria-label="移除参考截图" :disabled="locked" @click="reference = null"><X :size="13" /></button></div>
            <div class="composer-mode" role="group" aria-label="对话方式"><div class="mode-switch"><button v-for="option in [{ value: 'auto', label: '自动' }, { value: 'discuss', label: '只讨论' }, { value: 'edit', label: '直接改' }]" :key="option.value" type="button" :class="{ active: composerIntent === option.value }" :aria-pressed="composerIntent === option.value" :disabled="busy" @click="composerIntent = option.value">{{ option.label }}</button></div><span>{{ composerIntent === 'discuss' ? '不改代码' : composerIntent === 'edit' ? '局部修改' : '提问先聊，指令再改' }}</span></div>
            <div class="composer" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave.self="dragging = false" @drop.prevent="dropImage"><textarea ref="composer" v-model="input" @paste="pasteImage" aria-label="对话内容" :placeholder="busy ? '可以先写好下一条消息…' : selected ? '聊聊这个位置，或者告诉我怎么改…' : '这个设计怎么样？或者，告诉我想怎么改…\n截图可以直接粘贴进来'"></textarea><div class="composer-actions"><button class="icon-button" :title="model.supports_vision ? '加截图：也可以直接粘贴（⌘/Ctrl + V）或拖进输入框' : '加截图（当前模型看不了图片，发送前要在设置里换模型）'" aria-label="添加参考截图" :disabled="locked" @click="imageInput.click()"><ImagePlus :size="18" /></button><span v-if="!selected">⌘ / Ctrl ↵</span><span v-else class="composer-spacer"></span><button v-if="selected" class="quiet" :disabled="locked || !input.trim()" @click="saveNote">先记下</button><button v-if="activeRun" type="button" class="outline stop-run" :disabled="!activeRun.runId || activeRun.stopping" title="停在下一步之前；已经改好的部分会保留并检查，可以撤销" @click="stopAgent"><Square :size="12" />{{ activeRun.stopping ? '正在停止…' : '停止' }}</button><button v-else class="primary direct-modify" :disabled="locked || (!input.trim() && !annotations.length) || !page" :aria-label="composerIntent === 'edit' ? '执行修改' : '发送消息'" @click="runAgent()"><LoaderCircle v-if="busy" :size="15" class="spin" /><ArrowUp v-else :size="15" />{{ composerIntent === 'edit' ? '执行修改' : '发送' }}</button></div></div>
            <button v-if="project" class="model-status memory-status" title="AI 记住的约定和习惯：点开看、改、删" @click="openMemory"><Brain :size="12" />记忆 {{ memoryCount }}</button><div class="model-switch"><button class="model-status" :aria-expanded="modelMenu" title="切换模型" @click.stop="model.has_key ? (modelMenu = !modelMenu) : openDialog('settings')"><span class="status-dot" :class="{ connected: model.has_key }"></span>{{ model.has_key ? ((model.profiles || []).find(p => p.active)?.name || model.model) : '连接模型' }}<span v-if="lastResult?.usage?.total_tokens"> · {{ lastResult.usage.total_tokens.toLocaleString() }} tokens</span><ChevronDown :size="12" /></button>
              <div v-if="modelMenu" class="model-menu" role="menu" @click.stop><p>切换模型</p><button v-for="p in model.profiles || []" :key="p.id" type="button" role="menuitemradio" :aria-checked="p.active" :class="{ active: p.active }" :disabled="locked || switchingModel" @click="switchModel(p)"><Check v-if="p.active" :size="13" /><i v-else></i><span><b>{{ p.name || p.model }}</b><small>{{ p.name ? p.model + ' · ' : '' }}{{ p.host }}{{ p.has_key ? '' : ' · 缺密钥' }}</small></span><em v-if="p.supports_vision">看图</em></button><button type="button" class="manage" @click="modelMenu = false; openDialog('settings')"><Plus :size="13" />绑定或管理模型…</button><small v-if="locked" class="menu-note">AI 正在处理，等它做完再切换</small></div></div>
          </div>
      </aside>

      <section class="canvas-panel" aria-label="原型画布">
        <div v-if="view === 'preview'" class="canvas" :class="device">

          <ExpandBoard v-if="boardMounted" :class="{ 'view-hidden': !boardOpen }" :aria-hidden="!boardOpen" v-model:focus="boardFocus" v-model:route="boardRoute" :notes="annotations" :patch="cardPatch" :page-name="page?.title" :selection="selected" :mode="mode" @open="openFromBoard" @select="pickFromBoard" @clear="closeSelection" @mode="setMode" @export="requestExport" />
          <div class="preview-shell" :class="{ 'is-selecting': mode !== 'interact', 'view-hidden': boardOpen }" :aria-hidden="boardOpen"><iframe v-if="previewDoc" ref="previewFrame" title="原型预览" :srcdoc="previewDoc" :sandbox="PREVIEW_SANDBOX"></iframe><div v-else class="empty-canvas"><div class="empty-emblem"><PanelsTopLeft :size="30" :stroke-width="1.4" /></div><h1>给想法一个可操作的样子</h1><p>从已有的 HTML 开始修改，<br>或描述需求，让 AI 帮你搭建第一版。</p><div><button class="primary" @click="openDialog('new')"><Plus :size="16" />新建原型</button><button class="outline" @click="fileInput.click()"><Upload :size="16" />导入原型</button></div><span>支持 HTML、包含多页面的 ZIP</span></div><RegionCapture v-if="previewDoc && mode === 'box' && !loading" :key="regionKey" @select="send({ type: 'PA_BOX_RECT', bounds: $event })" @scroll="send({ type: 'PA_SCROLL', ...$event })" /><div v-if="loading" class="loading-veil"><LoaderCircle class="spin" :size="25" /><span>正在加载原型…</span></div></div>
          
        </div>
        <div v-else class="code-panel"><div class="code-toolbar"><Braces :size="15" /><select aria-label="源码区域" v-model="codeRegion"><option value="all">完整文件 · 只读</option><option v-for="region in sourceInfo.regions" :key="region.name" :value="region.name">{{ region.label || '自定义区域' }}</option></select><span>{{ codeText.split('\n').length }} 行</span><button class="quiet" @click="copySource"><Check v-if="codeCopied" :size="14" /><Copy v-else :size="14" />{{ codeCopied ? '已复制' : '复制' }}</button></div><div class="source-scroll"><pre class="line-numbers" aria-hidden="true">{{ lineNumbers }}</pre><pre class="source-code"><code>{{ codeText }}</code></pre></div></div>
        <div v-if="error" class="error-banner" role="alert"><AlertCircle :size="16" /><span>{{ error }}</span><button class="icon-button" aria-label="关闭错误提示" @click="error = ''"><X :size="14" /></button></div>
        <footer class="canvas-status"><span v-if="page" class="status-version">v{{ page.version }} · {{ page.modification_count || 0 }} 次修改</span><span :title="validationDetails + (savedAt ? ' · ' + savedAt : '')"><LoaderCircle v-if="locked" :size="13" class="spin" /><Check v-else :size="13" />{{ status }}</span><details v-if="runtimeErrors.length" class="runtime-warning"><summary><AlertCircle :size="13" />{{ runtimeErrors.length }} 条运行提示</summary><div><p v-for="warning in runtimeErrors" :key="warning">{{ warning }}</p></div></details></footer>
      </section>

      <aside class="inspector" :class="{ collapsed: !rightOpen }" aria-label="属性面板">
        <div class="panel-header"><strong>属性</strong><span class="free-label">{{ aiOnly ? 'AI 修改' : '微调不调用 AI' }}</span><button class="icon-button" aria-label="收起属性" @click="rightOpen = false"><PanelRightClose :size="16" /></button></div>
        <div class="inspector-scroll">
          <div v-if="!selected && !annotations.length" class="inspector-empty"><SquareMousePointer :size="28" :stroke-width="1.3" /><h2>还没有选中元素</h2><p>{{ mode === 'box' ? '按住拖动框选一片区域，' : '按 V 或在画布上方切换点选，' }}<br>{{ mode === 'box' ? '一次可以选中多个元素。' : '再点击要调整的位置。' }}</p></div>
          <div v-else-if="!selected" class="noted-panel">
            <div class="section-label">已记下的意见<span class="count">{{ annotations.length }}</span></div>
            <div v-for="(a, i) in annotations" :key="a.id" class="annotation-row"><span class="annotation-number">{{ i + 1 }}</span><div><b>{{ a.kind === 'region' ? `框选 ${a.targets?.length || 0} 个元素` : (a.text?.slice(0, 30) || a.tag) }}</b><p>{{ a.note }}</p></div><button class="icon-button" aria-label="移除这条意见" :disabled="locked" @click="removeAnnotation(a.id)"><X :size="14" /></button></div>
            <p class="field-hint">{{ mode === 'interact' ? '按 V 点选或按 B 拉框，继续标下一处。' : '继续标下一处，或一起交给 AI 修改。' }}</p>
            <button class="primary full-width" :disabled="locked" @click="runAgent('请逐条处理已记下的修改意见，保留其他区域。', '', { intent: 'edit' })"><CheckCheck :size="15" />这 {{ annotations.length }} 条一起修改</button>
          </div>
          <template v-else>
            <div class="selected-heading"><span class="element-icon"><MousePointer2 :size="17" /></span><div><h2>{{ elementLabel(selected) }}</h2><small>只调整选中的位置</small></div><button class="icon-button" aria-label="取消选择" @click="closeSelection"><X :size="14" /></button></div>
            <p v-if="!inspection" class="inspector-loading"><LoaderCircle class="spin" :size="14" />定位中…</p>
            <template v-else-if="aiOnly && (selected.card || selected.modal)">
              <section class="property-section"><div class="section-label">所在位置<span>目标不会丢失</span></div><p class="target-location">{{ selected.pageTitle || page?.title }}<br>{{ selected.viewTitle || selected.modal }} › {{ selected.kind === 'region' ? '多处选择' : elementLabel(selected) }}</p><button v-if="selected.card" class="outline full-width" @click="focusSelected"><Maximize2 :size="15" />放大编辑</button></section>
              <section class="property-section"><div class="section-label">选中内容<span>{{ selected.kind === 'region' ? '多选' : '只读预览' }}</span></div><div v-if="selected.kind === 'region'" class="region-list"><span v-for="(target, index) in selected.targets" :key="index">{{ target.text?.slice(0, 40) || target.tag }}</span></div><p v-else class="selected-text">{{ selected.text || selected.tag }}</p><p class="field-hint">{{ selected.kind === 'region' ? '把这些位置的修改需求一起写入对话。' : selected.modal ? '这是动态弹窗中的元素，由 AI 修改对应模板；不能直接套用静态页面的微调。' : '这个位置由页面脚本生成，由 AI 修改对应代码。' }}</p><button class="primary full-width write-request" @click="toAI"><MessageSquare :size="15" />写修改需求</button><div class="quick-actions"><button @click="quickFill('text')">修改选中文字<ChevronRight :size="14" /></button><button @click="quickFill('short')">缩短说明<ChevronRight :size="14" /></button></div></section>
              <section class="property-section"><p class="sync-line"><Check :size="14" />选中位置已同步到对话</p><p class="field-hint">切换查看方式不会清空目标。已选元素在当前视图看不到时，仍保留名称与所属弹窗。</p><button class="outline full-width" @click="closeSelection">取消选择</button></section>
            </template>
            <div v-else-if="!inspection.editable" class="dynamic-note"><Scan v-if="selected.kind === 'region'" :size="16" /><AlertCircle v-else :size="16" /><div><b>{{ selected.kind === 'region' ? `已框选 ${selected.targets.length} 个元素` : '这是动态生成的内容' }}</b><p>{{ selected.kind === 'region' ? '在对话中写下这片区域需要怎么改，可以直接修改或先记下。' : '这个位置由页面交互生成，无法直接微调。可以在对话中描述修改需求。' }}</p><div v-if="selected.targets" class="region-targets"><span v-for="(target, index) in selected.targets" :key="index">{{ target.text?.slice(0, 28) || target.tag }}</span></div><button class="text-button" @click="toAI">交给 AI 修改<ChevronRight :size="13" /></button></div></div>
            <template v-else>
              <div v-if="playing" class="dynamic-note play-note"><Hand :size="16" /><div><b>交互中 · 属性只读</b><p>交互时的操作不会保存。要改这个元素，先回到编辑。</p><button class="outline" @click="setMode('select')">返回编辑</button></div></div>
              <section class="property-section"><div class="section-label">内容<span>当前元素</span></div><label class="field-label" for="element-text">文字</label><textarea id="element-text" class="text-property" v-model="textValue" :disabled="!canEdit || !inspection.text_editable" @change="edit('text', textValue)"></textarea><p v-if="!inspection.text_editable" class="field-hint">包含子元素，请点选具体文字进行编辑。</p></section>
              <section class="property-section"><div class="section-label">外观<span>当前元素</span></div><label v-for="field in [{ key: 'color', label: '文字颜色' }, { key: 'background-color', label: '背景颜色' }]" :key="field.key" class="color-field"><span>{{ field.label }}</span><div><i :style="{ background: selected.styles?.[field.key] }"></i><select :aria-label="field.label" value="" :disabled="!canEdit" @change="edit(field.key, $event.target.value)"><option value="" disabled>当前颜色</option><option v-for="color in colors" :key="color.key" :value="`var(${color.key})`">{{ color.label }} · {{ color.value }}</option></select></div></label><div class="number-grid"><label v-for="field in numericFields" :key="field.key"><span>{{ field.label }}</span><div class="number-control"><input type="number" min="0" max="160" :step="field.step" :aria-label="field.label" :value="Number.isFinite(parseFloat(selected.styles?.[field.key])) ? parseFloat(selected.styles[field.key]) : ''" placeholder="未读取" :disabled="!canEdit" @change="changeNumber(field.key, $event)"><span>px</span></div></label></div><label class="visibility-control"><span>显示元素</span><input type="checkbox" role="switch" :checked="selected.styles?.display !== 'none'" :disabled="!canEdit" @change="edit('display', $event.target.checked ? 'revert' : 'none')"><span class="switch-track"></span></label></section>
            </template>
            <section v-if="selected.kind !== 'region' && !(aiOnly && (selected.card || selected.modal))" class="property-section ai-property"><button class="outline full-width" @click="toAI"><MessageSquare :size="15" />写修改需求<ChevronRight :size="14" /></button></section>
          </template>

        </div>

      </aside>
    </main>

    <dialog ref="dialog" class="studio-dialog" :class="{ 'image-dialog': dialogType === 'image', 'files-dialog': dialogType === 'files' }" @cancel="dialogBusy && $event.preventDefault()" @click="($event.target === dialog) && closeDialog()">
      <div class="dialog-header"><h2>{{ dialogType === 'settings' ? '模型' : dialogType === 'history' ? '版本历史' : dialogType === 'image' ? '截图圈选' : dialogType === 'files' ? '文件管理' : dialogType === 'palette' ? '项目配色' : dialogType === 'spec' ? '设计规范' : '新建原型' }}</h2><button class="icon-button" aria-label="关闭弹窗" :disabled="dialogBusy" @click="closeDialog"><X :size="19" /></button></div>
      <FileManager v-if="dialogType === 'files'" :key="fileManagerRevision" :current-project-id="project?.id" @changed="filesChanged" @open="openManagedProject" @busy="dialogBusy = $event" />
      <div v-else-if="dialogType === 'image' && reference"><ImageReference :reference="reference" @update="reference.regions = $event" /><p class="field-hint">已有原型：参考截图，局部修改当前代码。只有截图：新建独立原型，不会据此重建原项目源码。</p><p class="field-hint">截图仅在本次对话中保留。执行时会发送给你配置的视觉模型，用于理解参考与修改意见。</p><p v-if="dialogError" class="form-error">{{ dialogError }}</p><div class="dialog-actions image-actions"><button class="quiet" :disabled="dialogBusy" @click="imageInput.click()">更换截图</button><button v-if="project" class="outline" :disabled="dialogBusy" @click="useReference(true)">以截图新建原型</button><button class="primary" :disabled="dialogBusy" @click="useReference(false)"><ImageIcon :size="16" />{{ project ? '用于当前原型' : '以截图新建原型' }}</button></div></div>
      <div v-else-if="dialogType === 'spec'" class="spec-dialog"><div class="spec-tabs"><button type="button" :class="{ active: specTab === 'spec' }" @click="specTab = 'spec'">规范正文</button><button type="button" :class="{ active: specTab === 'parts' }" @click="specTab = 'parts'">组件库<span class="count">{{ componentList.length }}</span></button><button type="button" :class="{ active: specTab === 'memory' }" :disabled="!project" @click="specTab = 'memory'">记忆<span class="count">{{ memoryCount }}</span></button></div><p class="dialog-intro">{{ specTab === 'spec' ? '这段文字每次修改都会完整发给模型，是视觉底线。换成你们公司的规范，AI 改出来的就按你们的来——别清空，空的等于没有依据。' : specTab === 'parts' ? '这里的组件模型平时只看到清单，要用时才取原文，所以存再多也不拖慢对话。生成大页面时它会照抄你们的结构。' : '你说过的长期约定，AI 会自己记下来，对这个项目的所有页面生效，换页也不会忘。不同意的直接删掉。' }}</p><textarea v-show="specTab === 'spec'" v-model="specDraft" class="spec-editor" aria-label="设计规范内容" spellcheck="false"></textarea><p v-if="specNotice" class="spec-notice">{{ specNotice }}</p><p v-if="dialogError" class="form-error" role="alert">{{ dialogError }}</p><input ref="specInput" type="file" class="sr-only" accept=".html,.htm,.css,text/html,text/css,text/plain" @change="importSpecTokens" /><div v-show="specTab === 'spec'" class="dialog-actions"><button type="button" class="quiet" :disabled="dialogBusy" @click="specInput.click()">从现有页面读配色</button><button type="button" class="outline" :disabled="dialogBusy || specDraft === specSaved" @click="specDraft = specSaved">放弃改动</button><button class="primary" :disabled="dialogBusy || specDraft === specSaved" @click="saveSpec">保存规范</button></div><p v-show="specTab === 'spec'" class="field-hint">导入的旧原型不会被强制套用本规范——规范里这条的优先级高于全部视觉要求。</p>
        <section v-if="specTab === 'memory' && project" class="memory-shelf"><MemoryPanel :project-id="project.id" @count="memoryCount = $event" /></section>
        <section v-show="specTab === 'parts'" class="component-shelf"><template v-if="skillList.length"><div class="section-label"><span>Skill 包</span><span>{{ skillList.length }} / 12</span></div><div v-for="item in skillList" :key="item.name" class="skill-row"><div><b>{{ item.name }}</b><small>{{ item.description }}</small><em v-if="item.files.length">{{ item.files.length }} 个附带文件 · {{ item.files.slice(0, 3).join('、') }}{{ item.files.length > 3 ? ' …' : '' }}</em></div><button class="icon-button" :aria-label="'卸掉 ' + item.name" title="卸掉这个 skill" :disabled="dialogBusy" @click="removeSkill(item.name)"><X :size="13" /></button></div></template><div class="section-label" :style="skillList.length ? 'margin-top:18px' : ''"><span>单个组件</span><span>{{ componentList.length }} / 40</span></div><p class="field-hint"><code>.html</code> 是可照抄的代码，<code>.md</code> 是写法说明；整包 <code>.zip</code> 直接传也行，会自动挑出里面的 html 和 md。每条后面那句用途说明取自文件第一行，它是 AI 判断何时用哪个组件的依据。<br>带 <code>SKILL.md</code> 的 zip 会按 skill 装上：整包结构原样保留，正文里的相对路径仍然有效。<b>SKILL.md 正文每轮都完整发给 AI，装上就默认生效</b>，不用你再提；它引用的组件库、规范那些大文件仍然按需取。</p><div v-for="item in componentList" :key="item.name" class="component-row"><div><b>{{ item.name }}</b><small>{{ item.kind }} · {{ item.description }}</small></div><button class="icon-button" :aria-label="'移除 ' + item.name" :disabled="dialogBusy" @click="removeComponent(item.name)"><X :size="13" /></button></div><p v-if="!componentList.length" class="field-hint muted-empty">还没有组件。生成大页面时它最管用——AI 会照抄你们的结构，而不是每次自己发明一个。</p><input ref="componentInput" type="file" class="sr-only" accept=".html,.htm,.md,.markdown,.zip,text/html,text/markdown,text/plain,application/zip,application/x-zip-compressed" @change="addComponent" /><button type="button" class="outline full-width" :disabled="dialogBusy" @click="componentInput.click()">导入组件或 skill 包</button></section></div>
      <div v-else-if="dialogType === 'palette'"><section class="property-section token-section"><div class="section-label"><span class="label-with-icon"><Palette :size="15" />项目设计变量</span><span>全局</span></div><p class="field-hint">修改变量，所有引用它的元素一起更新。</p><details><summary><span class="palette-preview"><i v-for="color in colors.slice(0, 6)" :key="color.key" :style="{ background: color.value }"></i></span><span>查看与调整</span><ChevronDown :size="13" /></summary><label v-for="color in colors" :key="color.key" class="token-row"><span>{{ color.label }}<small>{{ color.key }}</small></span><div><input type="color" :aria-label="`全局${color.label}`" :value="color.value.length === 7 ? color.value : '#ffffff'" :disabled="locked" @change="edit(color.key, $event.target.value)"><code>{{ color.value }}</code></div></label><p v-if="!Object.keys(sourceInfo.tokens).length" class="field-hint">当前为旧版原型。使用变量时会追加定义，现有视觉保持原样。</p></details></section></div>
      <ModelSettings v-else-if="dialogType === 'settings'" :model="model" :notice="dialogError" v-model:keep-inspector="keepInspector" @saved="model = $event" />
      <form v-else-if="dialogType === 'new'" @submit.prevent="createProject"><p class="dialog-intro">先建立可编辑的页面骨架，再逐步把想法做出来。</p><label>原型名称<input v-model="projectName" autofocus required maxlength="80" placeholder="例如：订单售后管理"></label><label>你想做什么？<span class="optional">选填</span><textarea v-model="brief" rows="5" placeholder="为谁设计？页面需要哪些内容、按钮和交互？"></textarea></label><p class="field-hint">{{ model.has_key ? '填写需求后将调用已配置的模型制作第一版。' : '尚未连接模型，将先创建骨架。你仍可使用属性面板直接编辑。' }}</p><p v-if="dialogError" class="form-error" role="alert">{{ dialogError }}</p><div class="dialog-actions"><button class="outline" type="button" :disabled="dialogBusy" @click="closeDialog">取消</button><button class="primary" :disabled="dialogBusy || !projectName.trim()"><LoaderCircle v-if="dialogBusy" class="spin" :size="16" />创建原型</button></div></form>
      <div v-else class="history-content"><p class="dialog-intro">退回历史会生成新版本，已有版本始终保留。</p><div v-if="undoCount" class="manual-summary"><SlidersHorizontal :size="16" />还有 {{ undoCount }} 步修改可撤销，使用顶部撤销按钮。</div><div class="version-list"><div v-for="v in [...(page?.versions || [])].reverse()" :key="v.version" class="version-row"><span class="version-node" :class="{ current: v.version === page?.version }"></span><div><b>v{{ v.version }}<span v-if="v.version === page?.version" class="current-badge">当前基础版本</span></b><p>{{ v.reason }}</p><time>{{ formatTime(v.created_at) }}</time></div><button class="outline" :disabled="dialogBusy || (v.version === page?.version && !undoCount)" @click="restore(v.version)">退回</button></div></div><p v-if="dialogError" class="form-error" role="alert">{{ dialogError }}</p></div>
    </dialog>
    <div v-if="backendStale" class="stale-banner" role="alert"><AlertCircle :size="15" /><span>后台服务还在跑旧代码，新功能可能用不了：关掉原型工坊的终端窗口，再双击「启动原型工坊」重启一下。</span><button type="button" class="icon-button" aria-label="知道了" @click="backendStale = false"><X :size="13" /></button></div>
    <div v-if="notice" class="toast" role="status"><Check :size="16" />{{ notice }}</div>
  </div>
</template>
