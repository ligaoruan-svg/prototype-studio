// 展开结果的总管：每个页面（原型里的路由）一份快照，落盘保存。
// - 一键展开全部页面：后台排队逐个展开，展开视图和预览都照常用
// - 改了一版：所有已展开的页面自动按原路径同步，正在看的那页排第一
// - 展开视图只管显示这里的结果，不再自己去跑
import { reactive } from 'vue'
import { discoverRoutes, probePage, syncNodes } from './probe.js'

const CONCURRENCY = 2
// 展开结果的格式版本：找法变了（比如开始找子页面）就升一下，旧结果作废重找，免得一直用缺了第二层的老快照
// 业务页面清单的找法版本：v2 起首页（刚打开时那一页）也算一页；旧清单下次用到时重找一遍
const ROUTES_V = 3   // 3：菜单改过（AI 加了页面）的旧清单要重新认
let routesV = 0
const SCHEMA = 's7'  // s7：后台副本以前放在屏幕外，被浏览器限速（每个按钮 3 秒、动画冻住），漏了弹窗，旧结果要重拍
export const expand = reactive({
  scope: '',          // 项目:页面
  hash: '',           // 当前版本的源码哈希
  routes: [],         // [{ hash: '#factor-list', title }]
  entries: {},        // 路由 → { hash, result, partial }
  jobs: {},           // 路由 → { kind: 'probe' | 'sync', progress }
  queued: [],         // 排队中的路由
  discovering: false,
  error: '',
  batch: false,      // 点了「一键展开」、还没跑完：按钮显示总进度。单看一页时不算
  focusRoute: null,   // 展开视图正在看的那一页：改完同步时永远排第一
  overrides: {},      // 用户纠正过的认法：路由 → { 按钮文字: 'jump' | 'subpage' | 'tab' }
  avg: loadAvg(),     // 这台电脑上展开 / 同步一页平均要多久（毫秒），用来估「还要多久」
})

// ===== 空闲时再跑 =====
// 正在看的那页（插队任务）全速跑；别的页面只在你停手 1.5 秒以后才接着点，
// 你一动鼠标、敲键盘、滚动，后台就先停在两次点击之间，不跟你抢电脑
const IDLE_MS = 1500
let lastInput = 0
let priorityRunning = 0
if (typeof window !== 'undefined') for (const type of ['pointerdown', 'keydown', 'wheel'])
  window.addEventListener(type, () => { lastInput = Date.now() }, { capture: true, passive: true })
const userBusy = () => !(typeof document !== 'undefined' && document.hidden) && Date.now() - lastInput < IDLE_MS
const sleep = ms => new Promise(r => setTimeout(r, ms))
function loadAvg() {
  try { const v = JSON.parse(localStorage.getItem('pa-expand-avg') || 'null'); if (v?.probe > 0 && v?.sync > 0) return v } catch { /* 读不到就用默认 */ }
  return { probe: 45_000, sync: 8_000 }
}
function learn(kind, ms) {
  if (!(ms > 500)) return
  expand.avg = { ...expand.avg, [kind]: Math.round(expand.avg[kind] * 0.6 + ms * 0.4) }
  try { localStorage.setItem('pa-expand-avg', JSON.stringify(expand.avg)) } catch { /* 存不了下次用默认 */ }
}
// 还要多久（毫秒）：正在跑的按进度估，排队的按平均时长，再按同时跑几页摊开。没有任务时是 null
function jobLeft(job, now) {
  const p = job.progress || {}, active = Math.max(0, now - job.started - (job.paused || 0) - (job.waiting ? now - job.waitSince : 0))
  const done = job.kind === 'sync' ? p.done : p.tried, total = p.total
  if (done >= 3 && total > done) return active * (total - done) / done
  if (total && done >= total) return 2000
  return Math.max(expand.avg[job.kind] - active, 3000)
}
export function routeEta(route, now = Date.now()) { const job = expand.jobs[route]; return job ? jobLeft(job, now) : null }
export function estimate(now = Date.now()) {
  const left = Object.values(expand.jobs).map(job => jobLeft(job, now))
  for (const route of expand.queued) left.push(expand.avg[queue.find(j => j.route === route)?.kind || 'probe'])
  if (!left.length) return null
  return left.reduce((a, b) => a + b, 0) / Math.min(CONCURRENCY, left.length)
}
export const isWaitingForIdle = () => Object.values(expand.jobs).some(j => j.waiting)
const adopted = new Map()   // 预同步的令牌 → 提交后的正式版本哈希
const candidates = new Map() // 预同步的令牌 → 候选版本的副本源码（用完就删，一份几百 KB）
const runningTokens = new Set()
let ctx = null        // { pid, pageId, makeDoc(route), width }
// 每切一次项目 / 页面加一：旧任务一看代号不对就作废。只比 scope 字符串不够——A → B → A 回来时旧任务会"复活"
let gen = 0
let jobSeq = 0
let ready = Promise.resolve()   // 这一页存过的展开结果读完了没有；读完之前不许开跑，免得重找一遍还把存档盖掉
const queue = []
let active = 0
const touched = {}    // 路由 → 最近点选 / 记过意见的卡片 id，同步时先拍它们

const api = (url, options) => fetch(url, options).then(r => r.ok ? r.json() : Promise.reject(new Error('保存展开结果失败')))
const base = (c = ctx) => `/api/projects/${c.pid}/pages/${c.pageId}/expand`

// 交互用的副本源码：和后台展开同一份
export function liveDoc(route) { return ctx ? ctx.makeDoc(route) : '' }
export function isFresh(route) { const e = expand.entries[route]; return !!e && !e.partial && e.hash === expand.hash }
export function touch(route, nodeId) { (touched[route] ||= new Set()).add(nodeId) }

// 切到某个项目的某一页、或者这一页提交了新版本时调用
export async function bindExpand({ pid, pageId, hash, makeDoc, width }) {
  const scope = `${pid}:${pageId}`
  ctx = { pid, pageId, makeDoc, width: width || 1150 }
  hash = `${SCHEMA}:${hash}`
  if (scope !== expand.scope) {
    const g = ++gen
    routesJob = null; expand.discovering = false
    // 换了项目 / 页面：上一个的预同步候选、点选记录都不要了（候选里存着整份页面，留着就是泄漏）
    for (const k of Object.keys(touched)) delete touched[k]
    candidates.clear(); adopted.clear(); runningTokens.clear()
    expand.scope = scope; expand.hash = hash; expand.routes = []; expand.entries = {}; expand.jobs = {}; expand.queued = []; expand.batch = false; expand.error = ''; expand.overrides = {}; routesV = 0
    queue.length = 0
    ready = (async () => {
      try {
        const saved = await api(base())
        if (g !== gen) return
        expand.routes = saved.routes || []
        routesV = saved.routes_v || 0
        expand.overrides = saved.overrides && typeof saved.overrides === 'object' ? saved.overrides : {}
        expand.entries = Object.fromEntries(Object.entries(saved.entries || {}).filter(([, e]) => e?.result && String(e.hash || '').startsWith(SCHEMA + ':')).map(([route, e]) => [route, { hash: e.hash, result: e.result }]))
      } catch { /* 没存过就从空的开始 */ }
    })()
    await ready
    if (g === gen) syncStale()
    return
  }
  await ready
  if (hash && hash !== expand.hash) { expand.hash = hash; syncStale(); refreshRoutes() }
}

// 某一页要看了：没展开过就展开，过期了就同步，都排在最前面
export async function requestRoute(route, { force = false } = {}) {
  if (!ctx) return
  const g = gen
  await ready
  if (g !== gen) return
  await ensureRoutes(route)   // 第一次看某个原型：先认清业务页面，免得把别的页面当成这页的子页面
  if (g !== gen) return
  if (force) return schedule(route, 'probe', true, true)
  if (isFresh(route) || expand.jobs[route]) return
  schedule(route, expand.entries[route]?.result?.nodes?.length && !expand.entries[route].partial ? 'sync' : 'probe', true)
}

// 先弄清这个原型有哪些业务页面：跳到这些页面算「跳走」，不挂进当前页的树。只找一次，找的时候别人等着
let routesJob = null
async function ensureRoutes(currentRoute = '') {
  if ((expand.routes.length >= 2 && routesV >= ROUTES_V) || !ctx) return
  if (routesJob) return routesJob
  const g = gen, c = ctx
  expand.discovering = true
  const job = (async () => {
    try {
      const found = await discoverRoutes({ doc: c.makeDoc(''), width: c.width })   // 从刚打开的样子找，首页才不会漏
      if (g !== gen) return
      // 用户纠正时加进来的页面留着
      const kept = expand.routes.filter(r => r.added && !found.routes.some(f => f.hash === r.hash))
      expand.routes = found.routes.length ? [...found.routes, ...kept] : expand.routes.length ? expand.routes : [{ hash: currentRoute, title: expand.entries[currentRoute]?.result?.title || '当前页面' }]
      routesV = ROUTES_V
      saveRoutes(c)
    } catch (e) { if (g === gen) expand.error = e.message || '没找到页面列表' }
    // 只清自己：切了项目以后新项目可能已经开始自己的查找，旧的跑完不能把它的标记一起清掉（否则会再开一份）
    finally { if (g === gen) expand.discovering = false; if (routesJob === job) routesJob = null }
  })()
  routesJob = job
  return job
}

// 改了一版：菜单里可能多了页面（AI 加了「巡检人员」）或少了。重新认一遍业务页面；
// 新多出来的页面，如果别的页面都展开过了，就在后台也展开它
async function refreshRoutes() {
  if (!ctx || !expand.routes.length) return
  const g = gen, before = new Set(expand.routes.map(r => r.hash))
  routesV = 0
  await ensureRoutes(expand.focusRoute || '')
  if (g !== gen) return
  const fresh = expand.routes.filter(r => !before.has(r.hash))
  if (fresh.length && Object.keys(expand.entries).length >= 2) for (const r of fresh) schedule(r.hash, 'probe')
}

// 一键展开全部页面
export async function expandAll(currentRoute = '') {
  if (!ctx) return
  await ready
  const g = gen
  expand.batch = true
  await ensureRoutes(currentRoute)
  if (g !== gen) return
  const order = [...expand.routes].sort((a, b) => (b.hash === currentRoute) - (a.hash === currentRoute))
  for (const r of order) if (!isFresh(r.hash)) schedule(r.hash, expand.entries[r.hash]?.result?.nodes?.length && !expand.entries[r.hash].partial ? 'sync' : 'probe', r.hash === currentRoute)   // 半截的结果要重找，不能当完整的同步
  pump()   // 全都是新的、没东西要跑：按钮马上回到原样
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

// 认错了，用户自己纠正：这个按钮点出来的其实是 别的业务页面 / 子页面 / 页签。kind 为空 = 恢复自动认。
// 记在磁盘上，这一页马上按新认法重找一遍；以后每次展开都照这个来
export async function setOverride(route, label, kind) {
  if (!ctx || !label) return
  const g = gen, c = ctx
  await ready
  if (g !== gen) return
  const mine = { ...(expand.overrides[route] || {}) }
  if (kind) mine[label] = kind; else delete mine[label]
  const next = { ...expand.overrides }
  if (Object.keys(mine).length) next[route] = mine; else delete next[route]
  expand.overrides = next
  // 撤销「其实是别的业务页面」：当初因为它加进清单的页面也拿掉，不然按自动规则它还是会被当成跳走
  if (kind !== 'jump' && expand.routes.some(r => r.added === label && r.from === route)) {
    expand.routes = expand.routes.filter(r => !(r.added === label && r.from === route))
    saveRoutes(c)
  }
  api(`${base(c)}/overrides`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ overrides: next }) })
    .catch(() => { if (c === ctx) expand.error = '纠正没存上，下次打开可能又按原来的认法' })
  schedule(route, 'probe', true, true)
}
// 用户说「其实是别的业务页面」，而那一页不在清单里（地址是个新的 #路由）：加进业务页面清单
function addRoutes(route, result, c) {
  const extra = (result.jumps || []).filter(j => j.forced && j.hash && !expand.routes.some(r => r.hash === j.hash))
  if (!extra.length) return
  const seen = new Set()
  expand.routes = [...expand.routes, ...extra.filter(j => !seen.has(j.hash) && seen.add(j.hash)).map(j => ({ hash: j.hash, title: (j.title || j.hash).slice(0, 30), added: j.label, from: route }))]
  saveRoutes(c)
}

// ===== 预同步：AI 改完、还在做运行检查的时候，就用候选版本先把正在看的那页拍出来 =====
// 检查 + 提交要一两秒，这段时间副本已经在跑了；提交成功直接认领成正式结果，失败就退回旧快照。
export function presync(token, route, makeDoc) {
  const e = expand.entries[route]
  if (!ctx || route == null || !e?.result?.nodes?.length || e.partial) return
  if (makeDoc) candidates.set(token, makeDoc)
  runningTokens.add(token)
  schedule(route, 'sync', true, true, token)
}
function forget(token) { if (!runningTokens.has(token)) { adopted.delete(token); candidates.delete(token) } }
export function adoptPresync(token, rawHash) {
  const hash = `${SCHEMA}:${rawHash}`
  adopted.set(token, hash)
  // 还在拍的那页先不落盘：卡片里还有「更新中」的旧快照，等它拍完 run 自己按正式版本存
  for (const [route, e] of Object.entries(expand.entries)) if (e.hash === `pending:${token}` && !expand.jobs[route]) { expand.entries[route] = { hash, result: e.result }; persist(route, hash, e.result); if (e.result?.needsProbe?.length) schedule(route, 'probe', route === expand.focusRoute, true) }
  forget(token)
}
export function dropPresync(token) {
  adopted.set(token, null)
  for (const [route, e] of Object.entries(expand.entries)) if (e.hash === `pending:${token}`) expand.entries[route] = e.prev || { ...e, hash: '' }
  forget(token)
}
function saveRoutes(c = ctx) {
  api(`${base(c)}/routes`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ routes: expand.routes, v: routesV }) }).catch(() => {})
}
function persist(route, hash, result, c = ctx) {
  api(`${base(c)}/entry`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ route, hash, result }) })
    .catch(() => { if (c === ctx) expand.error = `${route || '当前页面'}：展开结果没存上（可能太大），下次打开会重新找` })
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
  if (!queue.length && !active && !expand.discovering) expand.batch = false
}

async function run({ route, kind, token, priority }) {
  const g = gen, c = ctx
  // 预同步拍的是候选版本：先挂在「pending:令牌」名下，提交成功再认领
  let hash = token ? `pending:${token}` : expand.hash
  const alive = () => gen === g
  const entry = expand.entries[route]
  // 用编号认自己的任务：expand 是响应式对象，取出来的是代理，和原对象比 === 永远不相等
  const id = ++jobSeq
  expand.jobs[route] = { kind, progress: null, id, started: Date.now(), paused: 0, waiting: false, priority: !!priority }
  const mine = () => expand.jobs[route]?.id === id
  const progress = update => { if (mine()) expand.jobs[route].progress = update }
  // 后台的页面：两次点击之间看一眼，你在用电脑、或者正在看的那页在跑，就先等着
  const pause = priority ? null : async () => {
    if (route === expand.focusRoute || !(priorityRunning > 0 || userBusy())) return
    const t = Date.now()
    if (mine()) Object.assign(expand.jobs[route], { waiting: true, waitSince: t })
    while (alive() && route !== expand.focusRoute && (priorityRunning > 0 || userBusy())) await sleep(300)
    if (mine()) { expand.jobs[route].waiting = false; expand.jobs[route].paused += Date.now() - t }
  }
  if (priority) priorityRunning++
  try {
    const doc = ((token && candidates.get(token)) || c.makeDoc)(route)
    let result
    if (kind === 'sync' && entry?.result?.nodes?.length) {
      result = await syncNodes({ doc, pause, nodes: entry.result.nodes, jumps: entry.result.jumps || [], links: entry.result.links || [], dead: entry.result.dead || [], coverage: entry.result.coverage || null, top: entry.result.top || null, routes: expand.routes.map(r => r.hash), first: [...(touched[route] || [])], width: c.width, height: 800, cancelled: () => !alive() || adopted.get(token) === null,
        onUpdate: update => { if (!alive() || adopted.get(token) === null) return; progress(update); expand.entries[route] = { ...expand.entries[route], result: update, ...(token ? { hash, prev: entry } : {}) } } })
    } else {
      result = await probePage({ doc, pause, overrides: expand.overrides[route] || {}, width: c.width, routes: expand.routes.map(r => r.hash), height: 800, cancelled: () => !alive(),
        onUpdate: update => { if (!alive()) return; progress(update); const now = expand.entries[route]; if (!now || now.partial) expand.entries[route] = { hash, result: update, partial: true } } })
    }
    if (!alive()) return
    if (mine() && !result.cancelled) { const j = expand.jobs[route]; learn(kind === 'sync' ? 'sync' : 'probe', Date.now() - j.started - j.paused) }
    if (kind !== 'sync') addRoutes(route, result, c)
    if (token) {
      if (adopted.get(token) === null) { expand.entries[route] = entry; return }   // 检查没通过，候选作废
      if (adopted.has(token)) hash = adopted.get(token)                           // 已经提交：直接是正式版本
      expand.entries[route] = hash.startsWith('pending:') ? { hash, result, prev: entry } : { hash, result }
      if (!hash.startsWith('pending:')) { persist(route, hash, result, c); if (kind === 'sync' && result.needsProbe?.length) schedule(route, 'probe', !!priority, true) }
      delete touched[route]
      return
    }
    expand.entries[route] = { hash, result }
    delete touched[route]
    persist(route, hash, result, c)
    if (kind === 'sync' && result.needsProbe?.length) schedule(route, 'probe', !!priority, true)   // 页面上多了新按钮：整页重找一遍
  } catch (e) {
    if (!alive()) return
    expand.error = `${route || '当前页面'}：${e.message || '展开失败'}`
    // 同步半路出错：退回旧快照，别让卡片一直转「更新中」
    if (kind === 'sync' && entry) expand.entries[route] = entry
  } finally {
    if (priority) priorityRunning--
    if (token) { runningTokens.delete(token); if (adopted.has(token)) forget(token) }
    if (alive() && mine()) {
      delete expand.jobs[route]
      // 跑的过程中又提交了一版：现在才能排（任务还挂着的时候 schedule 会直接跳过）
      const e = expand.entries[route]
      if (e && !e.partial && e.hash !== expand.hash && !String(e.hash).startsWith('pending:')) schedule(route, 'sync')
    }
  }
}
