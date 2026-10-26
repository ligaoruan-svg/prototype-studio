// 架构：一块画布，上面是这个原型的页面树。平时不用；点顶上的「架构」才打开，打开时对话多一个「架构」模式。
// - 导入过原型的：打开就从原型读（和「展开」一样把每页点一遍），只合并不冲掉——原型里新做的补进来，画布上规划的留着
// - 没有原型的：画布是空的，自己加，或者在「架构」模式里跟 AI 说
// - 「架构」模式里 AI 只改画布，不碰原型代码；切回「自动」「直接改」时 AI 拿画布当背景做页面
import { computed, ref, watch } from 'vue'
import { CHILD_TYPES, addChild, addSibling, changeLabel, changesUnder, checkMessage, clone, diffNodes, emptyArchitecture, findNode, impactOf, moveNode, pendingChanges, removeNode, syncMessage } from '../lib/architecture.js'
import { expand, expandAll, isFresh } from '../lib/expandStore.js'

export function useArchitecture(s) {
  const { project, archOpen, boardOpen, boardFocus, view, api, sourceInfo, previewRoute, composerIntent } = s
  const arch = ref(null), archIssues = ref([]), archCounts = ref({})
  const archBase = ref(null)       // 上次从原型读出来的样子；画布和它比，多做的就是还没同步到原型的
  const archMounted = ref(false), archLoaded = ref(''), archBusy = ref(''), archError = ref('')
  const archSelected = ref(null), archShowDesc = ref(true), archQuery = ref('')
  const archShowFields = ref(false)   // 弹窗、表格默认只露一行字段摘要，点开画成小表单
  const archRemoved = ref(null)   // 刚删掉的：底部「撤销」条
  const archRenaming = ref('')    // 正在原地改名的节点
  const archFlash = ref(new Set())  // AI 刚改到的节点：高亮几秒
  // 页面树一层一层看：默认展开到菜单页；点一张卡片往下展开一层，同一层别的自动收起
  const archLevel = ref(2)
  const archExpand = ref({})      // 手动展开 / 收起过的：id → true / false
  const history = ref([])         // 撤销用的快照，最多 60 份
  let saveTimer = null, removedTimer = null, flashTimer = null, saving = Promise.resolve()

  const url = () => `/api/projects/${project.value.id}/architecture`
  function apply(bundle, replace = true) {
    if (replace) arch.value = bundle.architecture
    archIssues.value = bundle.issues || []; archCounts.value = bundle.counts || {}
    if ('base' in bundle) archBase.value = bundle.base
  }
  async function loadArch(force = false) {
    const pid = project.value?.id
    if (!pid || (!force && archLoaded.value === pid)) return
    archError.value = ''
    try {
      const bundle = await api(`/api/projects/${pid}/architecture`)
      if (project.value?.id !== pid) return
      apply(bundle); archLoaded.value = pid
      if (!force) { history.value = []; archSelected.value = null }
    } catch (e) { archError.value = e.message }
  }
  // 换项目：画布跟着换；开着的话马上读新的
  watch(() => project.value?.id, () => { archLoaded.value = ''; arch.value = null; archBase.value = null; archIssues.value = []; history.value = []; if (archOpen.value) showArch() })

  async function showArch() {
    if (!project.value) return
    archMounted.value = true; archOpen.value = true
    boardOpen.value = false; boardFocus.value = null; view.value = 'preview'
    await loadArch()
    readPrototype()
  }
  function hideArch() { archOpen.value = false }
  // 「架构」模式和画布绑在一起：打开画布就切过去，关掉回到原来的模式
  let intentBefore = 'auto'
  watch(archOpen, open => {
    if (open && composerIntent.value !== 'architecture') { intentBefore = composerIntent.value; composerIntent.value = 'architecture' }
    if (!open && composerIntent.value === 'architecture') composerIntent.value = intentBefore || 'auto'
  })

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
  // localRev：画布上每改一下就加一。从原型读回来时要是这期间你又改过，就不拿读回来的盖掉（不然刚改的会丢），过一会儿再读
  let localRev = 0
  function scheduleSave() { localRev++; clearTimeout(saveTimer); saveTimer = setTimeout(saveNow, 500) }
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
    // 选中的、AI 刚改到的：把它上面几层都展开，不然看不到
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
  // ---------- 从原型读 ----------
  const hasPrototype = () => (sourceInfo.value.source || '').length > 400
  // 导入过原型：展开图 → 页面树，并进画布（后台只合并不冲掉）。还没展开过就先展开，展开完这里自动再读。
  // 没有原型：画布是空的，等你自己加
  async function readPrototype() {
    if (!project.value || archBusy.value === 'read') return
    if (!hasPrototype()) { if (!arch.value) arch.value = { ...emptyArchitecture(project.value.name || ''), nodes: [] }; return }
    // 正在改名：等你改完再读
    if (archRenaming.value) { clearTimeout(readTimer); readTimer = setTimeout(readPrototype, 1500); return }
    await saveNow()
    const rev = localRev
    archBusy.value ||= 'read'
    try {
      const bundle = await s.post(`${url()}/refresh`, { page_id: s.pageId.value })
      // 读的这一会儿你又改了：这份读回来的不算（它没有你刚改的），存好再读一次
      if (rev !== localRev) { clearTimeout(readTimer); readTimer = setTimeout(readPrototype, 1500); return }
      if (bundle.refreshed) { apply(bundle); if (archSelected.value && !selectedItem()) archSelected.value = null }
      // 原型改过、还有页面没跟着展开（或者从来没展开过）：把它们点一遍，展开完这里自动再读。不花 token
      if (!expand.batch && (bundle.reason === 'no_expand' || expand.routes.some(r => !isFresh(r.hash)))) expandAll(previewRoute.value || '')
    } catch (e) { archError.value = e.message } finally { if (archBusy.value === 'read') archBusy.value = '' }
  }
  // AI 在原型里改完，展开图在后台同步；它一变就再读一遍（停手 1.5 秒后，免得一页一页地闪）
  let readTimer = null
  watch(() => [expand.scope, expand.routes.map(r => r.hash).join(','), Object.entries(expand.entries).map(([r, e]) => r + e.hash).join(',')].join('|'), () => {
    if (!archOpen.value) return
    clearTimeout(readTimer); readTimer = setTimeout(readPrototype, 1500)
  })
  const archReading = () => archBusy.value === 'read' || (archOpen.value && hasPrototype() && (expand.discovering || (expand.batch && (Object.keys(expand.jobs).length > 0 || expand.queued.length > 0))))

  // ---------- 和 AI ----------
  // 「架构」模式那一轮做完：重新读画布，改到的节点亮一下、上面几层展开
  async function afterArchChat() {
    const before = clone(arch.value?.nodes || [])
    if (arch.value) snapshot()   // AI 改的也能撤销
    await loadArch(true)
    const ids = diffNodes(before, arch.value?.nodes || []).filter(c => c.kind !== 'remove').map(c => c.id)
    const open = {}
    for (const id of ids) for (const p of findNode(arch.value, id)?.parents || []) open[p.id] = true
    archExpand.value = { ...archExpand.value, ...open }
    archFlash.value = new Set(ids)
    clearTimeout(flashTimer); flashTimer = setTimeout(() => { archFlash.value = new Set() }, 4000)
  }
  // 还没同步到原型的改动。有原型但还没读过（base 还没有）时先不算，免得一打开就满屏都是
  const archChanges = computed(() => !arch.value || (!archBase.value && hasPrototype()) ? [] : pendingChanges(archBase.value, arch.value.nodes))
  // 同步到原型：挂在输入框上面一张卡片、切到「自动」，你看一眼（可以补一句）再发。AI 改完，原型一变画布自动再读，对上的就不算了
  // 传了 id 就只同步那一块（卡片工具条上的「同步」）
  // 有没有记下的改动都能点：有改动就交代这几处；没有就让 AI 照画布核对这一块（或整个原型），对不上的照画布改
  function syncToPrototype(id = '') {
    if (!arch.value) return
    const list = id ? changesUnder(arch.value, archChanges.value, id) : archChanges.value
    const node = id ? findNode(arch.value, id)?.node : null
    composerIntent.value = 'auto'
    // 不往输入框里塞一大段：像附件一样挂一张小卡片（标题 + 几处改动），输入框留给你写补充
    s.syncAttach.value = {
      title: node ? `同步「${node.name}」到原型` : '同步到原型',
      items: list.length ? list.map(changeLabel) : [node ? '照画布核对这一块，对不上的照画布改' : '照画布核对整个原型，对不上的照画布改'],
      message: list.length ? syncMessage(list) : checkMessage(arch.value, node),
    }
    s.composer?.value?.focus()
  }


  // 键盘：选中页面树的节点后，回车加同级、Tab 加子项、Delete 删除、F2 改名；⌘Z 撤销架构里的改动
  function archKey(event) {
    const key = event.key, command = event.metaKey || event.ctrlKey
    if (command && key.toLowerCase() === 'z' && !event.shiftKey) { event.preventDefault?.(); undoArch(); return true }
    const sel = archSelected.value
    if (sel?.kind !== 'node' || command) return false
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

  return { arch, archIssues, archCounts, archMounted, archBusy, archError, archSelected, archShowDesc, archShowFields, archQuery,
    archRemoved, archHistory: history, loadArch, showArch, hideArch, saveArch: saveNow, archSnapshot: snapshot, archDirty: dirty, archChange: change,
    archLevel, archExpand, nodeOpen, openNode, setLevel, archReading, archFlash, archBase, archChanges, syncToPrototype,
    undoArch, archSelect: select, archSelectedItem: selectedItem, archAdd, archSibling, archMove, archToggle, archRemove,
    readPrototype, afterArchChat, archRenaming, archKey, renameNode,
    cloneArch: () => clone(arch.value) }
}
