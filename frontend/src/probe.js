// 展开：在一个看不见的副本里，把这一页能点的按钮挨个点一遍，记下每次多出来的那层弹窗。
// 真正的识别和点击在 backend/bridge.py 注入的脚本里，这里只负责调度：
// 排队、出问题时重载副本、把进度一条条报给界面。

const MAX_TRIES = 120, MAX_DEPTH = 4, BUDGET_MS = 240_000
const plain = value => JSON.parse(JSON.stringify(value ?? null))

// 一个后台副本：载入、发指令、出问题时重载
function probeFrame(doc, width, height, routes = []) {
  const frame = document.createElement('iframe')
  // 不给 allow-modals / allow-popups：副本里就算有人调 alert、window.open，也弹不到用户面前
  frame.setAttribute('sandbox', 'allow-scripts allow-forms')
  frame.setAttribute('aria-hidden', 'true'); frame.tabIndex = -1; frame.title = '后台展开'
  Object.assign(frame.style, { position: 'fixed', left: '-30000px', top: '0', width: width + 'px', height: height + 'px', border: '0' })
  let seq = 0, onLoaded = null
  const waiters = new Map()
  const listener = event => {
    if (event.source !== frame.contentWindow) return
    const data = event.data || {}
    if (data.source !== 'prototype-agent') return
    // LOADED 之后原型自己还会渲染一会儿（路由、初始数据），稍等再动手
    if (data.type === 'LOADED' && onLoaded) { const done = onLoaded; onLoaded = null; setTimeout(done, 450) }
    if (data.type === 'PROBE_REPLY' && waiters.has(data.id)) { waiters.get(data.id)(data); waiters.delete(data.id) }
  }
  const load = () => new Promise((resolve, reject) => {
    const timer = setTimeout(() => { onLoaded = null; reject(new Error('原型加载超时')) }, 20_000)
    onLoaded = () => { clearTimeout(timer); resolve() }
    frame.srcdoc = doc + `\n<!-- pa-probe ${++seq} -->`
  })
  const rpc = (type, payload = {}, ms = 9_000) => new Promise(resolve => {
    const id = ++seq
    const timer = setTimeout(() => { waiters.delete(id); resolve({ ok: false, timeout: true, needReload: true }) }, ms)
    waiters.set(id, data => { clearTimeout(timer); resolve(data) })
    frame.contentWindow?.postMessage(plain({ type, id, ...payload }), '*')
  })
  // 每次重载都要再告诉副本一遍有哪些业务页面：跳到这些页面算「跳走」，不算这一页的下一层
  const reload = async () => { await load(); await rpc('PA_PROBE_INIT', { full: false, routes }) }
  // 点一个按钮（或沿路径点到底）。只有真改了页面（换页、字变了、勾选变了）才重载回干净状态；
  // 点了没反应的按钮不用重载——以前每点一下都重载一次，展开慢主要慢在这
  let reloads = 0
  async function attempt(path, step) {
    let reply = await rpc('PA_PROBE_TRY', { path, step })
    if (reply.needReload) { await reload(); reloads++; reply = await rpc('PA_PROBE_TRY', { path, step }) }
    if (reply.pageChanged || reply.needReload || reply.dirty || reply.subpage || reply.jump || reply.tablink) { await reload(); reloads++ }
    return reply
  }
  window.addEventListener('message', listener)
  document.body.appendChild(frame)
  return { load, rpc, attempt, routes, get reloads() { return reloads }, dispose() { window.removeEventListener('message', listener); frame.remove() } }
}

async function begin(probe, width, height) {
  await probe.load()
  const init = await probe.rpc('PA_PROBE_INIT', { full: true, routes: probe.routes }, 15_000)
  if (init.timeout) throw new Error('原型没有响应')
  return { init, base: { title: init.title, styles: init.styles, page: init.page, width: init.width || width, height: init.height || height } }
}

// 第一次展开：从页面上的按钮出发，一层层找出所有弹窗
// overrides：用户纠正过的认法 {按钮文字: 'jump' | 'subpage' | 'tab'}，点这个按钮时照用户说的算
export async function probePage({ doc, width = 1150, height = 800, routes = [], overrides = {}, pause = null, onUpdate = () => {}, cancelled = () => false }) {
  const probe = probeFrame(doc, width, height, routes)
  const started = Date.now()
  // 后台页面会在两次点击之间停下来等你空闲；等的时间不算进「一页最多找 4 分钟」
  let waited = 0
  const hold = async () => { if (!pause) return; const t = Date.now(); await pause(); waited += Date.now() - t }
  // 找全了没有：每个按钮试出了什么、哪些没试、为什么。展开完在页面卡下面给一行说明
  const coverage = { tried: 0, views: 0, jumps: 0, links: 0, dead: 0, none: { n: 0, labels: [] }, dup: 0, fail: { n: 0, labels: [] }, cut: { n: 0, labels: [] }, left: { n: 0, labels: [], why: '' }, skipped: {}, ms: 0 }
  const note = (bucket, label) => { bucket.n++; const t = String(label || '').replace(/^表格行 · /, '').slice(0, 20); if (t && bucket.labels.length < 12 && !bucket.labels.includes(t)) bucket.labels.push(t) }
  const withFix = (label, step) => (overrides[label] ? { ...step, force: overrides[label] } : step)
  // jumps：这一页上点了会跳到别的业务页面的按钮。它们不进树（那一页有自己的树），只在页面卡下面列出来
  // links：点了切到同一页另一个页签的（整改跟踪 → 异常跟踪）；dead：展示类按钮点了没任何反应，待补
  const result = { title: '', styles: null, page: '', width, height, nodes: [], jumps: [], links: [], dead: [], tried: 0, total: 0, cancelled: false, coverage }
  const report = current => onUpdate(plain({ ...result, current }))
  try {
    await hold()
    const { init, base } = await begin(probe, width, height)
    Object.assign(result, base)
    coverage.skipped = init.skipped || {}
    const queue = (init.triggers || []).map(target => ({ path: [], step: withFix(target.text, { target }), label: target.text, parent: null, depth: 1 }))
    // 页签（巡检计划 / 路线配置 / 巡检点）：同一业务页面的另一个视图，切过去以后里面的按钮也要试
    for (const target of init.tabs || []) queue.push({ path: [], step: withFix('页签 · ' + target.text, { target, tab: true }), label: '页签 · ' + target.text, parent: null, depth: 1 })
    result.total = queue.length
    report(queue[0]?.label || '')
    const seen = new Set()
    while (queue.length && result.tried < MAX_TRIES && Date.now() - started - waited < BUDGET_MS) {
      await hold()
      if (cancelled()) { result.cancelled = true; break }
      const job = queue.shift()
      result.tried++; coverage.tried++
      report(job.label)
      const reply = await probe.attempt(job.path, job.step)
      if (!reply.ok) { note(coverage.fail, job.label); continue }
      if (reply.tablink) {
        coverage.links++
        if (!result.links.some(x => x.parent === job.parent && x.label === job.label)) result.links.push({ parent: job.parent, label: job.label, tab: reply.tablink.tab })
        report(job.label); continue
      }
      if (reply.dead) {
        coverage.dead++
        if (!result.dead.some(x => x.parent === job.parent && x.label === job.label)) result.dead.push({ parent: job.parent, label: job.label })
        report(job.label); continue
      }
      if (reply.jump) {
        const j = reply.jump
        coverage.jumps++
        if (!result.jumps.some(x => x.parent === job.parent && (x.hash || x.title) === (j.hash || j.title)))
          result.jumps.push({ parent: job.parent, label: job.label, hash: j.hash || '', title: j.title || '', ...(j.forced ? { forced: true } : {}) })
        report(job.label)
        continue
      }
      // 第二层：点了进到详情这类子页面。记成一张页面卡，它上面的按钮接着往下找
      const sub = reply.ok && !reply.opened && reply.subpage
      if (sub) {
        // 页签各是各的视图：不能因为两个页签上的按钮一样（都只有「导出」）就当成同一个
        const subKey = sub.tab ? 'tab|' + sub.title : sub.sig
        if (seen.has(subKey) || job.depth >= MAX_DEPTH) { coverage.dup++; continue }
        seen.add(subKey)
        // 原型的详情页常常没有自己的大标题，取到的还是整站标题；那就用点进来的那个按钮的字
        const subTitle = sub.tab ? sub.title : sub.title && sub.title !== result.title ? sub.title : String(job.label || '').replace(/^表格行 · /, '')
        // 子页面里点左边的树、切个筛选，标题没变只是内容换了：还是同一页，不再当一层
        const parentNode = job.parent != null && result.nodes.find(n => n.id === job.parent)
        if (parentNode?.kind === 'subpage' && parentNode.title === subTitle) { coverage.dup++; continue }
        coverage.views++
        const node = { id: result.nodes.length + 1, parent: job.parent, label: job.label, title: subTitle, html: sub.html, box: sub.box || null, kind: 'subpage', ...(sub.tab ? { tab: true } : {}), ...(job.step.force ? { forced: job.step.force } : {}), path: [...job.path, { ...job.step, nav: true }] }
        result.nodes.push(node)
        const all = sub.triggers || []
        for (const t of all.slice(24)) note(coverage.cut, t.text)
        const children = all.slice(0, 24).map(target => ({ step: withFix(target.text, { target }), label: target.text }))
        for (const child of children) queue.push({ ...child, path: node.path, parent: node.id, depth: job.depth + 1 })
        result.total += children.length
        report(job.label)
        continue
      }
      const opened = reply.opened
      if (!opened) { note(coverage.none, job.label); continue }
      if (seen.has(opened.sig)) { coverage.dup++; continue }
      seen.add(opened.sig)
      coverage.views++
      const node = { id: result.nodes.length + 1, parent: job.parent, label: job.label, title: opened.title, html: opened.html, box: opened.box, layerSel: opened.layerSel || '', path: [...job.path, job.step] }
      result.nodes.push(node)
      if (job.depth < MAX_DEPTH) {
        const all = [
          ...(opened.triggers || []).map(target => ({ step: { target, inLayer: true }, label: target.text })),
          ...(opened.branches || []).map(branch => ({ step: { ...branch.step, inLayer: true }, label: branch.label })),
        ]
        for (const c of all.slice(12)) note(coverage.cut, c.label)
        const children = all.slice(0, 12)
        for (const child of children) queue.push({ ...child, path: node.path, parent: node.id, depth: job.depth + 1 })
        result.total += children.length
      }
      report(job.label)
    }
    // 没轮到的：次数 / 时间用完了，或者中途停了
    for (const job of queue) note(coverage.left, job.label)
    if (queue.length) coverage.left.why = result.cancelled ? '中途停了' : result.tried >= MAX_TRIES ? `一页最多试 ${MAX_TRIES} 个` : '一页最多找 4 分钟'
    coverage.ms = Date.now() - started - waited
    coverage.reloads = probe.reloads
    return plain(result)
  } finally { probe.dispose() }
}

// 改完之后同步：已经知道每张卡怎么点开，直接按路径重新点一遍拍新快照，
// 不再把整页按钮从头试一遍。刚改的那张排第一个，通常一两秒就换上新样子。
export async function syncNodes({ doc, pause = null, nodes = [], jumps = [], links = [], dead = [], coverage = null, first = [], width = 1150, height = 800, routes = [], onUpdate = () => {}, cancelled = () => false }) {
  const probe = probeFrame(doc, width, height, routes)
  // 每张卡先标「更新中」，拍到新样子再去掉：哪张已经是新的、哪张还在等，一眼能看出来
  const result = { title: '', styles: null, page: '', width, height, nodes: plain(nodes).map(n => ({ ...n, pending: true })), jumps: plain(jumps), links: plain(links), dead: plain(dead), coverage: plain(coverage), done: 0, total: nodes.length, stale: 0 }
  // 重拍时取不到标题（子页面常常只有整站标题）就留着原来的，免得卡片标题变空
  const keepTitle = (node, title, pageTitle) => (!title || (node.kind === 'subpage' && title === pageTitle) ? node.title : title)
  const report = () => onUpdate(plain(result))
  try {
    if (pause) await pause()
    const { base } = await begin(probe, width, height)
    Object.assign(result, base)
    report()   // 页面本身那张卡先换上
    const order = [...nodes].sort((a, b) => first.includes(b.id) - first.includes(a.id))
    for (const node of order) {
      if (pause) await pause()
      if (cancelled()) break
      const reply = await probe.attempt(node.path.slice(0, -1), node.path[node.path.length - 1])
      const at = result.nodes.findIndex(n => n.id === node.id)
      const opened = reply.ok && (node.kind === 'subpage' ? reply.subpage : reply.opened)
      // 点不开了（按钮被改名、被删了）就保留旧快照并标出来，刷新时会重新找
      result.nodes[at] = opened
        ? { ...result.nodes[at], title: keepTitle(result.nodes[at], opened.title, result.title), html: opened.html, box: node.kind === 'subpage' ? (opened.box || null) : opened.box, layerSel: opened.layerSel || result.nodes[at].layerSel, stale: false, pending: false }
        : { ...result.nodes[at], stale: true, pending: false }
      if (!opened) result.stale++
      result.done++
      report()
    }
    result.nodes = result.nodes.map(n => ({ ...n, pending: false }))   // 中途取消的也别一直挂着「更新中」
    return plain(result)
  } finally { probe.dispose() }
}

// 这个原型里有哪些页面（导航里的 #路由）
export async function discoverRoutes({ doc, width = 1150, height = 800 }) {
  const probe = probeFrame(doc, width, height)
  try {
    await probe.load()
    const reply = await probe.rpc('PA_PROBE_ROUTES', {}, 9_000)
    if ((reply.routes || []).length >= 2) return { routes: reply.routes, current: reply.current || '' }
    // 菜单不是 #链接（用脚本切页的原型）：把菜单每一项点一遍，看点完到了哪一页
    const nav = await probe.rpc('PA_PROBE_NAV', {}, 50_000)
    return { routes: nav.routes || reply.routes || [], current: reply.current || nav.current || '' }
  } finally { probe.dispose() }
}
