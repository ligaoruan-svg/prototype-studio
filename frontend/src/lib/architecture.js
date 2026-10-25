// 架构画布里不依赖界面的那部分：节点类型、树的增删改移、两棵树比改了什么（AI 改完画布后高亮用）、和原型对不对得上。
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
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null)
function index(nodes) {
  const out = new Map()
  for (const { node, parents } of walk(nodes)) out.set(node.id, { node, parentId: parents[parents.length - 1]?.id || '', path: [...parents.map(p => p.name), node.name] })
  return out
}
// 返回一条条改动：{ kind: 'add' | 'remove' | 'rename' | 'move' | 'edit', id, ... }。整棵加进来 / 删掉的只记最上面那一个
export function diffNodes(before = [], after = []) {
  const old = index(before), now = index(after), out = []
  for (const [id, cur] of now) {
    const prev = old.get(id)
    if (!prev) { if (!cur.parentId || old.has(cur.parentId)) out.push({ kind: 'add', id, node: cur.node, parent: cur.path.slice(0, -1) }); continue }
    if (prev.node.name !== cur.node.name) out.push({ kind: 'rename', id, from: prev.node.name, to: cur.node.name, path: cur.path })
    if (prev.parentId !== cur.parentId) out.push({ kind: 'move', id, node: cur.node, from: prev.path.slice(0, -1), to: cur.path.slice(0, -1) })
    const props = COMPARE.filter(k => !same(prev.node[k], cur.node[k]))
    if (props.length) out.push({ kind: 'edit', id, node: cur.node, path: cur.path, props, before: prev.node })
  }
  // 删掉的：上面几层用现在的名字（上面那层刚改过名也对得上）
  for (const [id, prev] of old) if (!now.has(id) && (!prev.parentId || now.has(prev.parentId))) out.push({ kind: 'remove', id, node: prev.node, path: [...(prev.parentId ? now.get(prev.parentId).path : []), prev.node.name] })
  return out
}
// 和原型对不对得上（从原型读的时候后台标的）：in 原型里有；planned 你规划了、原型里还没有；gone 原型里已经没有
export function protoState(node) {
  if (node?.proto) return 'in'
  return node?.seen ? 'gone' : 'planned'
}
