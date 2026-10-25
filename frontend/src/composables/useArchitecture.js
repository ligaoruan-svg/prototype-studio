// 架构是原型的镜子：左边对话里 AI 改完原型，页面树跟着从原型读一遍（不用 AI，几秒就好）；
// 你在树里改了（加页面、改字段……），底下记着还有几处没同步，点「同步到原型」只把这几处交给左边对话里的 AI 去改。
// 架构存在后台（每个项目一份），上次同步时的样子也存着，和它一比就知道改了什么
import { computed, ref, watch } from 'vue'
import { CHILD_TYPES, addChild, addSibling, clone, diffNodes, emptyArchitecture, findNode, impactOf, moveNode, removeNode, syncMessage } from '../lib/architecture.js'
import { expand, expandAll } from '../lib/expandStore.js'

export function useArchitecture(s) {
  const { project, archOpen, boardOpen, boardFocus, view, api, toast, model, dialogError, sourceInfo, previewRoute, runs } = s
  const arch = ref(null), archIssues = ref([]), archCounts = ref({}), archSynced = ref(null)
  const archMounted = ref(false), archLoaded = ref(''), archBusy = ref(''), archError = ref('')
  const archView = ref('tree'), archSelected = ref(null), archShowDesc = ref(true), archQuery = ref('')
  const archShowFields = ref(false)   // 页面树里弹窗、表格默认只露一行字段摘要；勾上就全部画成小表单
  const archRemoved = ref(null)   // 刚删掉的：底部「撤销」条
  const archOutline = ref(''), archOutlineDirty = ref(false)   // 用文字编辑：手动编的文字；没改过就跟着页面树变
  const archRenaming = ref('')    // 页面树里正在原地改名的节点
  const archReadAt = ref(0)       // 上次从原型读的时间
  // 上次同步时加的：同步完从原型读回来，要是原型里没有（AI 没做出来），提醒一声、能放回去再同步
  let lastSync = null
  const archMissing = ref(null)   // { names, tree }
  // 页面树一层一层看：默认只展开到菜单页；点一张卡片就往下展开一层，同一层别的自动收起（一次只看一个页面）
  const archLevel = ref(2)        // 1 只看模块 · 2 到菜单页 · 3 到页签 · 99 全部
  const archExpand = ref({})      // 手动展开 / 收起过的：id → true / false（换层级时清掉）
  const history = ref([])         // 撤销用的快照，最多 60 份
  let saveTimer = null, removedTimer = null, saving = Promise.resolve()
  // 还没同步到原型的改动：和上次同步时的树比。从来没同步过（自己从零编的）就整棵都算
  const archChanges = computed(() => arch.value ? diffNodes(archSynced.value || [], arch.value.nodes) : [])

  const url = () => `/api/projects/${project.value.id}/architecture`
  function apply(bundle, replace = true) {
    if (replace) arch.value = bundle.architecture
    if (!archOutlineDirty.value || replace) { archOutline.value = bundle.outline || ''; archOutlineDirty.value = false }
    archIssues.value = bundle.issues || []; archCounts.value = bundle.counts || {}
    if ('synced' in bundle) archSynced.value = bundle.synced
  }
  async function loadArch(force = false) {
    const pid = project.value?.id
    if (!pid || (!force && archLoaded.value === pid)) return
    archError.value = ''
    try {
      const bundle = await api(`/api/projects/${pid}/architecture`)
      if (project.value?.id !== pid) return
      apply(bundle); archLoaded.value = pid; history.value = []; archSelected.value = null
    } catch (e) { archError.value = e.message }
  }
  // 换项目：架构跟着换；看着架构的话马上读新的
  watch(() => project.value?.id, () => { archLoaded.value = ''; arch.value = null; archSynced.value = null; archIssues.value = []; if (archOpen.value) showArch() })

  async function showArch() {
    if (!project.value) return
    archMounted.value = true; archOpen.value = true
    boardOpen.value = false; boardFocus.value = null; view.value = 'preview'
    await loadArch()
    readPrototype()
  }
  function hideArch() { archOpen.value = false }

  // ---------- 保存、撤销 ----------
  function saveNow() {
    clearTimeout(saveTimer); saveTimer = null
    if (!arch.value || !project.value) return saving
    const pid = project.value.id, body = JSON.stringify({ architecture: arch.value })
    archBusy.value ||= 'saving'
    saving = saving.then(() => api(`/api/projects/${pid}/architecture`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body }))
      .then(bundle => { if (project.value?.id === pid) apply(bundle, false) })
      .catch(e => { archError.value = e.message })
      .finally(() => { if (archBusy.value === 'saving') archBusy.value = '' })
    return saving
  }
  function scheduleSave() { clearTimeout(saveTimer); saveTimer = setTimeout(saveNow, 500) }
  // 改之前留一份底：同样的内容不重复留（打字时只在开始改这一格时留一次）
  function snapshot() {
    if (!arch.value) return
    const text = JSON.stringify(arch.value)
    if (history.value[history.value.length - 1] !== text) history.value = [...history.value.slice(-59), text]
  }
  function change(mutate) { snapshot(); const out = mutate(arch.value); scheduleSave(); return out }
  function dirty() { scheduleSave() }
  function undoArch() {
    const last = history.value[history.value.length - 1]
    if (!last) return
    history.value = history.value.slice(0, -1)
    arch.value = JSON.parse(last); archRemoved.value = null
    if (archSelected.value && !selectedItem()) archSelected.value = null
    scheduleSave()
  }

  // ---------- 选中、增删改 ----------
  function select(kind, id) {
    archSelected.value = kind ? { kind, id } : null
    // 从改动清单跳过来的：把它上面几层都展开，不然看不到
    if (kind === 'node' && arch.value) {
      const hit = findNode(arch.value, id)
      if (hit?.parents.length) archExpand.value = { ...archExpand.value, ...Object.fromEntries(hit.parents.map(p => [p.id, true])) }
    }
  }
  function nodeOpen(node, depth) {
    if (node.id in archExpand.value) return archExpand.value[node.id]
    return depth + 1 < archLevel.value
  }
  // 展开一个就把同一层其它展开的收起来：屏幕上只留一条线，看得清
  function openNode(node, depth, siblings, open = !nodeOpen(node, depth)) {
    const next = { ...archExpand.value, [node.id]: open }
    if (open) for (const sib of siblings || []) if (sib.id !== node.id && (sib.children || []).length && nodeOpen(sib, depth)) next[sib.id] = false
    archExpand.value = next
  }
  function setLevel(level) { archLevel.value = level; archExpand.value = {} }
  function selectedItem() {
    const sel = archSelected.value, a = arch.value
    if (!sel || !a) return null
    if (sel.kind === 'root') return a
    if (sel.kind === 'node') return findNode(a, sel.id)?.node || null
    return null
  }
  // 加出来的直接进入改名：不然名字都叫「新菜单页」，再按回车又多出一个同名的
  function archAdd(parentId, type) { const node = change(a => addChild(a, parentId, type)); select('node', node.id); archRenaming.value = node.id; return node }
  function archSibling(id) { const node = change(a => addSibling(a, id)); if (node) { select('node', node.id); archRenaming.value = node.id } }
  function archMove(id, delta) { change(a => moveNode(a, id, delta)) }
  function archToggle(id) { const node = findNode(arch.value, id)?.node; if (node) change(() => { node.collapsed = !node.collapsed }) }
  function archRemove(id) {
    const node = findNode(arch.value, id)?.node
    if (!node) return
    const impact = impactOf(arch.value, id)
    change(a => removeNode(a, id))
    if (archSelected.value?.id === id) archSelected.value = null
    archRemoved.value = { name: node.name, impact }
    clearTimeout(removedTimer); removedTimer = setTimeout(() => { archRemoved.value = null }, 8000)
  }
  // 自己从零编：在页面树里一个个加，或者用文字写；编好了点「同步到原型」让 AI 做出来
  function startBlank(where = 'tree') {
    arch.value = emptyArchitecture(project.value?.name || ''); history.value = []
    if (where === 'outline') { arch.value.nodes = []; archView.value = 'outline' } else { archView.value = 'tree'; select('node', arch.value.nodes[0].id); archRenaming.value = arch.value.nodes[0].id }
    saveNow()
  }
  // 大纲改完「应用」：整份读回来，路径没变的节点沿用原来的编号
  async function applyOutline(text) {
    if (!project.value) return
    await saveNow()
    snapshot()
    try { apply(await s.post(`${url()}/outline`, { text })); toast('大纲已应用到架构') } catch (e) { archError.value = e.message }
  }
  // 粘贴：Excel 复制的功能清单，或一段大纲；追加时同名的并到一起
  async function importText(text, mode = 'append') {
    if (!project.value || !text.trim()) return false
    await saveNow()
    snapshot()
    try { apply(await s.post(`${url()}/import`, { text, mode })); archView.value = 'tree'; toast(mode === 'replace' ? '已替换成粘贴的内容' : '已加进架构，同名的并到了一起'); return true }
    catch (e) { archError.value = e.message; return false }
  }
  // ---------- 和原型对齐 ----------
  const hasPrototype = () => (sourceInfo.value.source || '').length > 400
  // 从原型读：展开图 → 页面树。树里有没同步的改动就不读（会冲掉）；force 是「放弃改动，照原型重读」
  async function readPrototype({ force = false } = {}) {
    if (!project.value || !arch.value && !hasPrototype() || archBusy.value === 'sync') return
    if (!force && arch.value && archSynced.value && archChanges.value.length) return
    await saveNow()
    archBusy.value ||= 'read'
    try {
      const bundle = await s.post(`${url()}/refresh`, { page_id: s.pageId.value, force })
      if (bundle.refreshed) {
        const before = arch.value ? JSON.stringify(arch.value) : null
        apply(bundle); archReadAt.value = Date.now()
        checkMissing()
        if (force && before) history.value = [...history.value.slice(-59), before]
        if (archSelected.value && !selectedItem()) archSelected.value = null
      } else if (bundle.reason === 'no_expand' && hasPrototype() && !expand.batch) {
        expandAll(previewRoute.value || '')   // 还没展开过：先把原型的每个页面点一遍，展开完这里自动读
      }
    } catch (e) { archError.value = e.message } finally { if (archBusy.value === 'read') archBusy.value = '' }
  }
  const expandIdle = () => !expand.discovering && !Object.keys(expand.jobs).length && !expand.queued.length
  // 左边 AI 改完原型，展开图在后台同步；它一变就重读一遍（停手 1.5 秒后，免得一页一页地闪）
  let readTimer = null
  watch(() => [expand.scope, expand.routes.map(r => r.hash).join(','), Object.entries(expand.entries).map(([r, e]) => r + e.hash).join(','), expandIdle()].join('|'), () => {
    if (!archOpen.value) return
    clearTimeout(readTimer); readTimer = setTimeout(() => readPrototype(), 1500)
  })
  const reading = computed(() => archBusy.value === 'read' || expand.discovering || (archOpen.value && expand.batch && (Object.keys(expand.jobs).length > 0 || expand.queued.length > 0)))

  // 同步到原型：只把改了的那几处交给左边对话里的 AI；改完了，现在的树就是原型的样子
  function needKey() {
    if (model.value.has_key) return false
    s.openDialog('settings'); dialogError.value = '请先配置模型密钥。'; return true
  }
  async function syncToPrototype() {
    const changes = archChanges.value
    if (!arch.value || !changes.length || s.locked.value || needKey()) return
    await saveNow()
    if (archError.value) return
    archBusy.value = 'sync'
    const count = runs.value.length
    try {
      await s.runAgent(syncMessage(changes), '', { intent: 'edit', includeAnnotations: false, selection: null, architecture: true })
      const run = runs.value[count]
      if (run?.status === 'complete' && run.result?.changed) {
        lastSync = { at: Date.now(), adds: changes.filter(c => c.kind === 'add'), tree: clone(arch.value.nodes) }
        archMissing.value = null
        apply(await s.post(`${url()}/synced`, {}), false)
        toast('已同步到原型')
      } else if (run?.status === 'complete') toast('AI 没有改动原型，改动还留着，可以再同步一次')
    } catch (e) { archError.value = e.message } finally { archBusy.value = '' }
  }
  // 同步完读回来：加的东西原型里有没有。展开还在跑（新页面还没认出来）就先不下结论，等跑完再看
  function checkMissing() {
    if (!lastSync || !arch.value) return
    const missing = lastSync.adds.filter(c => !findNode(arch.value, c.id))
    if (!missing.length) { lastSync = null; archMissing.value = null; return }
    if (!expandIdle() && Date.now() - lastSync.at < 180_000) return
    archMissing.value = { names: missing.map(c => c.node.name), tree: lastSync.tree }
    lastSync = null
  }
  // 放回去：回到同步时的那棵树，没做出来的又变成「还没同步」，再点一次同步
  function restoreMissing() {
    const tree = archMissing.value?.tree
    archMissing.value = null
    if (tree) change(a => { a.nodes = clone(tree) })
  }
  // 不要这些改动了：照原型重读一遍（能撤销）
  function discardChanges() { return readPrototype({ force: true }) }

  // 键盘：选中页面树的节点后，回车加同级、Tab 加子项、Delete 删除、F2 改名；⌘Z 撤销架构里的改动
  function archKey(event) {
    const key = event.key, command = event.metaKey || event.ctrlKey
    if (command && key.toLowerCase() === 'z' && !event.shiftKey) { event.preventDefault?.(); undoArch(); return true }
    const sel = archSelected.value
    if (archView.value !== 'tree' || sel?.kind !== 'node' || command) return false
    const node = findNode(arch.value, sel.id)?.node
    if (!node) return false
    if (key === 'Enter') { event.preventDefault?.(); archSibling(node.id); return true }
    if (key === 'Tab') {
      event.preventDefault?.()
      const type = (CHILD_TYPES[node.type] || [])[0]
      if (type) archAdd(node.id, type)
      return true
    }
    if (key === 'Delete' || key === 'Backspace') { event.preventDefault?.(); archRemove(node.id); return true }
    if (key === 'F2') { event.preventDefault?.(); archRenaming.value = node.id; return true }
    return false
  }
  function renameNode(id, name) {
    archRenaming.value = ''
    const node = findNode(arch.value, id)?.node
    if (node && name.trim() && name.trim() !== node.name) change(() => { node.name = name.trim() })
  }

  return { arch, archIssues, archCounts, archSynced, archChanges, archMounted, archBusy, archError, archView, archSelected, archShowDesc, archShowFields, archQuery,
    archRemoved, archHistory: history, loadArch, showArch, hideArch, saveArch: saveNow, archSnapshot: snapshot, archDirty: dirty, archChange: change,
    archLevel, archExpand, nodeOpen, openNode, setLevel, archReadAt, archReading: reading,
    undoArch, archSelect: select, archSelectedItem: selectedItem, archAdd, archSibling, archMove, archToggle, archRemove,
    startBlank, readPrototype, syncToPrototype, discardChanges, archMissing, restoreMissing,
    archOutline, archOutlineDirty, archRenaming, applyOutline, importText, archKey, renameNode,
    cloneArch: () => clone(arch.value) }
}
