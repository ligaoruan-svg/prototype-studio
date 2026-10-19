// 弹窗：新建原型（含选风格）、设计规范（风格 / 规范正文 / 组件库 / 记忆）、模型设置，以及输入框下面的换模型
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { t } from '../lib/i18n.js'

export function useDialogs(s) {
  const { dialog, dialogType, dialogBusy, dialogError, project, model, keepInspector, input, api, post, toast } = s
  const specDraft = ref(''), specSaved = ref(''), specInput = ref(null), specNotice = ref('')
  const componentList = ref([]), componentInput = ref(null), specTab = ref('spec')
  const memoryCount = ref(0), skillList = ref([])
  const configDraft = ref({ base_url: '', model: '', api_key: '' }), projectName = ref(''), brief = ref('')
  const fileManagerRevision = ref(0)

  // ---------- 换模型 ----------
  // 输入框下面一点就能换模型：保存过的每一套（地址 + 模型 + 密钥）都在这里，不用每次进设置重填
  const modelMenu = ref(false), switchingModel = ref(false)
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
  // ---------- 风格 ----------
  // 新建原型时选一套，之后在「设计规范 → 风格」里能换。上次新建选的那套记着，下次默认还是它
  const DEFAULT_STYLE = 'builtin:简洁后台'
  const styleList = ref({ builtin: [], mine: [] }), styleInput = ref(null)
  const newStyle = ref((() => { try { return localStorage.getItem('pa-new-style') || DEFAULT_STYLE } catch { return DEFAULT_STYLE } })())
  const styleValues = () => [...styleList.value.builtin.map(st => 'builtin:' + st.folder), ...styleList.value.mine.map(st => 'mine:' + st.folder), 'none']
  async function loadStyles() {
    try { styleList.value = await api('/api/styles') } catch { return }
    if (!styleValues().includes(newStyle.value)) newStyle.value = styleValues().includes(DEFAULT_STYLE) ? DEFAULT_STYLE : styleValues()[0]
  }
  // 「导入风格」：和组件库里导入 skill 包是同一个接口；装好就选上它
  async function importStyle(event) {
    const file = event.target.files?.[0]; event.target.value = ''
    if (!file) return
    dialogBusy.value = true; dialogError.value = ''; specNotice.value = ''
    try {
      const data = new FormData(); data.append('file', file); data.append('name', file.name)
      const result = await api('/api/components', { method: 'POST', body: data })
      await refreshShelf()
      await loadStyles()
      if (result.kind !== 'skill') { specNotice.value = '这个包里没有 SKILL.md，按单个组件装上了，不能当风格用'; return }
      const value = 'mine:' + result.name
      const item = styleList.value.mine.find(st => st.folder === result.name)
      specNotice.value = `已导入「${result.name}」` + (item && !item.has_shell ? '。它没有页面外壳，只当规矩用，不能一键起页面' : '')
      if (dialogType.value === 'new') newStyle.value = value
      else if (project.value) { dialogBusy.value = false; await changeStyle(value) }
    } catch (e) { dialogError.value = e.message } finally { dialogBusy.value = false }
  }
  async function changeStyle(value) {
    if (!project.value) return
    dialogBusy.value = true; dialogError.value = ''; specNotice.value = ''
    try {
      const result = await api(`/api/projects/${project.value.id}/style`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ style: value }) })
      project.value = { ...project.value, style: value }
      const item = [...styleList.value.builtin, ...styleList.value.mine].find(st => value.endsWith(':' + st.folder))
      specNotice.value = value === 'none' ? '已改成不选风格：之后只按设计规范来' : `已换成「${t(item?.name || value)}」：之后新做的页面和修改按这套来`
      // 还没写内容的页面后台已经换成新风格的样子了，预览跟着刷新
      if (result.swapped) { await s.refresh(false); specNotice.value += '；还是空的页面已经换成新风格的样子' }
    } catch (e) { dialogError.value = e.message } finally { dialogBusy.value = false }
  }

  // ---------- 设计规范、组件库 ----------
  async function refreshShelf() {
    const shelf = await api('/api/components')
    componentList.value = shelf.components; skillList.value = shelf.skills || []
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
      await refreshShelf()
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
  async function removeSkill(name) {
    dialogBusy.value = true; dialogError.value = ''
    try {
      await api('/api/skills/' + encodeURIComponent(name), { method: 'DELETE' })
      await refreshShelf()
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

  // ---------- 记忆 ----------
  watch(() => project.value?.id, id => { memoryCount.value = 0; if (id) refreshMemoryCount() })
  async function openMemory() { await openDialog('spec'); specTab.value = 'memory' }
  async function refreshMemoryCount() { const id = project.value?.id; if (!id) return; try { const m = await api(`/api/projects/${id}/memory`); if (project.value?.id !== id) return; memoryCount.value = (m.project?.memory?.length || 0) + (m.global?.memory?.length || 0) } catch { /* 读不到就不显示数 */ } }
  async function forgetFromCard(id) {
    try { await api(`/api/projects/${project.value.id}/memory/${id}`, { method: 'DELETE' }); toast('已忘掉这条约定') } catch (e) { toast(e.message) }
  }

  // ---------- 打开 / 关闭 ----------
  async function openDialog(type) {
    dialogType.value = type; dialogError.value = ''
    if (type === 'settings') configDraft.value = { base_url: model.value.base_url || 'https://api.deepseek.com', model: model.value.model || 'deepseek-flash', api_key: '', supports_vision: !!model.value.supports_vision, max_tokens: model.value.max_tokens || 32000, context_budget: model.value.context_budget || 200000, max_rounds: model.value.max_rounds || 24, stream: model.value.stream !== false, keepInspector: keepInspector.value }
    if (type === 'new') { projectName.value = ''; brief.value = ''; specNotice.value = ''; await loadStyles() }
    if (type === 'files') fileManagerRevision.value++
    if (type === 'spec') {
      specNotice.value = ''; specTab.value = 'spec'
      try {
        await loadStyles()
        specDraft.value = specSaved.value = (await api('/api/design-spec')).content
        await refreshShelf()
        if (project.value) { const m = await api(`/api/projects/${project.value.id}/memory`); memoryCount.value = (m.project?.memory?.length || 0) + (m.global?.memory?.length || 0) }
      } catch (e) { dialogError.value = e.message }
    }
    await nextTick(); dialog.value.showModal()
  }
  function closeDialog() { if (!dialogBusy.value) { dialog.value.close(); configDraft.value.api_key = '' } }
  async function createProject() {
    if (!projectName.value.trim()) return
    dialogBusy.value = true; dialogError.value = ''
    try {
      const result = await post('/api/projects/new', { name: projectName.value, style: newStyle.value })
      try { localStorage.setItem('pa-new-style', newStyle.value) } catch { /* 记不住就算了 */ }
      await s.loadProjects(result.id)
      input.value = brief.value; dialog.value.close(); await s.toAI(); toast('原型骨架已创建')
      if (brief.value.trim() && model.value.has_key) { dialogBusy.value = false; await s.runAgent('', '', { intent: 'edit' }) }
    } catch (e) { dialogError.value = e.message; } finally { dialogBusy.value = false }
  }
  return { specDraft, specSaved, specInput, specNotice, componentList, componentInput, specTab, memoryCount, skillList, configDraft,
    projectName, brief, fileManagerRevision, modelMenu, switchingModel, switchModel,
    styleList, styleInput, newStyle, importStyle, changeStyle, saveSpec, addComponent, removeSkill, removeComponent, importSpecTokens,
    openMemory, refreshMemoryCount, forgetFromCard, openDialog, closeDialog, createProject }
}
