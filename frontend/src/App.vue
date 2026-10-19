<script setup>
// 整个工作台的外壳：放共享的状态（项目、页面、选中、预览……）和几个基础动作（请求、刷新、换项目、快捷键）。
// 各块功能在 composables/ 里，按功能分文件；它们和界面组件共用同一个 studio 对象（provide 出去，名字不变）。
// 一个功能要用另一个功能的函数时写 s.xxx：调用的时候才去取，几块之间不用管谁先建好
import { computed, nextTick, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { PanelsTopLeft, Plus, Upload, X, Hand, Undo2, Check, LoaderCircle, AlertCircle, Braces, Copy, Pencil } from 'lucide-vue-next'
import { MessageCircle, Redo2, PenLine } from 'lucide-vue-next'
import ExpandBoard from './components/expand/ExpandBoard.vue'
import AppHeader from './components/layout/AppHeader.vue'
import ConversationPanel from './components/layout/ConversationPanel.vue'
import InspectorPanel from './components/layout/InspectorPanel.vue'
import StudioDialog from './components/layout/StudioDialog.vue'
import { previewMessage, PREVIEW_SANDBOX } from './lib/previewMessage.js'
import { preparePreviewDocument } from './lib/previewDocument.js'
import { responseError } from './lib/streamAgent.js'
import { t, dateLocale, locale } from './lib/i18n.js'
import { usePresent } from './composables/usePresent.js'
import { useDrawing } from './composables/useDrawing.js'
import { useBoard } from './composables/useBoard.js'
import { usePreviewBridge } from './composables/usePreviewBridge.js'
import { useCommit } from './composables/useCommit.js'
import { useAgentRun } from './composables/useAgentRun.js'
import { useDialogs } from './composables/useDialogs.js'
import { useImages } from './composables/useImages.js'
import { useExport } from './composables/useExport.js'

// ---------- 共享状态 ----------
const projects = ref([]), project = ref(null), pageId = ref('')
const sourceInfo = ref({ source: '', hash: '', tokens: {}, defaults: {}, regions: [] })
const model = ref({ model: '', base_url: '', has_key: false, profiles: [] })
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
const codeRegion = ref('all'), codeCopied = ref(false), runtimeErrors = ref([]), recentClicks = ref([]), previewRoute = ref('')
const imageInput = ref(null), reference = ref(null)
const runs = ref([]), canvasWidth = ref(0), previewScroll = ref(null), pendingHighlights = ref([]), savedAt = ref('')
const validationDetails = ref(''), composerIntent = ref('auto'), previewHash = ref('')
const previewOwner = ref('')   // 当前预览源码属于哪个「项目:页面」——切项目时源码还没换完，不能拿旧源码去展开
// 展开视图：把这一页的弹窗铺开看；点卡片后在预览里复现打开路径
const moreMenu = ref(null)
const cardPatch = ref(null)
const boardMounted = ref(false)   // 展开第一次打开后就一直留着，卡片不用每次重新载入
const boardOpen = ref(false), boardFocus = ref(null), boardRoute = ref(''), pendingReplay = ref(null), openedModal = ref(null)
// 评论：写在右侧，存成一条意见（攒几条一起交给 AI），或者直接发给 AI
const commentDraft = ref('')
let toastTimer, loadSequence = 0, reloadNonce = 0

const currentRuns = computed(() => runs.value.filter(r => r.pageId === pageId.value && r.projectId === project.value?.id && !['complete', 'dismissed'].includes(r.status)))
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
// 选中的东西只能交给 AI 改（弹窗里的、脚本生成的、多选的），右侧换成「位置 + 内容 + 写需求」
const aiOnly = computed(() => !!selected.value && !!inspection.value && !inspection.value.editable && !dynEdit.value)
const selectionPlace = computed(() => {
  const target = selected.value
  if (!target) return ''
  if (target.place) return target.place
  return target.modal ? `${page.value?.title || ''} › ${target.modal}` : ''
})

// ---------- 基础动作 ----------
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
// 让预览一定重新载入：srcdoc 结尾换一个编号，内容一样 iframe 也会重载
function forceReload(html) { return html.replace(/\n<!-- pa-open \d+ -->$/, '') + `\n<!-- pa-open ${++reloadNonce} -->` }
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
  if (value === 'present') { s.startPresent(); return }
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
const shotUrl = a => `/api/projects/${project.value?.id}/shots/${a.id}`
// 评论气泡只在评论模式里钉在页面上；浏览、编辑、演示时收起来，不挡视线（和 Claude Design 一样）
const visiblePins = () => (tool.value === 'comment' && !s.presenting.value ? annotations.value : [])
watch(tool, value => {
  if (value !== 'comment' && s.drawing.value) s.drawClear()
  send({ type: 'PA_RENDER_MARKERS', annotations: visiblePins() }); send({ type: 'PA_SET_DRAG', enabled: value === 'comment' }) })
function clearSelectionOnly() { selected.value = null; inspection.value = null; note.value = ''; textValue.value = ''; send({ type: 'PA_SELECT', selector: '' }) }
function closeSelection() { clearSelectionOnly(); if (!keepInspector.value) rightOpen.value = false }
function hideGuide() { showGuide.value = false; localStorage.setItem('pf-hide-guide', 'true') }
// 选中的东西在弹窗里时，告诉 AI 是哪个弹窗、怎么点开的——不然它只能满文件搜按钮文字
function modalContext(target) {
  if (!target) return {}
  const ctx = {}
  const title = target.modal || target.targets?.find(x => x.modal)?.modal || ''
  const trail = target.trail || (openedModal.value?.title === title ? openedModal.value.trail : '')
  if (title) Object.assign(ctx, { in_modal: title, modal_trail: trail })
  if (target.viewKind === 'subpage') Object.assign(ctx, { in_subpage: target.viewTitle, modal_trail: trail })
  if (target.card?.route != null) ctx.view_route = target.card.route
  return ctx
}
function elementLabel(target) { const kinds = { button: '按钮', input: '输入框', textarea: '输入框', h1: '标题', h2: '标题', p: '文字', a: '链接' }; return target?.kind === 'region' ? t('已选中 {0} 个元素', [target.targets.length]) : `${target?.text?.slice(0, 22) || t('选中')} · ${t(kinds[target?.tag] || '区域')}` }
function preparePreview(html) {
  let saved = {}
  try { saved = JSON.parse(localStorage.getItem(runtimeKey()) || '{}') } catch {}
  return preparePreviewDocument(html, { stored: saved, route: previewRoute.value, scroll: previewScroll.value })
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

// ---------- 项目和页面 ----------
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
async function openManagedProject(id) { s.closeDialog(); await chooseProject(id) }
async function upload(event) {
  const file = event.target.files?.[0]; if (!file || locked.value) return
  loading.value = true; error.value = ''
  try {
    const data = new FormData(); data.append('file', file); data.append('name', file.name.replace(/\.(html?|zip)$/i, ''))
    const result = await api('/api/projects/upload', { method: 'POST', body: data })
    loading.value = false; await loadProjects(result.id); toast('原型已导入，可以直接点选修改')
  } catch (e) { error.value = e.message } finally { loading.value = false; event.target.value = '' }
}

// ---------- 评论、面板 ----------
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
// 属性面板的图层列表：点一下换成选那一层，移上去在页面上框出来
function selectLayer(selector) { if (selector) send({ type: 'PA_SELECT', selector }) }
function hoverLayer(selector) { send({ type: 'PA_HOVER', selector: selector || '' }) }
// 对话和属性 / 评论共用左侧一栏（和 Claude Design 一样），用顶上的页签切换
function openLeft() { leftOpen.value = true; rightOpen.value = false }
function showChat() { leftOpen.value = true; rightOpen.value = false }
function showPanel() { rightOpen.value = true }
function toggleRight() { rightOpen.value = !rightOpen.value; if (rightOpen.value && window.innerWidth <= 960) leftOpen.value = false }
async function toAI() { leftOpen.value = true; rightOpen.value = false; await nextTick(); composer.value?.focus() }
async function copySource() { try { await navigator.clipboard.writeText(codeText.value); codeCopied.value = true; setTimeout(() => codeCopied.value = false, 1800) } catch { toast('请选中源码后复制') } }
// 一个格式器反复用：每次 toLocaleString 都新建一个，聊天长了以后每敲一个字都要重算几百次
const timeFormats = {}
function formatTime(value) { const d = new Date(value); if (isNaN(d)) return ''; const id = locale.value; timeFormats[id] ||= new Intl.DateTimeFormat(dateLocale(), { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }); return timeFormats[id].format(d) }
function keydown(event) {
  if (dialog.value?.open) return
  const key = event.key.toLowerCase(), command = event.metaKey || event.ctrlKey
  const editing = event.target?.closest?.('input,textarea,select,[contenteditable=true]')
  if (command && key === 'enter') { event.preventDefault?.(); s.runAgent(); return }
  if (editing || event.altKey) return
  if (command && key === 'z' && !event.shiftKey) { event.preventDefault?.(); s.undo(); return }
  if (command) return
  if (key === 'escape') { if (s.presenting.value) { s.stopPresent(); return } if (boardFocus.value != null) { boardFocus.value = null; return } if (boardOpen.value) { s.showPreview(); return } closeSelection(); setTool('browse') }
  if (s.presenting.value) return
  if (key === 'e' && page.value) { event.preventDefault?.(); s.toggleBoard(); return }
  const next = { h: 'browse', c: 'comment', b: 'comment', v: 'edit', p: 'present' }[key]
  if (next && page.value) { event.preventDefault?.(); setTool(next) }
}

// ---------- 拼起来 ----------
const s = {
  projects, project, pageId, sourceInfo, model, mode, view, device, keepInspector, leftOpen, rightOpen, showGuide, selected, inspection,
  textValue, note, input, busy, saving, loading, status, error, notice, pendingUser, pendingRef, lastResult, previewFrame, previewDoc,
  composer, chatBox, fileInput, dialog, dialogType, dialogBusy, dialogError, codeRegion, runtimeErrors, recentClicks, previewRoute,
  imageInput, reference, runs, canvasWidth, previewScroll, pendingHighlights, savedAt, validationDetails, composerIntent, previewHash,
  previewOwner, moreMenu, cardPatch, boardMounted, boardOpen, boardFocus, boardRoute, pendingReplay, openedModal, commentDraft,
  currentRuns, page, annotations, messages, locked, playing, dynEdit, canEdit, textEditable, undoCount, colors, aiOnly, selectionPlace,
  endpoint, runtimeKey, api, post, toast, send, forceReload, setMode, tool, TOOLS, setTool, shotUrl, visiblePins,
  clearSelectionOnly, closeSelection, hideGuide, modalContext, elementLabel, preparePreview, refresh, chooseProject, choosePage,
  loadProjects, filesChanged, openManagedProject, upload, saveNote, removeAnnotation, selectLayer, hoverLayer, openLeft, showChat,
  showPanel, toggleRight, toAI, formatTime, keydown,
}
Object.assign(s, usePresent(s))
Object.assign(s, useDrawing(s))
Object.assign(s, useBoard(s))
Object.assign(s, usePreviewBridge(s))
Object.assign(s, useCommit(s))
Object.assign(s, useAgentRun(s))
Object.assign(s, useDialogs(s))
Object.assign(s, useImages(s))
Object.assign(s, useExport(s))
// 模板里直接用到的
const { presenting, exitShown, peekExit, hideExitSoon, stopPresent, drawing, drawNote, drawBusy, drawInput, drawClear, drawSend, drawSave,
  openFromBoard, pickFromBoard, previewLoaded, onMessage, requestExport, openDialog } = s

watch(view, value => { if (value === 'preview' && previewDoc.value) previewDoc.value = preparePreview(previewDoc.value) })
watch(mode, () => send({ type: 'PA_SET_MODE', mode: mode.value }))
// 后台在跑的是旧代码（改过没重启）：页面是新的、接口是旧的，新功能会报「Method Not Allowed」。挂一条提示说清楚怎么办
const backendStale = ref(false)
async function checkBackend() {
  try { const h = await api('/api/health'); backendStale.value = h.packaged ? false : !h.code_epoch ? true : h.code_epoch > h.started_epoch + 1 } catch { /* 连不上另有提示 */ }
}
onMounted(checkBackend)
onMounted(async () => { window.addEventListener('message', onMessage); window.addEventListener('keydown', keydown); try { model.value = await api('/api/config'); await loadProjects(); if (!model.value.has_key && !model.value.profiles?.length) openDialog('settings') } catch (e) { error.value = e.message } })   // 第一次打开、一个模型都没绑：直接请他绑自己的
onUnmounted(() => { window.removeEventListener('message', onMessage); window.removeEventListener('keydown', keydown); clearTimeout(toastTimer) })

// 拆出去的界面块（AppHeader / ConversationPanel / InspectorPanel / StudioDialog）用到的状态和函数：按原名交给它们
provide('studio', s)
</script>

<template>
  <div class="studio" :class="{ presenting }">
    <div v-if="presenting" class="present-edge" @mouseenter="peekExit"></div>
    <button v-if="presenting" class="present-exit" :class="{ shown: exitShown }" @click="stopPresent" @mouseenter="peekExit" @mouseleave="hideExitSoon"><X :size="14" />{{ $t('退出演示') }} <kbd>Esc</kbd></button>
    <AppHeader />

    <main class="workspace" :class="{ 'side-closed': !leftOpen && !rightOpen }">
      <div v-if="(leftOpen || rightOpen)" class="mobile-scrim" @click="leftOpen = false; rightOpen = false"></div>
      <ConversationPanel />

      <section class="canvas-panel" :aria-label="$t('原型画布')">
        <div v-if="view === 'preview'" class="canvas" :class="device">

          <ExpandBoard v-if="boardMounted" :class="{ 'view-hidden': !boardOpen }" :aria-hidden="!boardOpen" v-model:focus="boardFocus" v-model:route="boardRoute" :notes="annotations" :patch="cardPatch" :page-name="page?.title" :selection="selected" :mode="mode" @open="openFromBoard" @select="pickFromBoard" @clear="closeSelection" @mode="setMode" @export="requestExport" />
          <div class="preview-shell" :class="{ 'is-selecting': mode !== 'interact', 'view-hidden': boardOpen }" :aria-hidden="boardOpen"><iframe v-if="previewDoc" ref="previewFrame" :title="$t('原型预览')" :srcdoc="previewDoc" :sandbox="PREVIEW_SANDBOX" @load="previewLoaded"></iframe><div v-else class="empty-canvas"><div class="empty-emblem"><PanelsTopLeft :size="30" :stroke-width="1.4" /></div><h1>{{ $t('给想法一个可操作的样子') }}</h1><p>{{ $t('从已有的 HTML 开始修改，') }}<br>{{ $t('或描述需求，让 AI 帮你搭建第一版。') }}</p><div><button class="primary" @click="openDialog('new')"><Plus :size="16" />{{ $t('新建原型') }}</button><button class="outline" @click="fileInput.click()"><Upload :size="16" />{{ $t('导入原型') }}</button></div><span>{{ $t('支持 HTML、包含多页面的 ZIP') }}</span></div><div v-if="drawing && tool === 'comment' && !boardOpen" class="draw-bar" @keydown.esc.stop="drawClear"><PenLine :size="15" /><input ref="drawInput" v-model="drawNote" maxlength="1000" :placeholder="$t('给画的 {0} 笔写一句说明，比如：这块改成卡片布局', [$t(drawing.count)])" :aria-label="$t('标记说明')" @keydown.enter.exact.prevent="drawSend" @keydown.meta.enter.prevent="drawSend"><button class="icon-button" :title="$t('撤销一笔')" :aria-label="$t('撤销一笔')" :disabled="!drawing.count || drawBusy" @click="send({ type: 'PA_DRAW_UNDO' })"><Undo2 :size="15" /></button><button class="icon-button" :title="$t('重做')" :aria-label="$t('重做')" :disabled="!drawing.redo || drawBusy" @click="send({ type: 'PA_DRAW_REDO' })"><Redo2 :size="15" /></button><button class="quiet" :disabled="drawBusy" @click="drawClear">{{ $t('取消') }}</button><button class="outline" :title="$t('先记下，攒几条一起改')" :disabled="drawBusy || locked || !drawNote.trim()" @click="drawSave">{{ $t('记下') }}</button><button class="primary" :title="$t('回车发送')" :disabled="drawBusy || locked || !drawNote.trim()" @click="drawSend"><LoaderCircle v-if="drawBusy" :size="14" class="spin" /><span v-else>{{ $t('发送') }}</span></button></div><div v-if="loading" class="loading-veil"><LoaderCircle class="spin" :size="25" /><span>{{ $t('正在加载原型…') }}</span></div></div>
          
        </div>
        <div v-else class="code-panel"><div class="code-toolbar"><Braces :size="15" /><select :aria-label="$t('源码区域')" v-model="codeRegion"><option value="all">{{ $t('完整文件 · 只读') }}</option><option v-for="region in sourceInfo.regions" :key="region.name" :value="region.name">{{ $t(region.label || '自定义区域') }}</option></select><span>{{ $t('{0} 行', [codeText.split('\n').length]) }}</span><button class="quiet" @click="copySource"><Check v-if="codeCopied" :size="14" /><Copy v-else :size="14" />{{ codeCopied ? $t('已复制') : $t('复制') }}</button></div><div class="source-scroll"><pre class="line-numbers" aria-hidden="true">{{ lineNumbers }}</pre><pre class="source-code"><code>{{ codeText }}</code></pre></div></div>
        <div v-if="error" class="error-banner" role="alert"><AlertCircle :size="16" /><span>{{ $t(error) }}</span><button class="icon-button" :aria-label="$t('关闭错误提示')" @click="error = ''"><X :size="14" /></button></div>
        <footer class="canvas-status"><span v-if="page" class="status-version">{{ $t('v{0} · {1} 次修改', [$t(page.version), page.modification_count || 0]) }}</span><span :title="validationDetails + (savedAt ? ' · ' + savedAt : '')"><LoaderCircle v-if="locked" :size="13" class="spin" /><Check v-else :size="13" />{{ $t(status) }}</span><details v-if="runtimeErrors.length" class="runtime-warning"><summary><AlertCircle :size="13" />{{ $t('{0} 条运行提示', [$t(runtimeErrors.length)]) }}</summary><div><p v-for="warning in runtimeErrors" :key="warning">{{ $t(warning) }}</p></div></details></footer>
      </section>

      <InspectorPanel />
    </main>

    <StudioDialog />
    <div v-if="backendStale" class="stale-banner" role="alert"><AlertCircle :size="15" /><span>{{ $t('后台服务还在跑旧代码，新功能可能用不了：关掉原型工坊的终端窗口，再双击「启动原型工坊」重启一下。') }}</span><button type="button" class="icon-button" :aria-label="$t('知道了')" @click="backendStale = false"><X :size="13" /></button></div>
    <div v-if="notice" class="toast" role="status"><Check :size="16" />{{ $t(notice) }}</div>
  </div>
</template>
