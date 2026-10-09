// 展开：在一个看不见的副本里，把这一页能点的按钮挨个点一遍，记下每次多出来的那层弹窗。
// 真正的识别和点击在 backend/bridge.py 注入的脚本里，这里只负责调度：
// 排队、出问题时重载副本、把进度一条条报给界面。

const MAX_TRIES = 120, MAX_DEPTH = 4, BUDGET_MS = 240_000
const plain = value => JSON.parse(JSON.stringify(value ?? null))

// 一个后台副本：载入、发指令、出问题时重载
function probeFrame(doc, width, height) {
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
  const reload = async () => { await load(); await rpc('PA_PROBE_INIT', { full: false }) }
  // 点一个按钮（或沿路径点到底）；没弹出东西的可能改了页面状态，重载回干净状态
  async function attempt(path, step) {
    let reply = await rpc('PA_PROBE_TRY', { path, step })
    if (reply.needReload) { await reload(); reply = await rpc('PA_PROBE_TRY', { path, step }) }
    if (reply.pageChanged || reply.needReload || (reply.ok && !reply.opened)) await reload()
    return reply
  }
  window.addEventListener('message', listener)
  document.body.appendChild(frame)
  return { load, rpc, attempt, dispose() { window.removeEventListener('message', listener); frame.remove() } }
}

async function begin(probe, width, height) {
  await probe.load()
  const init = await probe.rpc('PA_PROBE_INIT', { full: true }, 15_000)
  if (init.timeout) throw new Error('原型没有响应')
  return { init, base: { title: init.title, styles: init.styles, page: init.page, width: init.width || width, height: init.height || height } }
}

// 第一次展开：从页面上的按钮出发，一层层找出所有弹窗
export async function probePage({ doc, width = 1150, height = 800, onUpdate = () => {}, cancelled = () => false }) {
  const probe = probeFrame(doc, width, height)
  const started = Date.now()
  const result = { title: '', styles: null, page: '', width, height, nodes: [], tried: 0, total: 0, cancelled: false }
  const report = current => onUpdate(plain({ ...result, current }))
  try {
    const { init, base } = await begin(probe, width, height)
    Object.assign(result, base)
    const queue = (init.triggers || []).map(target => ({ path: [], step: { target }, label: target.text, parent: null, depth: 1 }))
    result.total = queue.length
    report(queue[0]?.label || '')
    const seen = new Set()
    while (queue.length && result.tried < MAX_TRIES && Date.now() - started < BUDGET_MS) {
      if (cancelled()) { result.cancelled = true; break }
      const job = queue.shift()
      result.tried++
      report(job.label)
      const reply = await probe.attempt(job.path, job.step)
      // 第二层：点了进到详情这类子页面。记成一张页面卡，它上面的按钮接着往下找
      const sub = reply.ok && !reply.opened && reply.subpage
      if (sub) {
        if (seen.has(sub.sig) || job.depth >= MAX_DEPTH) continue
        seen.add(sub.sig)
        // 原型的详情页常常没有自己的大标题，取到的还是整站标题；那就用点进来的那个按钮的字
        const subTitle = sub.title && sub.title !== result.title ? sub.title : String(job.label || '').replace(/^表格行 · /, '')
        const node = { id: result.nodes.length + 1, parent: job.parent, label: job.label, title: subTitle, html: sub.html, box: null, kind: 'subpage', path: [...job.path, { ...job.step, nav: true }] }
        result.nodes.push(node)
        const children = (sub.triggers || []).slice(0, 24).map(target => ({ step: { target }, label: target.text }))
        for (const child of children) queue.push({ ...child, path: node.path, parent: node.id, depth: job.depth + 1 })
        result.total += children.length
        report(job.label)
        continue
      }
      const opened = reply.ok && reply.opened
      if (!opened || seen.has(opened.sig)) continue
      seen.add(opened.sig)
      const node = { id: result.nodes.length + 1, parent: job.parent, label: job.label, title: opened.title, html: opened.html, box: opened.box, layerSel: opened.layerSel || '', path: [...job.path, job.step] }
      result.nodes.push(node)
      if (job.depth < MAX_DEPTH) {
        const children = [
          ...(opened.triggers || []).map(target => ({ step: { target, inLayer: true }, label: target.text })),
          ...(opened.branches || []).map(branch => ({ step: { ...branch.step, inLayer: true }, label: branch.label })),
        ].slice(0, 12)
        for (const child of children) queue.push({ ...child, path: node.path, parent: node.id, depth: job.depth + 1 })
        result.total += children.length
      }
      report(job.label)
    }
    return plain(result)
  } finally { probe.dispose() }
}

// 改完之后同步：已经知道每张卡怎么点开，直接按路径重新点一遍拍新快照，
// 不再把整页按钮从头试一遍。刚改的那张排第一个，通常一两秒就换上新样子。
export async function syncNodes({ doc, nodes = [], first = [], width = 1150, height = 800, onUpdate = () => {}, cancelled = () => false }) {
  const probe = probeFrame(doc, width, height)
  const result = { title: '', styles: null, page: '', width, height, nodes: plain(nodes), done: 0, total: nodes.length, stale: 0 }
  const report = () => onUpdate(plain(result))
  try {
    const { base } = await begin(probe, width, height)
    Object.assign(result, base)
    report()   // 页面本身那张卡先换上
    const order = [...nodes].sort((a, b) => first.includes(b.id) - first.includes(a.id))
    for (const node of order) {
      if (cancelled()) break
      const reply = await probe.attempt(node.path.slice(0, -1), node.path[node.path.length - 1])
      const at = result.nodes.findIndex(n => n.id === node.id)
      const opened = reply.ok && (node.kind === 'subpage' ? reply.subpage : reply.opened)
      // 点不开了（按钮被改名、被删了）就保留旧快照并标出来，刷新时会重新找
      result.nodes[at] = opened
        ? { ...result.nodes[at], title: opened.title, html: opened.html, box: node.kind === 'subpage' ? null : opened.box, layerSel: opened.layerSel || result.nodes[at].layerSel, stale: false }
        : { ...result.nodes[at], stale: true }
      if (!opened) result.stale++
      result.done++
      report()
    }
    return plain(result)
  } finally { probe.dispose() }
}

// 这个原型里有哪些页面（导航里的 #路由）
export async function discoverRoutes({ doc, width = 1150, height = 800 }) {
  const probe = probeFrame(doc, width, height)
  try {
    await probe.load()
    const reply = await probe.rpc('PA_PROBE_ROUTES', {}, 9_000)
    return { routes: reply.routes || [], current: reply.current || '' }
  } finally { probe.dispose() }
}
