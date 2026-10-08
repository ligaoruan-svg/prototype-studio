// 展开：在一个看不见的副本里，把这一页能点的按钮挨个点一遍，记下每次多出来的那层弹窗。
// 真正的识别和点击在 backend/bridge.py 注入的脚本里，这里只负责调度：
// 排队、出问题时重载副本、把进度一条条报给界面。

const MAX_TRIES = 80, MAX_DEPTH = 3, BUDGET_MS = 150_000
const plain = value => JSON.parse(JSON.stringify(value ?? null))

export async function probePage({ doc, width = 1150, height = 800, onUpdate = () => {}, cancelled = () => false }) {
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

  window.addEventListener('message', listener)
  document.body.appendChild(frame)
  const started = Date.now()
  const result = { title: '', styles: null, page: '', width, height, nodes: [], tried: 0, total: 0, cancelled: false }
  const report = current => onUpdate(plain({ ...result, current }))
  try {
    await load()
    const init = await rpc('PA_PROBE_INIT', { full: true }, 15_000)
    if (init.timeout) throw new Error('原型没有响应')
    Object.assign(result, { title: init.title, styles: init.styles, page: init.page, width: init.width || width, height: init.height || height })
    const queue = (init.triggers || []).map(target => ({ path: [], step: { target }, label: target.text, parent: null, depth: 1 }))
    result.total = queue.length
    report(queue[0]?.label || '')
    const seen = new Set()
    while (queue.length && result.tried < MAX_TRIES && Date.now() - started < BUDGET_MS) {
      if (cancelled()) { result.cancelled = true; break }
      const job = queue.shift()
      result.tried++
      report(job.label)
      let reply = await rpc('PA_PROBE_TRY', { path: job.path, step: job.step })
      if (reply.needReload) { await reload(); reply = await rpc('PA_PROBE_TRY', { path: job.path, step: job.step }) }
      // 没弹出东西的按钮可能已经改了页面（筛选、折叠、清空了弹窗容器），重载回干净状态再试下一个
      if (reply.pageChanged || reply.needReload || (reply.ok && !reply.opened)) await reload()
      const opened = reply.ok && reply.opened
      if (!opened || seen.has(opened.sig)) continue
      seen.add(opened.sig)
      const node = { id: result.nodes.length + 1, parent: job.parent, label: job.label, title: opened.title, html: opened.html, box: opened.box, path: [...job.path, job.step] }
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
  } finally {
    window.removeEventListener('message', listener)
    frame.remove()
  }
}

// 同一页、同一版本、同一个路由，结果不会变；来回切换展开视图不用每次重新点一遍
export const probeCache = new Map()
