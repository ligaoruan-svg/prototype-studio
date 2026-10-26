// 架构画布里不依赖界面的那部分：节点类型、树的增删改移、两棵树比改了什么（AI 改完画布后高亮、还有几处没同步到原型）、
// 同步到原型时交给 AI 的话、和原型对不对得上。
// 数据结构和 backend/architecture.py 一致；后台存的时候会再收拾一遍（类型、编号、长度）

export const NODE_TYPES = {
  module: { label: '模块', short: '模块' },
  page: { label: '菜单页', short: '菜单页' },
  tab: { label: '页签', short: '页签' },
  drill: { label: '下钻页', short: '下钻' },
  modal: { label: '弹窗', short: '弹窗' },
  drawer: { label: '抽屉', short: '抽屉' },
  wizard: { label: '向导', short: '向导' },
  jump: { label: '跳转', short: '跳转' },
  block: { label: '区块', short: '区块' },
  table: { label: '表格', short: '表格' },
  button: { label: '按钮', short: '按钮' },
  feature: { label: '功能', short: '功能' },
}
export const LAYER_TYPES = ['modal', 'drawer', 'wizard']
// 按钮点了以后：打开哪个弹窗 / 跳到哪一页 / 直接执行 / 先二次确认
export const ACTIONS = { open: '打开', jump: '跳到', run: '执行', confirm: '二次确认' }
export const SCREEN_TYPES = ['page', 'tab', 'drill']
// 会做成一个页面的：菜单页、页签、下钻页；还有下面什么都没挂的模块——它就是一个一级菜单页。后台 is_screen 同一条规则
export const isScreenNode = n => SCREEN_TYPES.includes(n?.type) || (n?.type === 'module' && !(n.children || []).length)
// 在某种节点下面加子项时，可以选哪些类型（第一个是默认）
export const CHILD_TYPES = {
  root: ['module', 'page'],
  module: ['page'],
  page: ['tab', 'block', 'table', 'button', 'modal', 'drawer', 'drill', 'wizard', 'feature'],
  tab: ['block', 'table', 'button', 'modal', 'drawer', 'drill', 'wizard', 'feature'],
  drill: ['block', 'table', 'button', 'modal', 'drawer', 'drill', 'feature'],
  modal: ['block', 'table', 'button', 'feature'],
  drawer: ['block', 'table', 'button', 'feature'],
  wizard: ['block', 'table', 'button', 'feature'],
  block: ['button', 'table', 'block', 'feature'],
  table: ['button', 'feature'],
  button: ['feature'],
  jump: [],
  feature: [],
}
export const newId = prefix => prefix + Math.random().toString(36).slice(2, 10).padEnd(8, '0')
export const clone = value => JSON.parse(JSON.stringify(value))

export function emptyArchitecture(name = '') {
  return {
    version: 1, status: 'draft', scope: 'pc', name, summary: '', roles: [],
    nodes: [{ id: newId('n'), type: 'module', name: '新模块', desc: '', children: [] }],
    entities: [], relations: [], lanes: [], steps: [], rules: [],
  }
}

// ---------- 树 ----------
export function* walk(nodes, depth = 0, parents = []) {
  for (const node of nodes || []) {
    yield { node, depth, parents }
    yield* walk(node.children, depth + 1, [...parents, node])
  }
}
export function findNode(arch, id) {
  for (const item of walk(arch?.nodes)) if (item.node.id === id) return item
  return null
}
// 这一层的兄弟数组（最外层就是 arch.nodes）
function siblingsOf(arch, id) {
  const hit = findNode(arch, id)
  if (!hit) return null
  return hit.parents.length ? hit.parents[hit.parents.length - 1].children : arch.nodes
}
export function countBelow(node) {
  let n = 0
  for (const _ of walk(node?.children)) n++   // eslint-disable-line no-unused-vars
  return n
}
export function addChild(arch, parentId, type, name) {
  const parent = parentId ? findNode(arch, parentId)?.node : null
  const list = parent ? (parent.children ||= []) : arch.nodes
  const kind = type || (CHILD_TYPES[parent?.type || 'root'] || ['feature'])[0] || 'feature'
  const node = { id: newId('n'), type: kind, name: name || '新' + NODE_TYPES[kind].label, desc: '', children: [] }
  list.push(node)
  if (parent) parent.collapsed = false
  return node
}
export function addSibling(arch, id) {
  const list = siblingsOf(arch, id)
  if (!list) return null
  const index = list.findIndex(n => n.id === id)
  const kind = list[index].type
  const node = { id: newId('n'), type: kind, name: '新' + NODE_TYPES[kind].label, desc: '', children: [] }
  list.splice(index + 1, 0, node)
  return node
}
// 删掉一个节点：返回删掉的那个（含下面的全部），撤销时原样放回同一位置
export function removeNode(arch, id) {
  const list = siblingsOf(arch, id)
  if (!list) return null
  const index = list.findIndex(n => n.id === id)
  const [node] = list.splice(index, 1)
  // 流程里指向它的步骤把链接断开，免得指着一个不存在的页面
  for (const step of arch.steps || []) if (step.node && !findNode(arch, step.node)) delete step.node
  return node
}
export function moveNode(arch, id, delta) {
  const list = siblingsOf(arch, id)
  if (!list) return false
  const index = list.findIndex(n => n.id === id), to = index + delta
  if (to < 0 || to >= list.length) return false
  const [node] = list.splice(index, 1)
  list.splice(to, 0, node)
  return true
}
// 删除影响到什么：下面挂着几项
export function impactOf(arch, id) {
  const node = findNode(arch, id)?.node
  const below = node ? countBelow(node) : 0
  return below ? `含 ${below} 项` : ''
}

// 一个节点在哪一页里（最外层的菜单页 / 下钻页）
export function screenOf(arch, id) {
  const hit = findNode(arch, id)
  if (!hit) return null
  const chain = [...hit.parents, hit.node]
  return chain.find(isScreenNode) || null
}
// 按钮写的「新增报修工单（业主来电代录）」和弹窗名「新增报修工单」算同一个：括号里的补充、末尾的「弹窗 / 抽屉」不算
export const looseName = name => String(name || '').replace(/[（(][^（()）]*[）)]/g, '').replace(/\s+|(弹窗|弹框|抽屉|对话框|页面)$/g, '')
export const sameName = (a, b) => a === b || (!!looseName(a) && looseName(a) === looseName(b))
// 表格上的「状态」列怎么流转：同一页里写了选项的「xx状态」下拉（筛选里的「报修状态：待派单/处理中/已完成」），
// 没有就看这一页用到的数据里写的状态
export function statesOf(arch, id) {
  const hit = findNode(arch, id)
  if (!hit) return []
  const screen = [...hit.parents, hit.node].find(isScreenNode)
  for (const { node } of walk(screen ? screen.children : [])) {
    for (const raw of node.fields || []) {
      const m = String(raw).match(/^[^（(]*状态[^（(]*[（(](?:下拉|单选)[：:]([^）)]+)[）)]/)
      if (m) return m[1].split(/\s*[/／、]\s*/).filter(Boolean)
    }
  }
  const used = [...hit.parents, hit.node].flatMap(n => n.data || [])
  const pool = (arch.entities || []).filter(e => e.states?.length)
  return (pool.find(e => used.includes(e.name)) || (pool.length === 1 ? pool[0] : null))?.states || []
}
// 同一页里能被按钮打开 / 跳到的东西（给详情里的下拉用）
export function targetsIn(arch, id, action) {
  const screen = screenOf(arch, id)
  if (action === 'jump') return [...walk(arch?.nodes)].map(x => x.node).filter(isScreenNode).map(n => n.name)
  return screen ? [...walk(screen.children)].map(x => x.node).filter(n => LAYER_TYPES.includes(n.type)).map(n => n.name) : []
}

// ---------- 页面 ----------
// 会做成页面的：菜单页（它下面的页签、下钻页、弹窗抽屉都算在这一页里）、没挂子项的模块
export function screens(arch) {
  const out = []
  for (const { node, parents } of walk(arch?.nodes)) {
    if (!isScreenNode(node) || parents.some(p => SCREEN_TYPES.includes(p.type))) continue
    const inside = [...walk(node.children)].map(x => x.node)
    out.push({ id: node.id, name: node.name, type: node.type, path: [...parents.filter(p => p.type !== 'module').map(p => p.name), node.name].join(' / '),
      module: [...parents].reverse().find(p => p.type === 'module')?.name || '',
      tabs: (node.children || []).filter(c => c.type === 'tab').map(c => c.name), drills: inside.filter(c => c.type === 'drill').map(c => c.name) })
  }
  return out
}

// ---------- 两棵树比：改了什么 ----------
// 比较的是这些：名字、类型、位置（挂在谁下面，排第几不算）、介绍和各项写法
const COMPARE = ['type', 'desc', 'fields', 'cols', 'action', 'target', 'when', 'after', 'route', 'entry', 'params', 'back', 'who']
// 原型里看得出来的：改了要同步到原型（介绍、谁用这些只写在画布上，不用同步）。和 backend/arch_expand.py 的 VISIBLE 一致
export const VISIBLE = ['type', 'fields', 'cols', 'action', 'target', 'when']
const PROP_LABEL = { fields: '字段', cols: '列', action: '点了以后', target: '点了以后', when: '什么时候出现', type: '类型', desc: '介绍' }
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null)
function index(nodes) {
  const out = new Map()
  for (const { node, parents } of walk(nodes)) out.set(node.id, { node, parentId: parents[parents.length - 1]?.id || '', path: [...parents.map(p => p.name), node.name] })
  return out
}
// 返回一条条改动：{ kind: 'add' | 'remove' | 'rename' | 'move' | 'edit', id, ... }。整棵加进来 / 删掉的只记最上面那一个
export function diffNodes(before = [], after = [], props = COMPARE) {
  const old = index(before), now = index(after), out = []
  for (const [id, cur] of now) {
    const prev = old.get(id)
    if (!prev) { if (!cur.parentId || old.has(cur.parentId)) out.push({ kind: 'add', id, node: cur.node, parent: cur.path.slice(0, -1) }); continue }
    if (prev.node.name !== cur.node.name) out.push({ kind: 'rename', id, from: prev.node.name, to: cur.node.name, path: cur.path })
    if (prev.parentId !== cur.parentId) out.push({ kind: 'move', id, node: cur.node, from: prev.path.slice(0, -1), to: cur.path.slice(0, -1) })
    const changed = props.filter(k => !same(prev.node[k], cur.node[k]))
    if (changed.length) out.push({ kind: 'edit', id, node: cur.node, path: cur.path, props: changed, before: prev.node })
  }
  // 删掉的：上面几层用现在的名字（上面那层刚改过名也对得上）
  for (const [id, prev] of old) if (!now.has(id) && (!prev.parentId || now.has(prev.parentId))) out.push({ kind: 'remove', id, parentId: prev.parentId, node: prev.node, path: [...(prev.parentId ? now.get(prev.parentId).path : []), prev.node.name] })
  return out
}
// 和原型对不对得上（从原型读的时候后台标的）：in 原型里有；planned 你规划了、原型里还没有；gone 原型里已经没有
export function protoState(node) {
  if (node?.proto) return 'in'
  return node?.seen ? 'gone' : 'planned'
}
// 还有哪些没同步到原型：画布和上次从原型读的样子（base）比，只看原型里看得出来的；原型里已经没有的那些不算（那是原型那边删的）
// 加出来还没起名、下面也是空的（「新模块」「新菜单页」）也不算：多半是手滑按回车多加的，同步过去只会让 AI 犯糊涂
export const unnamed = node => node?.name === '新' + (NODE_TYPES[node?.type]?.label || '') && !(node.children || []).length && !(node.fields || []).length
export function pendingChanges(base, nodes) {
  return diffNodes(base || [], nodes || [], VISIBLE).filter(c => !(c.kind === 'add' && (protoState(c.node) === 'gone' || unnamed(c.node))))
}
// 只看某一个节点（连同它下面的）的改动：卡片工具条上的「同步」只同步这一块
export function changesUnder(arch, changes, id) {
  const hit = findNode(arch, id)
  if (!hit) return []
  const ids = new Set([id, ...[...walk(hit.node.children)].map(x => x.node.id)])
  return changes.filter(c => ids.has(c.id) || (c.kind === 'remove' && ids.has(c.parentId)))
}
// 给人看的一行：「新增菜单页「测试」」「改了「派单」的字段」
export function changeLabel(c) {
  const type = NODE_TYPES[c.node?.type]?.label || ''
  if (c.kind === 'add') return `新增${type}「${c.node.name}」`
  if (c.kind === 'remove') return `删掉${type}「${c.node.name}」`
  if (c.kind === 'rename') return `「${c.from}」改名为「${c.to}」`
  if (c.kind === 'move') return `「${c.node.name}」挪到「${c.to.join(' / ') || '最外层'}」下面`
  return `改了「${c.node.name}」的${[...new Set(c.props.map(k => PROP_LABEL[k] || k))].join('、')}`
}

// ---------- 同步到原型：交给 AI 的话 ----------
const where = path => path.length ? `「${path.join(' / ')}」` : '最外层'
function describe(node) {
  const type = node.type === 'module' && !(node.children || []).length ? '一级菜单页（左侧菜单加一项，点了直接进这一页）' : NODE_TYPES[node.type]?.label || ''
  const parts = [`${type}「${node.name}」`]
  if (node.desc) parts.push(node.desc)
  if (node.action) parts.push(`点了${ACTIONS[node.action]}${node.target ? `「${node.target}」` : ''}`)
  if (node.when) parts.push(`出现：${node.when}`)
  if (node.fields?.length) parts.push(`字段：${node.fields.join('、')}`)
  if (node.cols?.length) parts.push(`列：${node.cols.join('、')}`)
  if (node.after) parts.push(`确认后：${node.after}`)
  return parts.join('；')
}
function describeTree(node, depth = 1) {
  return [describe(node), ...(node.children || []).map(child => '  '.repeat(depth) + '- ' + describeTree(child, depth + 1))].join('\n')
}
function listDelta(before = [], after = []) {
  const name = f => String(f).replace(/[*🔒]|[（(].*$/g, '').trim()
  const was = new Map(before.map(f => [name(f), f])), now = new Map(after.map(f => [name(f), f]))
  const added = after.filter(f => !was.has(name(f))), gone = before.filter(f => !now.has(name(f))), changed = after.filter(f => was.has(name(f)) && was.get(name(f)) !== f)
  return [added.length ? '加上 ' + added.join('、') : '', gone.length ? '去掉 ' + gone.map(name).join('、') : '', changed.length ? '改成 ' + changed.join('、') : ''].filter(Boolean).join('；') || '按这个来：' + after.join('、')
}
export function syncMessage(changes) {
  const lines = changes.map((c, i) => {
    const n = `${i + 1}. `
    if (c.kind === 'add') return n + (c.parent.length ? `在${where(c.parent)}下面新增 ` : '在最外层新增 ') + describeTree(c.node)
    if (c.kind === 'remove') return n + `删掉${where(c.path.slice(0, -1))}里的${NODE_TYPES[c.node.type]?.label || ''}「${c.node.name}」（连同它下面的）`
    if (c.kind === 'rename') return n + `${where(c.path.slice(0, -1))}里的「${c.from}」改名为「${c.to}」（菜单、标题、按钮上的字都跟着改）`
    if (c.kind === 'move') return n + `把「${c.node.name}」从${where(c.from)}挪到${where(c.to)}下面`
    const bits = c.props.filter(k => k !== 'target' || !c.props.includes('action')).map(k => {
      if (k === 'fields' || k === 'cols') return `${PROP_LABEL[k]}${listDelta(c.before[k], c.node[k])}`
      if (k === 'action' || k === 'target') return `点了改成${c.node.action ? ACTIONS[c.node.action] : '（没定）'}${c.node.target ? `「${c.node.target}」` : ''}`
      if (k === 'type') return `改成${NODE_TYPES[c.node.type]?.label}`
      return `${PROP_LABEL[k] || k}改成：${c.node[k] || '（去掉）'}`
    })
    return n + `${where(c.path)}：` + bits.join('；')
  })
  return '按架构画布的改动改原型，只改下面这几处，别的页面和内容都不要动：\n' + lines.join('\n')
    + '\n字段写法：* 是必填，🔒 是自动带出不用填，括号里是控件和选项（比如「报修分类*（下拉：给排水/电气照明）」）。'
}
