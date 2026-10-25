// 架构模式：先把页面树、共用数据、业务流程理清楚，确认了再按它一页一步生成。
// 架构存在后台（每个项目一份）；这里管打开 / 关闭、改动后自动保存、撤销、让 AI 起草、按架构生成
import { ref, watch } from 'vue'
import { addChild, addSibling, clone, emptyArchitecture, findNode, generateMessage, impactOf, moveNode, newId, rebuildMessage, removeNode } from '../lib/architecture.js'

export function useArchitecture(s) {
  const { project, archOpen, boardOpen, boardFocus, view, api, toast, model, dialogError, sourceInfo } = s
  const arch = ref(null), archIssues = ref([]), archOrder = ref([]), archCounts = ref({})
  const archMounted = ref(false), archLoaded = ref(''), archBusy = ref(''), archError = ref('')
  const archView = ref('tree'), archSelected = ref(null), archShowDesc = ref(true), archQuery = ref('')
  const archRemoved = ref(null)   // 刚删掉的：底部「撤销」条
  const history = ref([])         // 撤销用的快照，最多 60 份
  let saveTimer = null, removedTimer = null, saving = Promise.resolve()

  const url = () => `/api/projects/${project.value.id}/architecture`
  function apply(bundle, replace = true) {
    if (replace) arch.value = bundle.architecture
    archIssues.value = bundle.issues || []; archOrder.value = bundle.order || []; archCounts.value = bundle.counts || {}
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
  watch(() => project.value?.id, () => { archLoaded.value = ''; arch.value = null; archIssues.value = []; archOrder.value = []; if (archOpen.value) loadArch() })

  function showArch() {
    if (!project.value) return
    archMounted.value = true; archOpen.value = true
    boardOpen.value = false; boardFocus.value = null; view.value = 'preview'
    loadArch()
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
  function select(kind, id) { archSelected.value = kind ? { kind, id } : null }
  function selectedItem() {
    const sel = archSelected.value, a = arch.value
    if (!sel || !a) return null
    if (sel.kind === 'root') return a
    if (sel.kind === 'node') return findNode(a, sel.id)?.node || null
    if (sel.kind === 'entity') return a.entities.find(e => e.id === sel.id) || null
    if (sel.kind === 'step') return a.steps.find(x => x.id === sel.id) || null
    if (sel.kind === 'lane') return a.lanes.find(x => x.id === sel.id) || null
    return null
  }
  function archAdd(parentId, type) { const node = change(a => addChild(a, parentId, type)); select('node', node.id); return node }
  function archSibling(id) { const node = change(a => addSibling(a, id)); if (node) select('node', node.id) }
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
  function addEntity() {
    const e = change(a => { const item = { id: newId('e'), name: '新数据' + (a.entities.length + 1), code: '', role: '', desc: '', external: false, fields: [{ name: '编号', kind: 'key' }], states: [] }; a.entities.push(item); return item })
    select('entity', e.id)
  }
  function removeEntity(id) {
    const e = arch.value.entities.find(x => x.id === id)
    if (!e) return
    change(a => { a.entities = a.entities.filter(x => x.id !== id); a.relations = a.relations.filter(r => r.from !== e.name && r.to !== e.name) })
    archSelected.value = null
    archRemoved.value = { name: e.name, impact: '' }
    clearTimeout(removedTimer); removedTimer = setTimeout(() => { archRemoved.value = null }, 8000)
  }
  // 数据改名：页面里用到它的、字段引用它的、关系两头一起改，不然一改名就全断了
  function renameEntity(entity, name) {
    const old = entity.name, next = name.trim()
    if (!next || next === old || arch.value.entities.some(e => e !== entity && e.name === next)) return false
    change(a => {
      entity.name = next
      for (const e of a.entities) for (const f of e.fields) if (f.ref === old) f.ref = next
      for (const r of a.relations) { if (r.from === old) r.from = next; if (r.to === old) r.to = next }
      const fix = nodes => nodes.forEach(n => { if (n.data) n.data = n.data.map(d => d === old ? next : d); fix(n.children || []) })
      fix(a.nodes)
    })
    return true
  }
  function addStep(laneId) {
    const st = change(a => { const item = { id: newId('s'), lane: laneId || a.lanes[0]?.id || '', name: '新步骤', desc: '', next: [] }; a.steps.push(item); return item })
    select('step', st.id)
  }
  function removeStep(id) {
    change(a => { a.steps = a.steps.filter(x => x.id !== id); a.steps.forEach(x => { x.next = (x.next || []).filter(n => n !== id) }) })
    archSelected.value = null
  }
  function addLane() {
    const lane = change(a => { const item = { id: newId('l'), name: '新泳道', kind: 'user', note: '' }; a.lanes.push(item); return item })
    select('lane', lane.id)
  }
  function removeLane(id) {
    change(a => {
      a.lanes = a.lanes.filter(l => l.id !== id)
      const first = a.lanes[0]?.id || ''
      a.steps.forEach(x => { if (x.lane === id) x.lane = first })
    })
    archSelected.value = null
  }
  function startBlank() {
    arch.value = emptyArchitecture(project.value?.name || ''); history.value = []
    select('node', arch.value.nodes[0].id); saveNow()
  }

  // ---------- AI ----------
  function needKey() {
    if (model.value.has_key) return false
    s.openDialog('settings'); dialogError.value = '请先配置模型密钥。'; return true
  }
  async function draftArch(mode, text = '') {
    if (archBusy.value === 'draft' || needKey() || !project.value) return
    await saveNow()
    archBusy.value = 'draft'; archError.value = ''
    const before = arch.value ? JSON.stringify(arch.value) : null
    try {
      const bundle = await s.post(`${url()}/draft`, { mode, text, page_id: s.pageId.value })
      if (before) history.value = [...history.value.slice(-59), before]
      apply(bundle); archSelected.value = null
      toast(mode === 'refine' ? '已补全，不满意可以撤销' : '架构草稿好了：先看一遍，改好再按架构生成')
    } catch (e) { archError.value = e.message } finally { archBusy.value = '' }
  }
  const blocking = () => archIssues.value.filter(i => i.level === 'error')
  // 确认架构：改成「已确认」，回到预览，交给 AI 按架构一页一步做
  async function generateFromArch() {
    if (!arch.value || s.locked.value || needKey()) return
    if (blocking().length) { archError.value = `还有 ${blocking().length} 处对不上，先改好再生成（点上面的「一致性检查」看是哪几处）`; return }
    arch.value.status = 'confirmed'
    await saveNow()
    if (archError.value) return
    const fresh = (sourceInfo.value.source || '').length < 6000
    hideArch(); s.showPreview()
    await s.runAgent(generateMessage(arch.value, archOrder.value, { fresh }), '', { intent: 'edit', includeAnnotations: false, selection: null, architecture: true })
  }
  async function rebuildNode(node) {
    if (!arch.value || s.locked.value || needKey()) return
    await saveNow()
    hideArch(); s.showPreview()
    await s.runAgent(rebuildMessage(arch.value, node), '', { intent: 'edit', includeAnnotations: false, selection: null, architecture: true })
  }

  return { arch, archIssues, archOrder, archCounts, archMounted, archBusy, archError, archView, archSelected, archShowDesc, archQuery,
    archRemoved, archHistory: history, loadArch, showArch, hideArch, saveArch: saveNow, archSnapshot: snapshot, archDirty: dirty, archChange: change,
    undoArch, archSelect: select, archSelectedItem: selectedItem, archAdd, archSibling, archMove, archToggle, archRemove,
    addEntity, removeEntity, renameEntity, addStep, removeStep, addLane, removeLane, startBlank, draftArch, generateFromArch, rebuildNode,
    cloneArch: () => clone(arch.value) }
}
