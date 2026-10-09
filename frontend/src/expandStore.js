// 展开结果的总管：每个页面（原型里的路由）一份快照，落盘保存。
// - 一键展开全部页面：后台排队逐个展开，展开视图和预览都照常用
// - 改了一版：所有已展开的页面自动按原路径同步，正在看的那页排第一
// - 展开视图只管显示这里的结果，不再自己去跑
import { reactive } from 'vue'
import { discoverRoutes, probePage, syncNodes } from './probe.js'

const CONCURRENCY = 2
export const expand = reactive({
  scope: '',          // 项目:页面
  hash: '',           // 当前版本的源码哈希
  routes: [],         // [{ hash: '#factor-list', title }]
  entries: {},        // 路由 → { hash, result, partial }
  jobs: {},           // 路由 → { kind: 'probe' | 'sync', progress }
  queued: [],         // 排队中的路由
  discovering: false,
  error: '',
})
let ctx = null        // { pid, pageId, makeDoc(route), width }
const queue = []
let active = 0
const touched = {}    // 路由 → 最近点选 / 记过意见的卡片 id，同步时先拍它们

const api = (url, options) => fetch(url, options).then(r => r.ok ? r.json() : Promise.reject(new Error('保存展开结果失败')))
const base = () => `/api/projects/${ctx.pid}/pages/${ctx.pageId}/expand`

export function isFresh(route) { const e = expand.entries[route]; return !!e && !e.partial && e.hash === expand.hash }
export function touch(route, nodeId) { (touched[route] ||= new Set()).add(nodeId) }

// 切到某个项目的某一页、或者这一页提交了新版本时调用
export async function bindExpand({ pid, pageId, hash, makeDoc, width }) {
  const scope = `${pid}:${pageId}`
  ctx = { pid, pageId, makeDoc, width: width || 1150 }
  if (scope !== expand.scope) {
    expand.scope = scope; expand.hash = hash; expand.routes = []; expand.entries = {}; expand.jobs = {}; expand.queued = []; expand.error = ''
    queue.length = 0
    try {
      const saved = await api(base())
      if (expand.scope !== scope) return
      expand.routes = saved.routes || []
      expand.entries = Object.fromEntries(Object.entries(saved.entries || {}).filter(([, e]) => e?.result).map(([route, e]) => [route, { hash: e.hash, result: e.result }]))
    } catch { /* 没存过就从空的开始 */ }
    syncStale()
    return
  }
  if (hash && hash !== expand.hash) { expand.hash = hash; syncStale() }
}

// 某一页要看了：没展开过就展开，过期了就同步，都排在最前面
export function requestRoute(route, { force = false } = {}) {
  if (!ctx) return
  if (force) return schedule(route, 'probe', true, true)
  if (isFresh(route) || expand.jobs[route]) return
  schedule(route, expand.entries[route]?.result?.nodes?.length && !expand.entries[route].partial ? 'sync' : 'probe', true)
}

// 一键展开全部页面
export async function expandAll(currentRoute = '') {
  if (!ctx || expand.discovering) return
  expand.discovering = true; expand.error = ''
  try {
    if (!expand.routes.length) {
      const found = await discoverRoutes({ doc: ctx.makeDoc(currentRoute), width: ctx.width })
      expand.routes = found.routes.length ? found.routes : [{ hash: currentRoute, title: '当前页面' }]
      api(`${base()}/routes`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ routes: expand.routes }) }).catch(() => {})
    }
    const order = [...expand.routes].sort((a, b) => (b.hash === currentRoute) - (a.hash === currentRoute))
    for (const r of order) if (!isFresh(r.hash)) schedule(r.hash, expand.entries[r.hash]?.result?.nodes?.length ? 'sync' : 'probe')
  } catch (e) { expand.error = e.message || '没找到页面列表' }
  finally { expand.discovering = false }
}

// 版本变了：所有展开过的页面都按原路径同步（后台慢慢来）
function syncStale() {
  for (const [route, e] of Object.entries(expand.entries)) if (e.hash !== expand.hash && !e.partial) schedule(route, 'sync')
}

// 排队：同一页只排一份；正在跑的页面不重复排（跑完会自己检查版本），除非是「重新查找」
function schedule(route, kind, priority = false, force = false) {
  if (expand.jobs[route] && !force) return
  const at = queue.findIndex(j => j.route === route)
  if (at >= 0) {
    const [job] = queue.splice(at, 1)
    if (kind === 'probe') job.kind = 'probe'
    priority ? queue.unshift(job) : queue.splice(at, 0, job)
  } else if (priority) queue.unshift({ route, kind })
  else queue.push({ route, kind })
  pump()
}
function pump() {
  const later = []
  while (active < CONCURRENCY && queue.length) {
    const job = queue.shift()
    if (expand.jobs[job.route]) { later.push(job); continue }   // 同一页不同时跑两份，等它跑完
    active++
    run(job).finally(() => { active--; pump() })
  }
  queue.unshift(...later)
  expand.queued = queue.map(j => j.route)
}

async function run({ route, kind }) {
  const scope = expand.scope, hash = expand.hash
  const alive = () => expand.scope === scope
  const entry = expand.entries[route]
  expand.jobs[route] = { kind, progress: null }
  try {
    const doc = ctx.makeDoc(route)
    let result
    if (kind === 'sync' && entry?.result?.nodes?.length) {
      result = await syncNodes({ doc, nodes: entry.result.nodes, first: [...(touched[route] || [])], width: ctx.width, height: 800, cancelled: () => !alive(),
        onUpdate: update => { if (!alive()) return; expand.jobs[route].progress = update; expand.entries[route] = { ...expand.entries[route], result: update } } })
    } else {
      result = await probePage({ doc, width: ctx.width, height: 800, cancelled: () => !alive(),
        onUpdate: update => { if (!alive()) return; expand.jobs[route].progress = update; if (!entry || entry.partial) expand.entries[route] = { hash, result: update, partial: true } } })
    }
    if (!alive()) return
    expand.entries[route] = { hash, result }
    delete touched[route]
    api(`${base()}/entry`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ route, hash, result }) }).catch(() => {})
    if (expand.hash !== hash) schedule(route, 'sync')   // 跑的过程中又提交了一版
  } catch (e) {
    if (alive()) expand.error = `${route || '当前页面'}：${e.message || '展开失败'}`
  } finally {
    if (alive()) delete expand.jobs[route]
  }
}
