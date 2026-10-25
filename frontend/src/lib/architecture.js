// 架构模式里不依赖界面的那部分：节点类型、树的增删改移、流程和数据的布局、按架构生成时发给 AI 的话。
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
  feature: { label: '功能', short: '功能' },
}
export const SCREEN_TYPES = ['page', 'tab', 'drill']
// 在某种节点下面加子项时，可以选哪些类型（第一个是默认）
export const CHILD_TYPES = {
  root: ['module'],
  module: ['page'],
  page: ['tab', 'drawer', 'modal', 'drill', 'wizard', 'jump', 'block', 'feature'],
  tab: ['drawer', 'modal', 'drill', 'wizard', 'jump', 'block', 'feature'],
  drill: ['block', 'drawer', 'modal', 'drill', 'jump', 'feature'],
  modal: ['feature', 'block'],
  drawer: ['feature', 'block'],
  wizard: ['feature', 'block'],
  block: ['feature', 'block'],
  jump: [],
  feature: [],
}
export const FIELD_KINDS = { key: '编号', ref: '引用', derived: '自动算', locked: '继承', plain: '普通' }
export const FIELD_MARKS = { key: '🔑', ref: '↗', derived: 'ƒ', locked: '🔒', plain: '·' }
export const LANE_KINDS = { user: '操作的人', system: '系统自动', skip: '本次不做', external: '外部系统' }
export const PC_RULES = [
  '列表页：页头 → 筛选区（查询 / 重置）→ 操作栏（左边新增、右边导出）→ 表格 → 分页',
  '查看用右侧抽屉，只读；新增 / 编辑用居中弹窗，和查看共用一套表单',
  '多步操作用向导弹窗，带步骤条',
  '跳转带上编号：打开对应的抽屉，或切到对应页签；关掉回到原来的列表',
  '行操作按状态出现（比如离线才有「停用」、待执行才有「开始」）',
  '一个菜单下的几个页签共用菜单入口，每个页签都能单独直达',
  '外部系统回传的数据标明「由 XX 系统回传，只读」',
  '全局只有一份演示数据：引用的东西必须存在；个数、进度、摘要这类派生值从数据算，不能写死',
]

export const newId = prefix => prefix + Math.random().toString(36).slice(2, 10).padEnd(8, '0')
export const clone = value => JSON.parse(JSON.stringify(value))

export function emptyArchitecture(name = '') {
  return {
    version: 1, status: 'draft', scope: 'pc', name, summary: '', roles: [],
    nodes: [{ id: newId('n'), type: 'module', name: '新模块', desc: '', children: [] }],
    entities: [], relations: [],
    lanes: [{ id: 'l_user', name: '管理员', kind: 'user', note: '电脑' }, { id: 'l_sys', name: '系统自动', kind: 'system', note: '' }],
    steps: [], rules: [...PC_RULES],
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
// 删除影响到什么：用到的数据有没有别的页面在用、流程里有几步指着它
export function impactOf(arch, id) {
  const node = findNode(arch, id)?.node
  if (!node) return ''
  const ids = new Set([node.id, ...[...walk(node.children)].map(x => x.node.id)])
  const steps = (arch.steps || []).filter(s => ids.has(s.node)).length
  const below = countBelow(node)
  return [below ? `含 ${below} 项` : '', steps ? `流程里 ${steps} 步会断开链接` : ''].filter(Boolean).join('，')
}

// ---------- 页面、顺序（后台算的顺序优先，这里是没连上后台时的兜底） ----------
export function screens(arch) {
  const out = []
  for (const { node, parents } of walk(arch?.nodes)) {
    if (node.type === 'page' && (node.children || []).some(c => c.type === 'tab')) continue
    if (SCREEN_TYPES.includes(node.type))
      out.push({ id: node.id, name: node.name, type: node.type, path: [...parents.filter(p => p.type !== 'module').map(p => p.name), node.name].join(' / ') })
  }
  return out
}
export function entityRanks(arch) {
  const entities = Object.fromEntries((arch?.entities || []).map(e => [e.name, e]))
  const ranks = {}
  const rank = (name, stack) => {
    if (name in ranks) return ranks[name]
    if (stack.includes(name) || !entities[name]) return 0
    const deps = entities[name].fields.filter(f => f.kind === 'ref' && entities[f.ref] && f.ref !== name).map(f => f.ref)
    ranks[name] = 1 + Math.max(-1, ...deps.map(d => rank(d, [...stack, name])))
    return ranks[name]
  }
  Object.keys(entities).forEach(n => rank(n, []))
  return ranks
}

// ---------- 发给 AI 的话 ----------
export function generateMessage(arch, order, { fresh = true } = {}) {
  const list = (order?.length ? order : screens(arch)).map((s, i) => `${i + 1}. ${s.path || s.name}`).join('\n')
  return `按已确认的架构生成原型（只做电脑端）。${fresh ? '' : '页面里已经有的内容保留，按架构补齐、调整。'}\n`
    + `先在脚本里按架构的「数据」定义一份共用的演示数据，再按下面的顺序一页一步做，每做完一页调 finish_step：\n${list}\n`
    + '每一页都按架构里的统一规则来；本次不做的环节和外部系统不做页面，只生成它们产生的数据。'
}
export function rebuildMessage(arch, node) {
  const hit = findNode(arch, node.id)
  const path = hit ? [...hit.parents.filter(p => p.type !== 'module').map(p => p.name), node.name].join(' / ') : node.name
  return `按已确认的架构，只重做「${path}」这一${NODE_TYPES[node.type]?.label || '页'}：页签、弹窗、抽屉、字段都以架构为准，数据用共用的那一份。其他页面不动。`
}

// ---------- 流程布局：按箭头排列，前面的步骤在左边 ----------
export function layoutFlow(arch) {
  const steps = arch?.steps || [], lanes = arch?.lanes || []
  const byId = Object.fromEntries(steps.map(s => [s.id, s]))
  const col = {}
  const depth = (id, stack = []) => {
    if (id in col) return col[id]
    if (stack.includes(id)) return 0
    const parents = steps.filter(s => (s.next || []).includes(id))
    col[id] = parents.length ? 1 + Math.max(...parents.map(p => depth(p.id, [...stack, id]))) : 0
    return col[id]
  }
  steps.forEach(s => depth(s.id))
  const laneIndex = Object.fromEntries(lanes.map((l, i) => [l.id, i]))
  const taken = new Set(), cells = []
  for (const s of steps) {
    const row = laneIndex[s.lane] ?? 0
    let c = col[s.id]
    while (taken.has(`${row}:${c}`)) c++
    taken.add(`${row}:${c}`)
    cells.push({ step: s, row, col: c })
  }
  const columns = Math.max(1, ...cells.map(c => c.col + 1))
  const edges = []
  for (const s of steps) for (const n of s.next || []) if (byId[n]) edges.push({ from: s.id, to: n })
  return { cells, columns, edges }
}

// ---------- 数据布局：被依赖的在左边一列 ----------
export function layoutData(arch) {
  const ranks = entityRanks(arch)
  const columns = []
  for (const e of arch?.entities || []) {
    const r = ranks[e.name] ?? 0
    ;(columns[r] ||= []).push(e)
  }
  const edges = [], seen = new Set()
  const names = new Set((arch?.entities || []).map(e => e.name))
  for (const r of arch?.relations || []) {
    if (!names.has(r.from) || !names.has(r.to)) continue
    seen.add(r.from + '>' + r.to); seen.add(r.to + '>' + r.from)
    edges.push({ from: r.from, to: r.to, label: r.label || '' })
  }
  // 字段引用了别的数据、又没单独写关系的：自动画一条，名字用字段名
  for (const e of arch?.entities || []) for (const f of e.fields || [])
    if (f.kind === 'ref' && names.has(f.ref) && f.ref !== e.name && !seen.has(f.ref + '>' + e.name)) {
      seen.add(f.ref + '>' + e.name); seen.add(e.name + '>' + f.ref)
      edges.push({ from: f.ref, to: e.name, label: f.note ? `${f.name} · ${f.note}` : f.name })
    }
  return { columns: columns.map(c => c || []), edges }
}

// 两张卡片之间的连线：同一列的竖着连，不同列的横着连（带一点弯）
export function connector(a, b) {
  if (!a || !b) return ''
  if (Math.abs(a.x - b.x) < 20) {
    const down = b.y > a.y
    const x1 = a.x + a.w / 2, y1 = down ? a.y + a.h : a.y, x2 = b.x + b.w / 2, y2 = down ? b.y : b.y + b.h
    return `M${x1} ${y1} C${x1} ${(y1 + y2) / 2} ${x2} ${(y1 + y2) / 2} ${x2} ${y2}`
  }
  const forward = b.x > a.x
  const x1 = forward ? a.x + a.w : a.x, y1 = a.y + a.h / 2, x2 = forward ? b.x : b.x + b.w, y2 = b.y + b.h / 2
  const m = (x1 + x2) / 2
  return `M${x1} ${y1} C${m} ${y1} ${m} ${y2} ${x2} ${y2}`
}
