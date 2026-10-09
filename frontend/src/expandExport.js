// 把「展开」导出成一个独立的 HTML 文件：按业务页面分节，每页一棵「谁打开谁」的树，
// 卡片是真实界面的静态快照（不是截图，文字能选），不带原型自己的脚本。
// 发给别人双击就能看，不需要原型工坊；要 PDF 就用浏览器「打印 → 存储为 PDF」。
import { buildTree, cardDocument, thumbFrame } from './probeTree.js'

const CARD_W = 560
const esc = v => String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
const clean = label => String(label || '').replace(/^表格行 · /, '')
const BODY = '\u0000PA_BODY\u0000'

// 哪些意见落在这张卡上：和展开视图里「已记 N」同一个口径，再按记下时所在的业务页面过滤
function notesFor(notes, route, node) {
  return notes.filter(a => (!a.view_route || a.view_route === route) &&
    (node.isPage ? !a.in_modal && !a.in_subpage : (a.in_modal || a.in_subpage) === node.title))
}

export function buildExpandExport({ projectName = '', fileName = '', version = '', routes = [], entries = {}, currentHash = '', notes = [], now = new Date() }) {
  // 有页面清单就按清单（侧栏顺序）；从没「一键展开」过就导出手上已有的
  const list = routes.length ? routes.map(r => ({ hash: r.hash, title: r.title }))
    : Object.keys(entries).map(hash => ({ hash, title: entries[hash]?.result?.title || hash || '当前页面' }))
  const styleSets = [], styleKey = new Map(), bodies = [], cards = []
  const styleOf = (styles, scroll) => {
    const key = JSON.stringify(styles || {}) + (scroll ? '|s' : '')
    if (!styleKey.has(key)) { const [a, b] = cardDocument(styles || {}, BODY, { scroll }).split(BODY); styleKey.set(key, styleSets.length); styleSets.push([a, b]) }
    return styleKey.get(key)
  }
  // 一张卡：只在导出文件里留个占位，打开时滚到附近才真正渲染，几十张卡也不卡
  function card(result, node) {
    const frame = { w: result.width || 1150, h: result.height || 800 }
    const pageLike = node.isPage || node.kind === 'subpage'
    const box = pageLike ? { x: 0, y: 0, w: frame.w, h: frame.h } : (node.box || { x: 0, y: 0, ...frame })
    const t = thumbFrame(box, CARD_W, 100000, pageLike ? 1 : 0.8)
    const i = cards.length
    bodies.push(node.html || '')
    cards.push({ s: styleOf(result.styles, pageLike), w: frame.w, h: frame.h, t: t.transform })
    return `<div class="thumb${pageLike ? ' scroll' : ''}" style="width:${t.width}px;height:${t.height}px" data-card="${i}"></div>`
  }
  const kind = node => node.isPage ? '页面' : node.kind === 'subpage' ? '子页面' : '弹窗'
  function block(route, result, node, depth) {
    const own = notesFor(notes, route.hash, node)
    const head = `<header class="card-head"><span class="tag ${node.isPage ? 'page' : node.kind === 'subpage' ? 'sub' : 'modal'}">${kind(node)}</span><h3>${esc(node.title)}</h3>${node.stale ? '<span class="warn">按原路径已打不开，显示的是旧样子</span>' : ''}</header>`
    const list = own.length ? `<ol class="notes">${own.map(a => `<li>${esc(a.note || '')}${a.text ? `<small>「${esc(String(a.text).slice(0, 40))}」</small>` : ''}</li>`).join('')}</ol>` : ''
    const edge = node.isPage ? '' : `<div class="edge">${node.parent == null ? (/^表格行 · /.test(node.label || '') ? '列表行操作' : '页面按钮') : '在上一层里点'}「${esc(clean(node.label))}」打开</div>`
    const kids = (node.children || []).map(c => block(route, result, c, depth + 1)).join('')
    return `<div class="node">${edge}<article class="card">${head}${card(result, node)}${list}</article>${kids ? `<div class="kids">${kids}</div>` : ''}</div>`
  }

  const sections = [], toc = []
  let total = 0, missing = 0
  list.forEach((route, i) => {
    const entry = entries[route.hash]
    const result = entry?.result
    if (!result?.styles) { missing++; toc.push(`<tr><td>${esc(route.title)}</td><td>—</td><td class="muted">未展开</td></tr>`); return }
    const state = entry.partial ? '没展开完' : entry.hash !== currentHash ? '不是最新版本' : ''
    const nodes = result.nodes || []
    const views = nodes.length + 1
    total += views
    const pageNode = { id: 0, isPage: true, title: route.title, html: result.page, children: buildTree(nodes) }
    toc.push(`<tr><td><a href="#p${i}">${esc(route.title)}</a></td><td>${views}</td><td class="${state ? 'warn' : 'ok'}">${state || '已展开'}</td></tr>`)
    sections.push(`<section id="p${i}" class="route"><h2>${esc(route.title)}<small>${views} 个视图${route.hash ? ' · ' + esc(route.hash) : ''}${state ? ` · <b class="warn">${state}</b>` : ''}</small></h2><div class="tree">${block(route, result, pageNode, 0)}</div></section>`)
  })

  const stamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  const title = `${projectName || '原型'} · 展开图`
  // 数据放进 JSON 脚本块：</script> 之类的字样要转义，否则会把外面的脚本提前截断
  const data = JSON.stringify({ styleSets, bodies, cards }).replace(/</g, '\\u003c')
  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(title)}</title><style>${CSS}</style></head><body>
<header class="top"><div><p class="eyebrow">原型工坊 · 展开图</p><h1>${esc(projectName)}</h1><p class="meta">${esc(fileName)}${version ? ' · v' + esc(version) : ''} · 导出于 ${stamp} · ${sections.length} 个业务页面 · ${total} 个视图${missing ? ` · ${missing} 个页面未展开` : ''}</p></div><button type="button" id="print">打印 / 存为 PDF</button></header>
<main><nav class="toc"><h2>目录</h2><table><thead><tr><th>业务页面</th><th>视图</th><th>状态</th></tr></thead><tbody>${toc.join('')}</tbody></table><p class="hint">每张卡是导出时的界面快照：页面和子页面可以在卡片里滚动查看，弹窗只截弹窗本身。卡片下方的编号列表是当时记下、还没处理的修改意见。</p></nav>${sections.join('') || '<p class="empty">还没有展开过任何页面。</p>'}</main>
<script type="application/json" id="pa-data">${data}</script>
<script>${RUNTIME}</script></body></html>`
  return { html, pages: sections.length, views: total, missing }
}

const CSS = `
:root{--ink:#141413;--muted:#6f6e69;--line:#e5e2d6;--shell:#faf9f5;--canvas:#f0eee6;--primary:#b8532f;--soft:#f6e9e2;--warn:#8a5a0b}
*{box-sizing:border-box}body{margin:0;background:var(--canvas);color:var(--ink);font:14px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
.top{position:sticky;top:0;z-index:5;display:flex;align-items:flex-end;justify-content:space-between;gap:16px;padding:18px 28px;background:var(--shell);border-bottom:1px solid var(--line)}
.eyebrow{margin:0;font-size:12px;color:var(--primary);font-weight:600}h1{margin:2px 0;font-size:22px}.meta{margin:0;color:var(--muted);font-size:12.5px}
#print{flex-shrink:0;border:1px solid #e2ded3;background:#fff;border-radius:10px;padding:8px 14px;font:inherit;cursor:pointer}#print:hover{border-color:#c9c1b4}
main{padding:20px 28px 60px}
.toc{max-width:720px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin-bottom:28px}.toc h2{margin:0 0 8px;font-size:15px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}th{color:var(--muted);font-weight:500}
td a{color:var(--ink)}td.ok{color:#4c7a52}td.warn,.warn{color:var(--warn)}td.muted{color:var(--muted)}.hint{margin:10px 0 0;font-size:12px;color:var(--muted)}
.route{margin:0 0 36px}.route h2{display:flex;align-items:baseline;gap:12px;margin:0 0 14px;font-size:18px}.route h2 small{font-size:12px;font-weight:400;color:var(--muted)}
.node{position:relative}.kids{margin:12px 0 0 28px;padding-left:22px;border-left:2px solid #dcd7cb;display:grid;gap:16px}
.edge{display:inline-block;margin-bottom:6px;padding:2px 10px;font-size:12px;color:var(--muted);background:#fff;border:1px solid var(--line);border-radius:20px}
.card{width:${CARD_W + 26}px;max-width:100%;background:#fff;border:1px solid #dfddd5;border-radius:12px;overflow:hidden}
.card-head{display:flex;align-items:center;gap:8px;padding:9px 12px;border-bottom:1px solid var(--line)}.card-head h3{margin:0;font-size:13.5px;flex:1;min-width:0}
.card-head .warn{font-size:11px}
.tag{flex-shrink:0;font-size:11px;padding:1px 7px;border-radius:20px;background:#eef0f3;color:#55606e}.tag.page{background:var(--soft);color:var(--primary)}.tag.sub{background:#eef4ec;color:#4c7a52}
.thumb{position:relative;margin:12px;overflow:hidden;border-radius:6px;background:#f5f7fa;box-shadow:0 1px 4px #2b33200f}
.thumb iframe{position:absolute;left:0;top:0;border:0;transform-origin:0 0;background:#fff}
.notes{margin:0;padding:8px 14px 10px 32px;border-top:1px dashed var(--line);font-size:12.5px;background:#fffaf6}.notes li{margin:2px 0}.notes small{margin-left:6px;color:var(--muted)}
.empty{color:var(--muted)}
@media (max-width:700px){main,.top{padding-left:14px;padding-right:14px}.kids{margin-left:8px;padding-left:12px}}
@media print{.top{position:static}#print{display:none}body{background:#fff}.card,.edge{break-inside:avoid}.edge{break-after:avoid}.route{break-before:page}.toc{break-after:page}}
`

// 导出文件里唯一的脚本：滚到附近再把卡片渲染出来；打印前全部渲染好
const RUNTIME = `(()=>{const D=JSON.parse(document.getElementById('pa-data').textContent);
function show(el){if(el.firstChild)return;const c=D.cards[+el.dataset.card],s=D.styleSets[c.s],f=document.createElement('iframe');
f.setAttribute('sandbox','');f.setAttribute('loading','eager');f.title='界面快照';f.style.width=c.w+'px';f.style.height=c.h+'px';f.style.transform=c.t;f.srcdoc=s[0]+D.bodies[+el.dataset.card]+s[1];el.appendChild(f)}
const all=[...document.querySelectorAll('[data-card]')];
if('IntersectionObserver' in window){const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){show(e.target);io.unobserve(e.target)}}),{rootMargin:'800px'});all.forEach(el=>io.observe(el))}else all.forEach(show);
document.getElementById('print').onclick=()=>{all.forEach(show);const b=document.getElementById('print');b.textContent='准备中…';setTimeout(()=>{b.textContent='打印 / 存为 PDF';print()},1500)};
addEventListener('beforeprint',()=>all.forEach(show));})();`
