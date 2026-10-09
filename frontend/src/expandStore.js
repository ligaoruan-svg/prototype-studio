// 展开结果的总管：每个页面（原型里的路由）一份快照，落盘保存。
// - 一键展开全部页面：后台排队逐个展开，展开视图和预览都照常用
// - 改了一版：所有已展开的页面自动按原路径同步，正在看的那页排第一
// - 展开视图只管显示这里的结果，不再自己去跑
import { reactive } from 'vue'
import { discoverRoutes, probePage, syncNodes } from './probe.js'

const CONCURRENCY = 2
// 展开结果的格式版本：找法变了（比如开始找子页面）就升一下，旧结果作废重找，免得一直用缺了第二层的老快照
const SCHEMA = 's3'  // s3：换路由的子页面（配置单元/设备）也展开，旧结果要重拍
export const expand = reactive({
  scope: '',          // 项目:页面
  hash: '',           // 当前版本的源码哈希
  routes: [],         // [{ hash: '#factor-list', title }]
  entries: {},        // 路由 → { hash, result, partial }
  jobs: {},           // 路由 → { kind: 'probe' | 'sync', progress }
  queued: [],         // 排队中的路由
  discovering: false,
  error: '',
  focusRoute: null,   // 展开视图正在看的那一页：改完同步时永远排第一
})
const adopted = new Map()   // 预同步的令牌 → 提交后的正式版本哈希
const candidates = new Map() // 预同步的令牌 → 候选版本的副本源码
let ctx = null        // { pid, pageId, makeDoc(route), width }
const queue = []
let active = 0
const touched = {}    // 路由 → 最近点选 / 记过意见的卡片 id，同步时先拍它们

const api = (url, options) => fetch(url, options).then(r => r.ok ? r.json() : Promise.reject(new Error('保存展开结果失败')))
const base = () => `/api/projects/${ctx.pid}/pages/${ctx.pageId}/expand`

// 试玩用的副本源码：和后台展开同一份
export function liveDoc(route) { return ctx ? ctx.makeDoc(route) : '' }
export function isFresh(route) { const e = expand.entries[route]; return !!e && !e.partial && e.hash === expand.hash }
export function touch(route, nodeId) { (touched[route] ||= new Set()).add(nodeId) }

// 切到某个项目的某一页、或者这一页提交了新版本时调用
export async function bindExpand({ pid, pageId, hash, makeDoc, width }) {
  const scope = `${pid}:${pageId}`
  ctx = { pid, pageId, makeDoc, width: width || 1150 }
  hash = `${SCHEMA}:${hash}`
  if (scope !== expand.scope) {
    expand.scope = scope; expand.hash = hash; expand.routes = []; expand.entries = {}; expand.jobs = {}; expand.queued = []; expand.error = ''
    queue.length = 0
    try {
      const saved = await api(base())
      if (expand.scope !== scope) return
      expand.routes = saved.routes || []
      expand.entries = Object.fromEntries(Object.entries(saved.entries || {}).filter(([, e]) => e?.result && String(e.hash || '').startsWith(SCHEMA + ':')).map(([route, e]) => [route, { hash: e.hash, result: e.result }]))
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
  const scope = expand.scope
  try {
    if (!expand.routes.length) {
      const found = await discoverRoutes({ doc: ctx.makeDoc(currentRoute), width: ctx.width })
      if (expand.scope !== scope) return   // 找页面的时候已经切到别的项目了
      expand.routes = found.routes.length ? found.routes : [{ hash: currentRoute, title: '当前页面' }]
      api(`${base()}/routes`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ routes: expand.routes }) }).catch(() => {})
    }
    const order = [...expand.routes].sort((a, b) => (b.hash === currentRoute) - (a.hash === currentRoute))
    for (const r of order) if (!isFresh(r.hash)) schedule(r.hash, expand.entries[r.hash]?.result?.nodes?.length ? 'sync' : 'probe')
  } catch (e) { expand.error = e.message || '没找到页面列表' }
  finally { expand.discovering = false }
}

// 版本变了：所有展开过的页面都按原路径同步（后台慢慢来）
// 正在看的那一页先同步（插队，不等别的页跑完），其余后台慢慢来
function syncStale() {
  const stale = Object.entries(expand.entries).filter(([, e]) => e.hash !== expand.hash && !e.partial && !String(e.hash).startsWith('pending:')).map(([route]) => route)
  const first = stale.filter(r => r === expand.focusRoute)
  for (const route of first) schedule(route, 'sync', true)
  for (const route of stale) if (!first.includes(route)) schedule(route, 'sync')
}
export function setFocusRoute(route) { expand.focusRoute = route }

// ===== 预同步：AI 改完、还在做运行检查的时候，就用候选版本先把正在看的那页拍出来 =====
// 检查 + 提交要一两秒，这段时间副本已经在跑了；提交成功直接认领成正式结果，失败就退回旧快照。
export function presync(token, route, makeDoc) {
  const e = expand.entries[route]
  if (!ctx || route == null || !e?.result?.nodes?.length || e.partial) return
  if (makeDoc) candidates.set(token, makeDoc)
  schedule(route, 'sync', true, true, token)
}
export function adoptPresync(token, rawHash) {
  const hash = `${SCHEMA}:${rawHash}`
  adopted.set(token, hash)
  for (const [route, e] of Object.entries(expand.entries)) if (e.hash === `pending:${token}`) { expand.entries[route] = { hash, result: e.result }; persist(route, hash, e.result) }
}
export function dropPresync(token) {
  adopted.set(token, null)
  for (const [route, e] of Object.entries(expand.entries)) if (e.hash === `pending:${token}`) expand.entries[route] = e.prev || { ...e, hash: '' }
}
function persist(route, hash, result) {
  api(`${base()}/entry`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ route, hash, result }) }).catch(() => {})
}

// 排队：同一页只排一份；正在跑的页面不重复排（跑完会自己检查版本），除非是「重新查找」
function schedule(route, kind, priority = false, force = false, token = null) {
  if (expand.jobs[route] && !force) return
  const at = queue.findIndex(j => j.route === route)
  if (at >= 0) {
    const [job] = queue.splice(at, 1)
    if (kind === 'probe') job.kind = 'probe'
    if (token) job.token = token
    job.priority = job.priority || priority
    priority ? queue.unshift(job) : queue.splice(at, 0, job)
  } else if (priority) queue.unshift({ route, kind, priority, token })
  else queue.push({ route, kind, priority, token })
  pump()
}
function pump() {
  const later = []
  // 插队的任务（正在看的页、预同步）可以多占一个副本，不用等后台那两页跑完
  while (queue.length && (active < CONCURRENCY || (queue[0].priority && active < CONCURRENCY + 1))) {
    const job = queue.shift()
    if (expand.jobs[job.route]) { later.push(job); continue }   // 同一页不同时跑两份，等它跑完
    active++
    run(job).finally(() => { active--; pump() })
  }
  queue.unshift(...later)
  expand.queued = queue.map(j => j.route)
}

async function run({ route, kind, token }) {
  const scope = expand.scope, c = ctx
  // 预同步拍的是候选版本：先挂在「pending:令牌」名下，提交成功再认领
  let hash = token ? `pending:${token}` : expand.hash
  const alive = () => expand.scope === scope
  const entry = expand.entries[route]
  expand.jobs[route] = { kind, progress: null }
  try {
    const doc = ((token && candidates.get(token)) || c.makeDoc)(route)
    let result
    if (kind === 'sync' && entry?.result?.nodes?.length) {
      result = await syncNodes({ doc, nodes: entry.result.nodes, first: [...(touched[route] || [])], width: c.width, height: 800, cancelled: () => !alive() || adopted.get(token) === null,
        onUpdate: update => { if (!alive() || adopted.get(token) === null) return; expand.jobs[route].progress = update; expand.entries[route] = { ...expand.entries[route], result: update, ...(token ? { hash, prev: entry } : {}) } } })
    } else {
      result = await probePage({ doc, width: c.width, height: 800, cancelled: () => !alive(),
        onUpdate: update => { if (!alive()) return; expand.jobs[route].progress = update; if (!entry || entry.partial) expand.entries[route] = { hash, result: update, partial: true } } })
    }
    if (!alive()) return
    if (token) {
      if (adopted.get(token) === null) { expand.entries[route] = entry; return }   // 检查没通过，候选作废
      if (adopted.has(token)) hash = adopted.get(token)                           // 已经提交：直接是正式版本
      expand.entries[route] = hash.startsWith('pending:') ? { hash, result, prev: entry } : { hash, result }
      if (!hash.startsWith('pending:')) persist(route, hash, result)
      delete touched[route]
      return
    }
    expand.entries[route] = { hash, result }
    delete touched[route]
    persist(route, hash, result)
    if (expand.hash !== hash) schedule(route, 'sync')   // 跑的过程中又提交了一版
  } catch (e) {
    if (alive()) expand.error = `${route || '当前页面'}：${e.message || '展开失败'}`
  } finally {
    if (alive()) delete expand.jobs[route]
  }
}
